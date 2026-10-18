"""
Oracle Database Adapter

Implementación del adapter para Oracle Database con queries de introspección de metadata.

SEGURIDAD: Solo queries a ALL_* y USER_* views (metadata).
NO ejecuta queries sobre datos de usuario.

Requiere:
- oracledb>=2.0.0 (modo thin, no requiere Oracle Instant Client)
"""

import logging
from typing import Any, Dict, List, Optional

import oracledb
from oracledb import DatabaseError, InterfaceError

from app.models.db_metadata import (
    CheckConstraintMetadata,
    ColumnMetadata,
    DatabaseMetadata,
    DataType,
    ForeignKeyMetadata,
    IndexMetadata,
    IndexType,
    PrimaryKeyMetadata,
    SchemaMetadata,
    TableMetadata,
    TableStatistics,
    TableType,
    UniqueConstraintMetadata,
)

from .base_adapter import BaseDBAdapter
from .exceptions import (
    DBAuthenticationError,
    DBConnectionError,
    DBMetadataNotFoundError,
    DBPermissionError,
    DBQueryExecutionError,
    DBTimeoutError,
    DBTLSError,
)
from .tls import build_ssl_context, is_tls_error
from .type_mappers import OracleTypeMapper
from .validators import validate_schema_name, validate_table_name

logger = logging.getLogger(__name__)


