"""
SQL Server Database Adapter

Implementación del adapter para Microsoft SQL Server con queries de introspección de metadata.

SEGURIDAD: Solo queries a INFORMATION_SCHEMA y sys views (metadata).
NO ejecuta queries sobre datos de usuario.

Requiere:
- pyodbc>=5.1.0
- ODBC Driver 18 for SQL Server instalado en el sistema
"""

import logging
import re
import types
from typing import Any, Dict, List, Optional

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
    DBValidationError,
)
from .tls import is_tls_error
from .type_mappers import SQLServerTypeMapper
from .validators import validate_metadata_name

logger = logging.getLogger(__name__)

# Valores que no necesitan llaves en una cadena de conexión ODBC
_ODBC_PLAIN_VALUE = re.compile(r"[A-Za-z0-9_.\-]+")


def _odbc_value(value: str) -> str:
    """
    Escapa un valor para una cadena de conexión ODBC.

    Los valores con caracteres especiales (';', '=', '{', '}', espacios...) van entre llaves
    y '}' se duplica, de modo que no puedan añadir ni sobrescribir atributos del driver.
    """
    if _ODBC_PLAIN_VALUE.fullmatch(value):
        return value
    return "{" + value.replace("}", "}}") + "}"


def _missing_pyodbc(import_error: ImportError) -> types.SimpleNamespace:
    """
    Sustituto de pyodbc cuando no está instalado (o falta unixODBC).

    Permite importar el resto de adapters y la app; solo falla al conectar a SQL Server.
    """

    class Error(Exception):
        pass

    def connect(*args: Any, **kwargs: Any) -> None:
        raise Error(
            "SQL Server no disponible: pyodbc o el driver ODBC no están instalados "
            f"({import_error})"
        )

    return types.SimpleNamespace(Error=Error, connect=connect)


try:
    import pyodbc
except ImportError as e:  # pyodbc ausente o libodbc.so no encontrada
    logger.warning("pyodbc no disponible, SQL Server desactivado: %s", e)
    pyodbc = _missing_pyodbc(e)