class OracleAdapter(BaseDBAdapter):
    """
    Adapter para Oracle Database 11g+.

    Requisitos:
    - Usuario con permisos SELECT en ALL_TABLES, ALL_TAB_COLUMNS, ALL_CONSTRAINTS
    - Usuario con permisos SELECT ANY DICTIONARY (para acceso completo a metadata)

    Casos especiales:
    - NUMBER sin precisión → DECIMAL
    - NUMBER(*, 0) → INTEGER
    - NUMBER(1,0) → BOOLEAN (por convención)
    - VARCHAR2/NVARCHAR2 → VARCHAR
    - CLOB → TEXT
    - TIMESTAMP WITH TIME ZONE → TIMESTAMP
    """

    @property
    def dialect(self) -> str:
        return "oracle"

    # =============================================================================
    # CONNECTION MANAGEMENT
    # =============================================================================

    def connect(self) -> None:
        """Establece conexión con Oracle Database"""
        try:
            host = self.connection_config["host"]
            port = self.connection_config.get("port", 1521)
            service_name = self.connection_config.get("service_name")
            sid = self.connection_config.get("sid")

            # Host, puerto e identificador van como parámetros (no en un descriptor de texto):
            # makedsn solo genera PROTOCOL=TCP y un valor con paréntesis alteraría el descriptor
            if service_name:
                target = {"service_name": service_name}
            elif sid:
                target = {"sid": sid}
            else:
                # Por defecto, el nombre de la base de datos como service name
                target = {"service_name": self.connection_config["database"]}

            username = self.connection_config["user"]
            password = self.connection_config["password"]

            self.connection = oracledb.connect(
                user=username,
                password=password,
                host=host,
                port=port,
                protocol="tcps",
                ssl_context=build_ssl_context(self.tls),
                ssl_server_dn_match=self.tls.verify,
                tcp_connect_timeout=self.timeout,
                **target,
            )

            self._is_connected = True
            logger.info(f"Connected to Oracle: {self.connection_config['database']}@{host}")

        except oracledb.DatabaseError as e:
            (error_obj,) = e.args
            error_code = error_obj.code

            # ORA-01017: invalid username/password
            # ORA-01045: user lacks CREATE SESSION privilege
            if error_code in (1017, 1045):
                raise DBAuthenticationError(f"Invalid credentials for Oracle: {error_obj.message}")

            # Los fallos de certificado en modo thin llegan como DPY-6005, sin código ORA
            if is_tls_error(str(error_obj.message)):
                raise DBTLSError(f"TLS error connecting to Oracle: {error_obj.message}")

            # ORA-12541: TNS:no listener
            # ORA-12154: TNS:could not resolve the connect identifier
            # ORA-12170: TNS:Connect timeout occurred
            if error_code in (12541, 12154, 12170):
                raise DBConnectionError(f"Cannot connect to Oracle: {error_obj.message}")

            raise DBConnectionError(f"Oracle connection error: {error_obj.message}")

        except Exception as e:
            raise DBConnectionError(f"Unexpected error connecting to Oracle: {str(e)}")

    def disconnect(self) -> None:
        """Cierra conexión"""
        if self.connection:
            try:
                self.connection.close()
                self._is_connected = False
                logger.info("Disconnected from Oracle")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")

    def test_connection(self) -> bool:
        """Valida credenciales sin mantener conexión"""
        try:
            self.connect()
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
            cursor.close()
            self.disconnect()
            return True
        except (DBAuthenticationError, DBConnectionError, DBTimeoutError):
            raise
        except Exception as e:
            raise DBConnectionError(f"Connection test failed: {str(e)}")

    # =============================================================================
    # SCHEMA INTROSPECTION
    # =============================================================================

    def _get_default_schema(self) -> str:
        """Retorna el nombre del schema por defecto (usuario actual)"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT USER FROM DUAL")
            schema = cursor.fetchone()[0]
            cursor.close()
            return str(schema)
        except Exception as e:
            logger.error(f"Failed to get default schema: {e}")
            return str(self.connection_config.get("user", "")).upper()

    def get_schemas(self) -> List[str]:
        """
        Lista todos los schemas (usuarios) en la base de datos.

        En Oracle, los schemas son equivalentes a usuarios.
        Filtra schemas del sistema: SYS, SYSTEM, etc.
        """
        query = """
        SELECT DISTINCT OWNER
        FROM ALL_TABLES
        WHERE OWNER NOT IN (
            'SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'APPQOSSYS',
            'WMSYS', 'EXFSYS', 'CTXSYS', 'XDB', 'ANONYMOUS',
            'ORDSYS', 'ORDDATA', 'MDSYS', 'LBACSYS', 'DMSYS',
            'OLAPSYS', 'FLOWS_FILES', 'APEX_PUBLIC_USER'
        )
        ORDER BY OWNER
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            schemas = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return schemas

        except oracledb.DatabaseError as e:
            (error_obj,) = e.args
            raise DBQueryExecutionError(f"Failed to list schemas: {error_obj.message}")

    def get_tables(self, schema: Optional[str] = None) -> List[TableMetadata]:
        """
        Lista todas las tablas en un schema.

        Args:
            schema: Nombre del schema (usuario). Si es None, usa el schema por defecto.

        Returns:
            Lista de TableMetadata
        """
        if schema is None:
            schema = self._get_default_schema()

        schema_name = schema
        validate_schema_name(schema_name)

        query = """
        SELECT
            OWNER,
            TABLE_NAME,
            TABLESPACE_NAME,
            NUM_ROWS
        FROM ALL_TABLES
        WHERE OWNER = :schema_name
        ORDER BY TABLE_NAME
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, schema_name=schema_name.upper())
            rows = cursor.fetchall()
            cursor.close()

            tables = []
            for row in rows:
                tables.append(
                    TableMetadata(
                        name=row[1],
                        schema=row[0],
                        table_type=TableType.TABLE,
                    )
                )

            return tables

        except oracledb.DatabaseError as e:
            (error_obj,) = e.args
            raise DBQueryExecutionError(
                f"Failed to list tables in schema '{schema_name}': {error_obj.message}"
            )

    def get_columns(self, table_name: str, schema: Optional[str] = None) -> List[ColumnMetadata]:
        """
        Obtiene información de columnas de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema. Si es None, usa el schema por defecto.

        Returns:
            Lista de ColumnMetadata
        """
        if schema is None:
            schema = self._get_default_schema()

        schema_name = schema
        validate_schema_name(schema_name)
        validate_table_name(table_name)

        query = """
        SELECT
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.DATA_LENGTH,
            c.DATA_PRECISION,
            c.DATA_SCALE,
            c.NULLABLE,
            c.DATA_DEFAULT,
            c.COLUMN_ID,
            -- Check if column is primary key
            CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 'Y' ELSE 'N' END AS IS_PRIMARY_KEY
        FROM ALL_TAB_COLUMNS c
        LEFT JOIN (
            SELECT acc.OWNER, acc.TABLE_NAME, acc.COLUMN_NAME
            FROM ALL_CONSTRAINTS ac
            JOIN ALL_CONS_COLUMNS acc
                ON ac.CONSTRAINT_NAME = acc.CONSTRAINT_NAME
                AND ac.OWNER = acc.OWNER
            WHERE ac.CONSTRAINT_TYPE = 'P'
        ) pk ON c.OWNER = pk.OWNER
            AND c.TABLE_NAME = pk.TABLE_NAME
            AND c.COLUMN_NAME = pk.COLUMN_NAME
        WHERE c.OWNER = :schema_name
          AND c.TABLE_NAME = :table_name
        ORDER BY c.COLUMN_ID
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, schema_name=schema_name.upper(), table_name=table_name.upper())
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                raise DBMetadataNotFoundError(
                    f"Table '{schema_name}.{table_name}' not found or has no columns"
                )

            type_mapper = OracleTypeMapper()
            columns = []

            for row in rows:
                column_name = row[0]
                oracle_type = row[1]
                data_length = row[2]
                precision = row[3]
                scale = row[4]
                nullable = row[5] == "Y"
                default_value = row[6]
                position = row[7]
                is_pk = row[8] == "Y"

                # Map Oracle type to DataType enum
                # Special handling for NUMBER type
                if oracle_type == "NUMBER":
                    if precision is None and scale is None:
                        # NUMBER without precision/scale → DECIMAL
                        data_type = DataType.DECIMAL
                    elif scale == 0:
                        if precision == 1:
                            # NUMBER(1,0) → BOOLEAN (convention)
                            data_type = DataType.BOOLEAN
                        else:
                            # NUMBER(*,0) → INTEGER
                            data_type = DataType.INTEGER
                    else:
                        # NUMBER with scale → DECIMAL
                        data_type = DataType.DECIMAL
                else:
                    data_type = type_mapper.map_to_standard(oracle_type)

                # For VARCHAR2/CHAR, max_length is data_length
                max_length = (
                    data_length
                    if oracle_type in ("VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR")
                    else None
                )

                # Clean default value (Oracle includes trailing space)
                if default_value:
                    default_value = default_value.strip()

                columns.append(
                    ColumnMetadata(
                        name=column_name,
                        data_type=data_type,
                        is_nullable=nullable,
                        max_length=max_length,
                        numeric_precision=precision,
                        numeric_scale=scale,
                        default_value=default_value,
                        is_primary_key=is_pk,
                        is_auto_increment=False,  # Oracle uses sequences, not auto-increment
                        ordinal_position=position,
                        native_type=oracle_type,
                    )
                )

            return columns

        except oracledb.DatabaseError as e:
            (error_obj,) = e.args
            raise DBQueryExecutionError(
                f"Failed to get columns for '{schema_name}.{table_name}': {error_obj.message}"
            )

    def get_primary_keys(self, schema_name: str, table_name: str) -> List[PrimaryKeyMetadata]:  # type: ignore[override]
        """
        Obtiene claves primarias de una tabla.

        Args:
            schema_name: Nombre del schema
            table_name: Nombre de la tabla

        Returns:
            Lista de PrimaryKeyMetadata (usualmente 1 elemento)
        """
        validate_schema_name(schema_name)
        validate_table_name(table_name)

        query = """
        SELECT
            ac.CONSTRAINT_NAME,
            acc.COLUMN_NAME,
            acc.POSITION
        FROM ALL_CONSTRAINTS ac
        JOIN ALL_CONS_COLUMNS acc
            ON ac.CONSTRAINT_NAME = acc.CONSTRAINT_NAME
            AND ac.OWNER = acc.OWNER
        WHERE ac.OWNER = :schema_name
          AND ac.TABLE_NAME = :table_name
          AND ac.CONSTRAINT_TYPE = 'P'
        ORDER BY acc.POSITION
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, schema_name=schema_name.upper(), table_name=table_name.upper())
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                return []

            # Group columns by constraint name
            pk_dict: Dict[str, List[str]] = {}
            for row in rows:
                constraint_name = row[0]
                column_name = row[1]

                if constraint_name not in pk_dict:
                    pk_dict[constraint_name] = []
                pk_dict[constraint_name].append(column_name)

            # Convert to PrimaryKeyMetadata
            pks = []
            for constraint_name, columns in pk_dict.items():
                pks.append(
                    PrimaryKeyMetadata(
                        constraint_name=constraint_name,
                        table_name=table_name.upper(),
                        column_names=columns,
                    )
                )

            return pks

        except oracledb.DatabaseError as e:
            (error_obj,) = e.args
            raise DBQueryExecutionError(
                f"Failed to get primary keys for '{schema_name}.{table_name}': {error_obj.message}"
            )

    def get_foreign_keys(self, schema_name: str, table_name: str) -> List[ForeignKeyMetadata]:  # type: ignore[override]
        """
        Obtiene claves foráneas de una tabla.

        Args:
            schema_name: Nombre del schema
            table_name: Nombre de la tabla

        Returns:
            Lista de ForeignKeyMetadata
        """
        validate_schema_name(schema_name)
        validate_table_name(table_name)

        query = """
        SELECT
            ac.CONSTRAINT_NAME,
            acc.COLUMN_NAME,
            r_ac.TABLE_NAME AS REFERENCED_TABLE,
            r_acc.COLUMN_NAME AS REFERENCED_COLUMN,
            ac.DELETE_RULE,
            acc.POSITION
        FROM ALL_CONSTRAINTS ac
        JOIN ALL_CONS_COLUMNS acc
            ON ac.CONSTRAINT_NAME = acc.CONSTRAINT_NAME
            AND ac.OWNER = acc.OWNER
        JOIN ALL_CONSTRAINTS r_ac
            ON ac.R_CONSTRAINT_NAME = r_ac.CONSTRAINT_NAME
            AND ac.R_OWNER = r_ac.OWNER
        JOIN ALL_CONS_COLUMNS r_acc
            ON r_ac.CONSTRAINT_NAME = r_acc.CONSTRAINT_NAME
            AND r_ac.OWNER = r_acc.OWNER
            AND acc.POSITION = r_acc.POSITION
        WHERE ac.OWNER = :schema_name
          AND ac.TABLE_NAME = :table_name
          AND ac.CONSTRAINT_TYPE = 'R'
        ORDER BY ac.CONSTRAINT_NAME, acc.POSITION
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, schema_name=schema_name.upper(), table_name=table_name.upper())
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                return []

            # Group by constraint name
            fk_dict = {}
            for row in rows:
                constraint_name = row[0]
                column_name = row[1]
                referenced_table = row[2]
                referenced_column = row[3]
                delete_rule = row[4]

                if constraint_name not in fk_dict:
                    fk_dict[constraint_name] = {
                        "columns": [],
                        "referenced_table": referenced_table,
                        "referenced_columns": [],
                        "on_delete": delete_rule if delete_rule else "NO ACTION",
                    }

                fk_dict[constraint_name]["columns"].append(column_name)
                fk_dict[constraint_name]["referenced_columns"].append(referenced_column)

            # Convert to ForeignKeyMetadata
            fks = []
            for constraint_name, data in fk_dict.items():
                fks.append(
                    ForeignKeyMetadata(
                        constraint_name=constraint_name,
                        table_name=table_name.upper(),
                        column_names=data["columns"],
                        referenced_table=data["referenced_table"],
                        referenced_columns=data["referenced_columns"],
                        on_delete=data["on_delete"],
                        on_update=None,  # Oracle doesn't support ON UPDATE CASCADE
                    )
                )

            return fks

        except oracledb.DatabaseError as e:
            (error_obj,) = e.args
            raise DBQueryExecutionError(
                f"Failed to get foreign keys for '{schema_name}.{table_name}': {error_obj.message}"
            )

    def get_unique_constraints(
        self, schema_name: str, table_name: str
    ) -> List[UniqueConstraintMetadata]:
        """
        Obtiene constraints de unicidad de una tabla.

        Args:
            schema_name: Nombre del schema
            table_name: Nombre de la tabla

        Returns:
            Lista de UniqueConstraintMetadata
        """
        validate_schema_name(schema_name)
        validate_table_name(table_name)

        query = """
        SELECT
            ac.CONSTRAINT_NAME,
            acc.COLUMN_NAME,
            acc.POSITION
        FROM ALL_CONSTRAINTS ac
        JOIN ALL_CONS_COLUMNS acc
            ON ac.CONSTRAINT_NAME = acc.CONSTRAINT_NAME
            AND ac.OWNER = acc.OWNER
        WHERE ac.OWNER = :schema_name
          AND ac.TABLE_NAME = :table_name
          AND ac.CONSTRAINT_TYPE = 'U'
        ORDER BY ac.CONSTRAINT_NAME, acc.POSITION
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, schema_name=schema_name.upper(), table_name=table_name.upper())
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                return []

            # Group by constraint name
            unique_dict: Dict[str, List[str]] = {}
            for row in rows:
                constraint_name = row[0]
                column_name = row[1]

                if constraint_name not in unique_dict:
                    unique_dict[constraint_name] = []
                unique_dict[constraint_name].append(column_name)

            # Convert to UniqueConstraintMetadata
            uniques = []
            for constraint_name, columns in unique_dict.items():
                uniques.append(
                    UniqueConstraintMetadata(
                        constraint_name=constraint_name,
                        table_name=table_name.upper(),
                        column_names=columns,
                    )
                )

            return uniques

        except oracledb.DatabaseError as e:
            (error_obj,) = e.args
            raise DBQueryExecutionError(
                f"Failed to get unique constraints for '{schema_name}.{table_name}': {error_obj.message}"
            )

    def get_check_constraints(
        self, schema_name: str, table_name: str
    ) -> List[CheckConstraintMetadata]:
        """
        Obtiene check constraints de una tabla.

        Args:
            schema_name: Nombre del schema
            table_name: Nombre de la tabla

        Returns:
            Lista de CheckConstraintMetadata
        """
        validate_schema_name(schema_name)
        validate_table_name(table_name)

        query = """
        SELECT
            CONSTRAINT_NAME,
            SEARCH_CONDITION
        FROM ALL_CONSTRAINTS
        WHERE OWNER = :schema_name
          AND TABLE_NAME = :table_name
          AND CONSTRAINT_TYPE = 'C'
          AND CONSTRAINT_NAME NOT LIKE 'SYS_%'
        ORDER BY CONSTRAINT_NAME
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, schema_name=schema_name.upper(), table_name=table_name.upper())
            rows = cursor.fetchall()
            cursor.close()

            checks = []
            for row in rows:
                # Filter out NOT NULL constraints (they're captured in column metadata)
                search_condition = row[1]
                if search_condition and "IS NOT NULL" not in search_condition:
                    checks.append(
                        CheckConstraintMetadata(
                            constraint_name=row[0],
                            table_name=table_name.upper(),
                            check_clause=search_condition,
                        )
                    )

            return checks

        except oracledb.DatabaseError as e:
            (error_obj,) = e.args
            raise DBQueryExecutionError(
                f"Failed to get check constraints for '{schema_name}.{table_name}': {error_obj.message}"
            )

    def get_indexes(self, schema_name: str, table_name: str) -> List[IndexMetadata]:  # type: ignore[override]
        """
        Obtiene índices de una tabla.

        Args:
            schema_name: Nombre del schema
            table_name: Nombre de la tabla

        Returns:
            Lista de IndexMetadata
        """
        validate_schema_name(schema_name)
        validate_table_name(table_name)

        query = """
        SELECT
            ai.INDEX_NAME,
            ai.UNIQUENESS,
            aic.COLUMN_NAME,
            aic.COLUMN_POSITION
        FROM ALL_INDEXES ai
        JOIN ALL_IND_COLUMNS aic
            ON ai.INDEX_NAME = aic.INDEX_NAME
            AND ai.OWNER = aic.INDEX_OWNER
        WHERE ai.OWNER = :schema_name
          AND ai.TABLE_NAME = :table_name
          AND ai.INDEX_TYPE != 'LOB'
        ORDER BY ai.INDEX_NAME, aic.COLUMN_POSITION
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, schema_name=schema_name.upper(), table_name=table_name.upper())
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                return []

            # Group by index name
            index_dict = {}
            for row in rows:
                index_name = row[0]
                uniqueness = row[1]
                column_name = row[2]

                if index_name not in index_dict:
                    index_dict[index_name] = {
                        "is_unique": uniqueness == "UNIQUE",
                        "columns": [],
                    }

                index_dict[index_name]["columns"].append(column_name)

            # Convert to IndexMetadata
            # Filter out indexes created for PK/UK constraints
            indexes = []
            for index_name, data in index_dict.items():
                # Skip system-generated constraint indexes
                if index_name.startswith("SYS_"):
                    continue

                # Use BTREE as default type (unique is determined by is_unique flag)
                index_type = IndexType.BTREE

                indexes.append(
                    IndexMetadata(
                        name=index_name,
                        table_name=table_name.upper(),
                        columns=data["columns"],
                        is_unique=data["is_unique"],
                        index_type=index_type,
                    )
                )

            return indexes

        except oracledb.DatabaseError as e:
            (error_obj,) = e.args
            raise DBQueryExecutionError(
                f"Failed to get indexes for '{schema_name}.{table_name}': {error_obj.message}"
            )

    def get_table_statistics(self, schema_name: str, table_name: str) -> TableStatistics:  # type: ignore[override]
        """
        Obtiene estadísticas de una tabla.

        Args:
            schema_name: Nombre del schema
            table_name: Nombre de la tabla

        Returns:
            TableStatistics con row count y tamaño
        """
        validate_schema_name(schema_name)
        validate_table_name(table_name)

        query = """
        SELECT
            NUM_ROWS,
            BLOCKS * :block_size AS total_size_bytes
        FROM ALL_TABLES
        WHERE OWNER = :schema_name
          AND TABLE_NAME = :table_name
        """

        try:
            cursor = self.connection.cursor()

            # Get block size
            cursor.execute("SELECT VALUE FROM V$PARAMETER WHERE NAME = 'db_block_size'")
            block_size_row = cursor.fetchone()
            block_size = int(block_size_row[0]) if block_size_row else 8192

            cursor.execute(
                query,
                block_size=block_size,
                schema_name=schema_name.upper(),
                table_name=table_name.upper(),
            )
            row = cursor.fetchone()
            cursor.close()

            if not row:
                return TableStatistics(
                    table_name=table_name.upper(),
                    row_count=0,
                    size_bytes=0,
                )

            return TableStatistics(
                table_name=table_name.upper(),
                row_count=row[0] if row[0] else 0,
                size_bytes=row[1] if row[1] else 0,
            )

        except oracledb.DatabaseError as e:
            (error_obj,) = e.args
            raise DBQueryExecutionError(
                f"Failed to get statistics for '{schema_name}.{table_name}': {error_obj.message}"
            )

    def get_schema_metadata(self, schema_name: str) -> SchemaMetadata:
        """
        Obtiene metadata completa de un schema (tablas + columnas + constraints).

        Args:
            schema_name: Nombre del schema

        Returns:
            SchemaMetadata con todas las tablas y sus metadatos
        """
        validate_schema_name(schema_name)

        tables = self.get_tables(schema_name)

        # Para cada tabla, obtener metadata completa
        all_pks: List[PrimaryKeyMetadata] = []
        all_fks: List[ForeignKeyMetadata] = []
        all_unique: List[UniqueConstraintMetadata] = []
        all_indexes: List[IndexMetadata] = []
        for table in tables:
            table.columns = self.get_columns(table.table_name, schema_name)
            all_pks.extend(self.get_primary_keys(schema_name, table.table_name))
            all_fks.extend(self.get_foreign_keys(schema_name, table.table_name))
            all_unique.extend(self.get_unique_constraints(schema_name, table.table_name))
            all_indexes.extend(self.get_indexes(schema_name, table.table_name))

        return SchemaMetadata(
            name=schema_name.upper(),
            tables=tables,
            primary_keys=all_pks,
            foreign_keys=all_fks,
            unique_constraints=all_unique,
            indexes=all_indexes,
        )

    def get_database_metadata(self) -> DatabaseMetadata:
        """
        Obtiene metadata completa de la base de datos (todos los schemas).

        Returns:
            DatabaseMetadata con todos los schemas y sus tablas
        """
        database_name = (
            self.connection_config.get("service_name")
            or self.connection_config.get("sid")
            or self.connection_config["database"]
        )
        schemas_list = self.get_schemas()

        schemas_metadata = []
        for schema_name in schemas_list:
            schema_metadata = self.get_schema_metadata(schema_name)
            schemas_metadata.append(schema_metadata)

        return DatabaseMetadata(
            name=database_name,
            dialect="oracle",
            schemas=schemas_metadata,
        )