class SQLServerAdapter(BaseDBAdapter):
    """
    Adapter para Microsoft SQL Server 2016+.

    Requisitos:
    - Usuario con permisos VIEW DEFINITION en la base de datos
    - Usuario con permisos SELECT en sys.* views
    - ODBC Driver 18 for SQL Server instalado

    Casos especiales:
    - UNIQUEIDENTIFIER → UUID
    - NVARCHAR/NCHAR → VARCHAR/CHAR (Unicode strings)
    - BIT → BOOLEAN
    - DATETIME2 → TIMESTAMP
    """

    def __init__(self, connection_config: Dict[str, Any]):
        super().__init__(connection_config)
        # ODBC Driver 18 solo confía en el almacén del sistema: ignorar la CA en silencio
        # haría creer que se verifica contra ella
        if self.tls.ca_pem:
            raise DBValidationError(
                "A custom CA is not supported for SQL Server: ODBC Driver 18 only uses the "
                "system trust store. Install the CA in the system store"
            )

    @property
    def dialect(self) -> str:
        return "sqlserver"

    # =============================================================================
    # CONNECTION MANAGEMENT
    # =============================================================================

    def connect(self) -> None:
        """Establece conexión con SQL Server usando pyodbc"""
        try:
            # Build connection string
            driver = "{ODBC Driver 18 for SQL Server}"
            server = self.connection_config["host"]
            port = self.connection_config.get("port", 1433)
            database = self.connection_config["database"]
            username = self.connection_config["user"]
            password = self.connection_config["password"]

            # server ya viene validado como hostname/IP (validate_host); el resto se escapa
            connection_string = (
                f"DRIVER={driver};"
                f"SERVER={server},{port};"
                f"DATABASE={_odbc_value(database)};"
                f"UID={_odbc_value(username)};"
                f"PWD={_odbc_value(password)};"
                f"{self._tls_attributes()}"
                f"Connection Timeout={self.timeout};"
            )

            self.connection = pyodbc.connect(connection_string)
            self._is_connected = True
            logger.info(f"Connected to SQL Server: {database}@{server}")

        except pyodbc.Error as e:
            error_msg = str(e)

            # Check for authentication errors
            if "18456" in error_msg or "login failed" in error_msg.lower():
                raise DBAuthenticationError(f"Invalid credentials for SQL Server: {error_msg}")

            # El driver encadena el fallo de certificado con un "Login timeout expired":
            # hay que mirar TLS antes que el timeout
            if is_tls_error(error_msg):
                raise DBTLSError(f"TLS error connecting to SQL Server: {error_msg}")

            # Check for timeout
            if "timeout" in error_msg.lower():
                raise DBTimeoutError(f"Connection timeout to SQL Server: {error_msg}")

            raise DBConnectionError(f"Cannot connect to SQL Server: {error_msg}")

        except Exception as e:
            raise DBConnectionError(f"Unexpected error connecting to SQL Server: {str(e)}")

    def _tls_attributes(self) -> str:
        """
        Atributos TLS de la cadena de conexión ODBC.

        Se cifra siempre. Por defecto se valida el certificado y su hostname; el opt-out
        (tls_verify=False) solo salta esa validación.
        """
        trust_certificate = "no" if self.tls.verify else "yes"
        return f"Encrypt=yes;TrustServerCertificate={trust_certificate};"

    def disconnect(self) -> None:
        """Cierra conexión"""
        if self.connection:
            try:
                self.connection.close()
                self._is_connected = False
                logger.info("Disconnected from SQL Server")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")

    def test_connection(self) -> bool:
        """Valida credenciales sin mantener conexión"""
        try:
            self.connect()
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1 AS test")
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
        """Retorna el nombre del schema por defecto ('dbo' típicamente)"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT SCHEMA_NAME()")
            schema = cursor.fetchone()[0]
            cursor.close()
            return str(schema)
        except Exception as e:
            logger.error(f"Failed to get default schema: {e}")
            return "dbo"

    def get_schemas(self) -> List[str]:
        """
        Lista todos los schemas en la base de datos.

        Filtra schemas del sistema: sys, INFORMATION_SCHEMA
        """
        query = """
        SELECT SCHEMA_NAME
        FROM INFORMATION_SCHEMA.SCHEMATA
        WHERE SCHEMA_NAME NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest', 'db_owner',
                                   'db_accessadmin', 'db_securityadmin', 'db_ddladmin',
                                   'db_backupoperator', 'db_datareader', 'db_datawriter',
                                   'db_denydatareader', 'db_denydatawriter')
        ORDER BY SCHEMA_NAME
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            schemas = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return schemas

        except pyodbc.Error as e:
            raise DBQueryExecutionError(f"Failed to list schemas: {str(e)}")

    def get_tables(self, schema: Optional[str] = None) -> List[TableMetadata]:
        """
        Lista todas las tablas en un schema.

        Args:
            schema: Nombre del schema. Si es None, usa el schema por defecto.

        Returns:
            Lista de TableMetadata
        """
        if schema is None:
            schema = self._get_default_schema()

        schema_name = schema
        validate_metadata_name(schema_name, "Schema name")

        query = """
        SELECT
            t.TABLE_SCHEMA,
            t.TABLE_NAME,
            t.TABLE_TYPE,
            CAST(p.rows AS BIGINT) AS row_count
        FROM INFORMATION_SCHEMA.TABLES t
        LEFT JOIN sys.tables st ON t.TABLE_NAME = st.name AND SCHEMA_NAME(st.schema_id) = t.TABLE_SCHEMA
        LEFT JOIN sys.partitions p ON st.object_id = p.object_id AND p.index_id IN (0, 1)
        WHERE t.TABLE_SCHEMA = ?
          AND t.TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        ORDER BY t.TABLE_NAME
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (schema_name,))
            rows = cursor.fetchall()
            cursor.close()

            tables = []
            for row in rows:
                tables.append(
                    TableMetadata(
                        name=row[1],
                        schema=row[0],
                        table_type=(TableType.VIEW if row[2] == "VIEW" else TableType.BASE_TABLE),
                    )
                )

            return tables

        except pyodbc.Error as e:
            raise DBQueryExecutionError(
                f"Failed to list tables in schema '{schema_name}': {str(e)}"
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
        validate_metadata_name(schema_name, "Schema name")
        validate_metadata_name(table_name, "Table name")

        query = """
        SELECT
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.CHARACTER_MAXIMUM_LENGTH,
            c.NUMERIC_PRECISION,
            c.NUMERIC_SCALE,
            c.IS_NULLABLE,
            c.COLUMN_DEFAULT,
            c.ORDINAL_POSITION,
            -- Check if column is primary key
            CASE WHEN pk.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END AS is_primary_key,
            -- Check if column is identity (auto-increment)
            -- QUOTENAME: sin citar, OBJECT_ID fallaba con nombres con espacios, puntos, etc.
            COLUMNPROPERTY(
                OBJECT_ID(QUOTENAME(c.TABLE_SCHEMA) + '.' + QUOTENAME(c.TABLE_NAME)),
                c.COLUMN_NAME, 'IsIdentity'
            ) AS is_identity
        FROM INFORMATION_SCHEMA.COLUMNS c
        LEFT JOIN (
            SELECT ku.TABLE_SCHEMA, ku.TABLE_NAME, ku.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
                ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
                AND tc.TABLE_SCHEMA = ku.TABLE_SCHEMA
                AND tc.TABLE_NAME = ku.TABLE_NAME
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        ) pk ON c.TABLE_SCHEMA = pk.TABLE_SCHEMA
            AND c.TABLE_NAME = pk.TABLE_NAME
            AND c.COLUMN_NAME = pk.COLUMN_NAME
        WHERE c.TABLE_SCHEMA = ?
          AND c.TABLE_NAME = ?
        ORDER BY c.ORDINAL_POSITION
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (schema_name, table_name))
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                raise DBMetadataNotFoundError(
                    f"Table '{schema_name}.{table_name}' not found or has no columns"
                )

            type_mapper = SQLServerTypeMapper()
            columns = []

            for row in rows:
                column_name = row[0]
                sql_type = row[1]
                max_length = row[2]
                precision = row[3]
                scale = row[4]
                is_nullable = row[5] == "YES"
                default_value = row[6]
                position = row[7]
                is_pk = row[8] == 1
                is_identity = row[9] == 1

                # Map SQL Server type to DataType enum
                data_type = type_mapper.map_to_standard(sql_type)

                columns.append(
                    ColumnMetadata(
                        name=column_name,
                        data_type=data_type,
                        is_nullable=is_nullable,
                        max_length=max_length,
                        numeric_precision=precision,
                        numeric_scale=scale,
                        default_value=default_value,
                        is_primary_key=is_pk,
                        is_auto_increment=is_identity,
                        ordinal_position=position,
                        native_type=sql_type,
                    )
                )

            return columns

        except pyodbc.Error as e:
            raise DBQueryExecutionError(
                f"Failed to get columns for '{schema_name}.{table_name}': {str(e)}"
            )

    def get_primary_keys(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[PrimaryKeyMetadata]:
        """
        Obtiene claves primarias de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema. Si es None, usa el schema por defecto.

        Returns:
            Lista de PrimaryKeyMetadata (usualmente 1 elemento)
        """
        schema_name = schema or self._get_default_schema()
        validate_metadata_name(schema_name, "Schema name")
        validate_metadata_name(table_name, "Table name")

        query = """
        SELECT
            tc.CONSTRAINT_NAME,
            ku.COLUMN_NAME,
            ku.ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
            ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
            AND tc.TABLE_SCHEMA = ku.TABLE_SCHEMA
            AND tc.TABLE_NAME = ku.TABLE_NAME
        WHERE tc.TABLE_SCHEMA = ?
          AND tc.TABLE_NAME = ?
          AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        ORDER BY ku.ORDINAL_POSITION
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (schema_name, table_name))
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
                        table_name=table_name,
                        schema=schema_name,
                        column_names=columns,
                    )
                )

            return pks

        except pyodbc.Error as e:
            raise DBQueryExecutionError(
                f"Failed to get primary keys for '{schema_name}.{table_name}': {str(e)}"
            )

    def get_foreign_keys(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[ForeignKeyMetadata]:
        """
        Obtiene claves foráneas de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema. Si es None, usa el schema por defecto.

        Returns:
            Lista de ForeignKeyMetadata
        """
        schema_name = schema or self._get_default_schema()
        validate_metadata_name(schema_name, "Schema name")
        validate_metadata_name(table_name, "Table name")

        query = """
        SELECT
            fk.name AS constraint_name,
            SCHEMA_NAME(t.schema_id) AS schema_name,
            t.name AS table_name,
            c.name AS column_name,
            SCHEMA_NAME(rt.schema_id) AS referenced_schema,
            rt.name AS referenced_table,
            rc.name AS referenced_column,
            fk.delete_referential_action_desc,
            fk.update_referential_action_desc
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
        JOIN sys.tables t ON fk.parent_object_id = t.object_id
        JOIN sys.columns c ON fkc.parent_object_id = c.object_id AND fkc.parent_column_id = c.column_id
        JOIN sys.tables rt ON fk.referenced_object_id = rt.object_id
        JOIN sys.columns rc ON fkc.referenced_object_id = rc.object_id AND fkc.referenced_column_id = rc.column_id
        WHERE SCHEMA_NAME(t.schema_id) = ?
          AND t.name = ?
        ORDER BY fk.name, fkc.constraint_column_id
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (schema_name, table_name))
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                return []

            # Group by constraint name
            fk_dict = {}
            for row in rows:
                constraint_name = row[0]
                column_name = row[3]
                referenced_schema = row[4]
                referenced_table = row[5]
                referenced_column = row[6]
                on_delete = row[7]
                on_update = row[8]

                if constraint_name not in fk_dict:
                    fk_dict[constraint_name] = {
                        "columns": [],
                        "referenced_schema": referenced_schema,
                        "referenced_table": referenced_table,
                        "referenced_columns": [],
                        "on_delete": on_delete,
                        "on_update": on_update,
                    }

                fk_dict[constraint_name]["columns"].append(column_name)
                fk_dict[constraint_name]["referenced_columns"].append(referenced_column)

            # Convert to ForeignKeyMetadata
            fks = []
            for constraint_name, data in fk_dict.items():
                fks.append(
                    ForeignKeyMetadata(
                        constraint_name=constraint_name,
                        table_name=table_name,
                        schema=schema_name,
                        column_names=data["columns"],
                        referenced_table=data["referenced_table"],
                        referenced_columns=data["referenced_columns"],
                        on_delete=data["on_delete"],
                        on_update=data["on_update"],
                    )
                )

            return fks

        except pyodbc.Error as e:
            raise DBQueryExecutionError(
                f"Failed to get foreign keys for '{schema_name}.{table_name}': {str(e)}"
            )

    def get_unique_constraints(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[UniqueConstraintMetadata]:
        """
        Obtiene constraints de unicidad de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema. Si es None, usa el schema por defecto.

        Returns:
            Lista de UniqueConstraintMetadata
        """
        schema_name = schema or self._get_default_schema()
        validate_metadata_name(schema_name, "Schema name")
        validate_metadata_name(table_name, "Table name")

        query = """
        SELECT
            tc.CONSTRAINT_NAME,
            ku.COLUMN_NAME,
            ku.ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ku
            ON tc.CONSTRAINT_NAME = ku.CONSTRAINT_NAME
            AND tc.TABLE_SCHEMA = ku.TABLE_SCHEMA
            AND tc.TABLE_NAME = ku.TABLE_NAME
        WHERE tc.TABLE_SCHEMA = ?
          AND tc.TABLE_NAME = ?
          AND tc.CONSTRAINT_TYPE = 'UNIQUE'
        ORDER BY tc.CONSTRAINT_NAME, ku.ORDINAL_POSITION
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (schema_name, table_name))
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
                        table_name=table_name,
                        schema=schema_name,
                        column_names=columns,
                    )
                )

            return uniques

        except pyodbc.Error as e:
            raise DBQueryExecutionError(
                f"Failed to get unique constraints for '{schema_name}.{table_name}': {str(e)}"
            )

    def get_check_constraints(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[CheckConstraintMetadata]:
        """
        Obtiene check constraints de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema. Si es None, usa el schema por defecto.

        Returns:
            Lista de CheckConstraintMetadata
        """
        schema_name = schema or self._get_default_schema()
        validate_metadata_name(schema_name, "Schema name")
        validate_metadata_name(table_name, "Table name")

        query = """
        SELECT
            cc.CONSTRAINT_NAME,
            cc.CHECK_CLAUSE
        FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
        JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            ON cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
            AND cc.CONSTRAINT_SCHEMA = tc.TABLE_SCHEMA
        WHERE tc.TABLE_SCHEMA = ?
          AND tc.TABLE_NAME = ?
        ORDER BY cc.CONSTRAINT_NAME
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (schema_name, table_name))
            rows = cursor.fetchall()
            cursor.close()

            checks = []
            for row in rows:
                checks.append(
                    CheckConstraintMetadata(
                        constraint_name=row[0],
                        table_name=table_name,
                        schema=schema_name,
                        check_clause=row[1],
                    )
                )

            return checks

        except pyodbc.Error as e:
            raise DBQueryExecutionError(
                f"Failed to get check constraints for '{schema_name}.{table_name}': {str(e)}"
            )

    def get_indexes(self, table_name: str, schema: Optional[str] = None) -> List[IndexMetadata]:
        """
        Obtiene índices de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema. Si es None, usa el schema por defecto.

        Returns:
            Lista de IndexMetadata
        """
        schema_name = schema or self._get_default_schema()
        validate_metadata_name(schema_name, "Schema name")
        validate_metadata_name(table_name, "Table name")

        query = """
        SELECT
            i.name AS index_name,
            i.is_unique,
            i.is_primary_key,
            c.name AS column_name,
            ic.key_ordinal
        FROM sys.indexes i
        JOIN sys.tables t ON i.object_id = t.object_id
        JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
        JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE SCHEMA_NAME(t.schema_id) = ?
          AND t.name = ?
          AND i.is_hypothetical = 0
          AND i.type > 0
        ORDER BY i.name, ic.key_ordinal
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (schema_name, table_name))
            rows = cursor.fetchall()
            cursor.close()

            if not rows:
                return []

            # Group by index name
            index_dict = {}
            for row in rows:
                index_name = row[0]
                is_unique = row[1]
                is_primary = row[2]
                column_name = row[3]

                if index_name not in index_dict:
                    index_dict[index_name] = {
                        "is_unique": is_unique,
                        "is_primary": is_primary,
                        "columns": [],
                    }

                index_dict[index_name]["columns"].append(column_name)

            # Convert to IndexMetadata
            indexes = []
            for index_name, data in index_dict.items():
                # Skip primary key indexes (already captured in PK metadata)
                if data["is_primary"]:
                    continue

                # Use BTREE as default type (unique is determined by is_unique flag)
                index_type = IndexType.BTREE

                indexes.append(
                    IndexMetadata(
                        name=index_name,
                        table_name=table_name,
                        schema=schema_name,
                        columns=data["columns"],
                        is_unique=data["is_unique"],
                        index_type=index_type,
                    )
                )

            return indexes

        except pyodbc.Error as e:
            raise DBQueryExecutionError(
                f"Failed to get indexes for '{schema_name}.{table_name}': {str(e)}"
            )

    def get_table_statistics(
        self, table_name: str, schema: Optional[str] = None
    ) -> TableStatistics:
        """
        Obtiene estadísticas de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema. Si es None, usa el schema por defecto.

        Returns:
            TableStatistics con row count y tamaño
        """
        schema_name = schema or self._get_default_schema()
        validate_metadata_name(schema_name, "Schema name")
        validate_metadata_name(table_name, "Table name")

        query = """
        SELECT
            SUM(p.rows) AS row_count,
            SUM(a.total_pages) * 8 * 1024 AS total_size_bytes,
            SUM(a.used_pages) * 8 * 1024 AS data_size_bytes
        FROM sys.tables t
        JOIN sys.indexes i ON t.object_id = i.object_id
        JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
        JOIN sys.allocation_units a ON p.partition_id = a.container_id
        WHERE SCHEMA_NAME(t.schema_id) = ?
          AND t.name = ?
          AND i.index_id IN (0, 1)
        GROUP BY t.name
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (schema_name, table_name))
            row = cursor.fetchone()
            cursor.close()

            if not row:
                return TableStatistics(
                    table_name=table_name,
                    schema=schema_name,
                    row_count=0,
                    size_bytes=0,
                )

            return TableStatistics(
                table_name=table_name,
                schema=schema_name,
                row_count=row[0] if row[0] else 0,
                size_bytes=row[1] if row[1] else 0,
                index_size_bytes=row[2] if row[2] else 0,
            )

        except pyodbc.Error as e:
            raise DBQueryExecutionError(
                f"Failed to get statistics for '{schema_name}.{table_name}': {str(e)}"
            )

    def get_schema_metadata(self, schema_name: str) -> SchemaMetadata:
        """Alias de get_full_schema_metadata() (tablas + columnas + constraints + índices)."""
        return self.get_full_schema_metadata(schema_name)

    def get_database_metadata(self) -> DatabaseMetadata:
        """
        Obtiene metadata completa de la base de datos (todos los schemas).

        Returns:
            DatabaseMetadata con todos los schemas y sus tablas
        """
        database_name = self.connection_config["database"]
        schemas_list = self.get_schemas()

        schemas_metadata = []
        for schema_name in schemas_list:
            schema_metadata = self.get_schema_metadata(schema_name)
            schemas_metadata.append(schema_metadata)

        return DatabaseMetadata(
            name=database_name,
            dialect="sqlserver",
            schemas=schemas_metadata,
        )
