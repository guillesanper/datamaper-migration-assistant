"""
MySQL Database Adapter

Implementación del adapter para MySQL/MariaDB con queries de introspección de metadata.

SEGURIDAD: Solo queries a information_schema (metadata).
NO ejecuta queries sobre datos de usuario.
"""

import logging
from typing import Any, Dict, List, Optional

import pymysql  # type: ignore[import-untyped]
import pymysql.connections  # type: ignore[import-untyped]
import pymysql.cursors  # type: ignore[import-untyped]
from pymysql import InternalError, OperationalError, ProgrammingError
from pymysql.constants import CLIENT  # type: ignore[import-untyped]

from app.models.db_metadata import (
    ColumnMetadata,
    DataType,
    ForeignKeyMetadata,
    IndexMetadata,
    IndexType,
    PrimaryKeyMetadata,
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
    DBTLSError,
)
from .tls import build_ssl_context, is_tls_error
from .type_mappers import MySQLTypeMapper
from .validators import validate_schema_name, validate_table_name

logger = logging.getLogger(__name__)

# Código de error de cliente de MySQL para fallos TLS/SSL (CR_SSL_CONNECTION_ERROR)
_CR_SSL_CONNECTION_ERROR = 2026


class _TLSRequiredConnection(pymysql.connections.Connection):
    """
    Conexión PyMySQL que nunca se degrada a texto plano.

    PyMySQL 1.1.0 solo negocia TLS si el servidor lo anuncia en su saludo inicial; si no,
    sigue adelante sin cifrar y envía la autenticación. Un servidor sin TLS (o un
    intermediario que oculte esa capacidad) obtendría así la sesión sin cifrar. Aquí se
    aborta antes de autenticar.
    """

    def _request_authentication(self):
        if self.ssl and not self.server_capabilities & CLIENT.SSL:
            raise OperationalError(
                _CR_SSL_CONNECTION_ERROR, "TLS/SSL error: the server does not support TLS"
            )
        super()._request_authentication()


class MySQLAdapter(BaseDBAdapter):
    """
    Adapter para MySQL 8.0+ / MariaDB 10.5+.

    Requisitos:
    - Usuario con permisos de lectura en information_schema
    - Usuario con permiso SHOW DATABASES
    - NO requiere permisos en tablas de usuario

    Ver docs/PLAN_FASE_2_CONEXION_LOCAL.md para crear usuario read-only.
    """

    @property
    def dialect(self) -> str:
        return "mysql"

    # =============================================================================
    # CONNECTION MANAGEMENT
    # =============================================================================

    def connect(self) -> None:
        """Establece conexión con MySQL"""
        try:
            self.connection = _TLSRequiredConnection(
                host=self.connection_config["host"],
                port=self.connection_config["port"],
                database=self.connection_config["database"],
                user=self.connection_config["user"],
                password=self.connection_config["password"],
                connect_timeout=self.timeout,
                # Usar DictCursor para retornar rows como dicts
                cursorclass=pymysql.cursors.DictCursor,
                charset="utf8mb4",
                # SSLContext: PyMySQL activa TLS y verifica según el contexto (CA en memoria)
                ssl=build_ssl_context(self.tls),
            )
            self._is_connected = True
            logger.info(
                f"Connected to MySQL: {self.connection_config['database']}@{self.connection_config['host']}"
            )

        except OperationalError as e:
            error_msg = str(e).lower()
            if "access denied" in error_msg or "authentication" in error_msg:
                raise DBAuthenticationError(f"Authentication failed for MySQL: {str(e)}")
            if is_tls_error(str(e)):
                raise DBTLSError(f"TLS error connecting to MySQL: {str(e)}")
            raise DBConnectionError(f"Cannot connect to MySQL: {str(e)}")
        except Exception as e:
            raise DBConnectionError(f"Unexpected error connecting to MySQL: {str(e)}")

    def disconnect(self) -> None:
        """Cierra conexión"""
        if self.connection:
            try:
                self.connection.close()
                self._is_connected = False
                logger.info("Disconnected from MySQL")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")

    def test_connection(self) -> bool:
        """Valida credenciales sin mantener conexión"""
        try:
            self.connect()
            # Test simple query
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            self.disconnect()
            return True
        except (DBAuthenticationError, DBConnectionError):
            raise

    # =============================================================================
    # METADATA INTROSPECTION
    # =============================================================================

    def get_schemas(self) -> List[str]:
        """
        Lista todos los schemas/databases (excepto system databases).

        En MySQL, schema = database.
        """
        query = """
            SELECT SCHEMA_NAME
            FROM information_schema.SCHEMATA
            WHERE SCHEMA_NAME NOT IN (
                'information_schema', 'mysql', 'performance_schema', 'sys'
            )
            ORDER BY SCHEMA_NAME
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                return [row["SCHEMA_NAME"] for row in results]
        except Exception as e:
            raise DBQueryExecutionError(f"Error getting schemas: {str(e)}")

    def get_tables(self, schema: Optional[str] = None) -> List[TableMetadata]:
        """Lista todas las tablas de un schema/database"""
        schema = schema or self._get_default_schema()
        validate_schema_name(schema)

        query = """
            SELECT
                TABLE_NAME,
                TABLE_SCHEMA,
                TABLE_TYPE
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
              AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
            ORDER BY TABLE_NAME
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (schema,))
                results = cursor.fetchall()

                tables = []
                for row in results:
                    # Mapear table_type
                    if row["TABLE_TYPE"] == "BASE TABLE":
                        table_type = TableType.BASE_TABLE
                    elif row["TABLE_TYPE"] == "VIEW":
                        table_type = TableType.VIEW
                    else:
                        table_type = TableType.BASE_TABLE

                    tables.append(
                        TableMetadata(
                            name=row["TABLE_NAME"],
                            schema=row["TABLE_SCHEMA"],
                            table_type=table_type,
                            columns=[],  # Se llenan con get_columns()
                        )
                    )

                return tables

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting tables: {str(e)}")

    def get_columns(self, table_name: str, schema: Optional[str] = None) -> List[ColumnMetadata]:
        """Lista todas las columnas de una tabla"""
        schema = schema or self._get_default_schema()
        validate_table_name(table_name)
        validate_schema_name(schema)

        query = """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                COLUMN_TYPE,
                IS_NULLABLE,
                COLUMN_DEFAULT,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE,
                ORDINAL_POSITION,
                EXTRA
            FROM information_schema.COLUMNS
            WHERE TABLE_NAME = %s
              AND TABLE_SCHEMA = %s
            ORDER BY ORDINAL_POSITION
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (table_name, schema))
                results = cursor.fetchall()

                if not results:
                    raise DBMetadataNotFoundError(
                        f"Table '{schema}.{table_name}' not found or has no columns"
                    )

                columns = []
                for row in results:
                    # Usar COLUMN_TYPE para detectar TINYINT(1) como boolean
                    column_type = row["COLUMN_TYPE"]

                    # Mapear a tipo genérico
                    generic_type = MySQLTypeMapper.map_to_generic(column_type)

                    # Detectar auto-increment
                    is_auto_increment = (
                        "auto_increment" in row["EXTRA"].lower() if row["EXTRA"] else False
                    )

                    # Extraer valores ENUM si aplica
                    enum_values = None
                    if row["DATA_TYPE"].upper() == "ENUM":
                        # COLUMN_TYPE tiene formato: enum('value1','value2','value3')
                        import re

                        match = re.search(r"enum\((.*?)\)", column_type, re.IGNORECASE)
                        if match:
                            # Extraer valores entre comillas
                            enum_str = match.group(1)
                            enum_values = [v.strip("'") for v in re.findall(r"'([^']*)'", enum_str)]

                    columns.append(
                        ColumnMetadata(
                            name=row["COLUMN_NAME"],
                            data_type=generic_type,
                            native_type=row["DATA_TYPE"].upper(),
                            is_nullable=(row["IS_NULLABLE"] == "YES"),
                            is_auto_increment=is_auto_increment,
                            default_value=row["COLUMN_DEFAULT"],
                            max_length=row["CHARACTER_MAXIMUM_LENGTH"],
                            numeric_precision=row["NUMERIC_PRECISION"],
                            numeric_scale=row["NUMERIC_SCALE"],
                            ordinal_position=row["ORDINAL_POSITION"],
                            enum_values=enum_values,
                        )
                    )

                # Marcar columnas que son PK o FK
                columns = self._mark_key_columns(columns, table_name, schema)

                return columns

        except DBMetadataNotFoundError:
            raise
        except Exception as e:
            raise DBQueryExecutionError(f"Error getting columns: {str(e)}")

    def _mark_key_columns(
        self, columns: List[ColumnMetadata], table_name: str, schema: str
    ) -> List[ColumnMetadata]:
        """
        Marca columnas que son PK o FK.
        Returns a new list with updated column metadata.
        """
        # Obtener PKs
        pks = self.get_primary_keys(table_name, schema)
        pk_columns = set()
        for pk in pks:
            pk_columns.update(pk.columns)

        # Obtener FKs
        fks = self.get_foreign_keys(table_name, schema)
        fk_columns = set()
        for fk in fks:
            fk_columns.update(fk.columns)

        # Crear nuevas instancias con flags actualizados
        updated_columns = []
        for col in columns:
            if col.name in pk_columns or col.name in fk_columns:
                # Need to update - create new instance with updated fields
                col_dict = col.model_dump()
                if col.name in pk_columns:
                    col_dict["is_primary_key"] = True
                if col.name in fk_columns:
                    col_dict["is_foreign_key"] = True
                updated_columns.append(ColumnMetadata(**col_dict))
            else:
                # No changes needed
                updated_columns.append(col)

        return updated_columns

    def get_primary_keys(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[PrimaryKeyMetadata]:
        """Obtiene las primary keys de una tabla"""
        schema = schema or self._get_default_schema()
        validate_table_name(table_name)
        validate_schema_name(schema)

        query = """
            SELECT
                CONSTRAINT_NAME,
                COLUMN_NAME,
                ORDINAL_POSITION
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_NAME = %s
              AND TABLE_SCHEMA = %s
              AND CONSTRAINT_NAME = 'PRIMARY'
            ORDER BY ORDINAL_POSITION
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (table_name, schema))
                results = cursor.fetchall()

                if not results:
                    return []

                # Agrupar columnas por constraint_name (aunque PRIMARY es único)
                pk_dict: Dict[str, List[str]] = {}
                for row in results:
                    constraint_name = row["CONSTRAINT_NAME"]
                    if constraint_name not in pk_dict:
                        pk_dict[constraint_name] = []
                    pk_dict[constraint_name].append(row["COLUMN_NAME"])

                # Crear objetos PrimaryKeyMetadata
                primary_keys = []
                for constraint_name, columns in pk_dict.items():
                    primary_keys.append(
                        PrimaryKeyMetadata(
                            constraint_name=constraint_name,
                            column_names=columns,
                            table_name=table_name,
                            schema=schema,
                        )
                    )

                return primary_keys

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting primary keys: {str(e)}")

    def get_foreign_keys(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[ForeignKeyMetadata]:
        """Obtiene las foreign keys de una tabla"""
        schema = schema or self._get_default_schema()
        validate_table_name(table_name)
        validate_schema_name(schema)

        query = """
            SELECT
                kcu.CONSTRAINT_NAME,
                kcu.COLUMN_NAME,
                kcu.REFERENCED_TABLE_SCHEMA,
                kcu.REFERENCED_TABLE_NAME,
                kcu.REFERENCED_COLUMN_NAME,
                rc.UPDATE_RULE,
                rc.DELETE_RULE,
                kcu.ORDINAL_POSITION
            FROM information_schema.KEY_COLUMN_USAGE kcu
            JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
                ON kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
                AND kcu.TABLE_SCHEMA = rc.CONSTRAINT_SCHEMA
            WHERE kcu.TABLE_NAME = %s
              AND kcu.TABLE_SCHEMA = %s
              AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
            ORDER BY kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (table_name, schema))
                results = cursor.fetchall()

                if not results:
                    return []

                # Agrupar por constraint_name
                fk_dict = {}
                for row in results:
                    constraint_name = row["CONSTRAINT_NAME"]
                    if constraint_name not in fk_dict:
                        fk_dict[constraint_name] = {
                            "columns": [],
                            "referenced_schema": row["REFERENCED_TABLE_SCHEMA"],
                            "referenced_table": row["REFERENCED_TABLE_NAME"],
                            "referenced_columns": [],
                            "on_update": row["UPDATE_RULE"],
                            "on_delete": row["DELETE_RULE"],
                        }
                    fk_dict[constraint_name]["columns"].append(row["COLUMN_NAME"])
                    fk_dict[constraint_name]["referenced_columns"].append(
                        row["REFERENCED_COLUMN_NAME"]
                    )

                # Crear objetos ForeignKeyMetadata
                foreign_keys = []
                for constraint_name, fk_data in fk_dict.items():
                    foreign_keys.append(
                        ForeignKeyMetadata(
                            constraint_name=constraint_name,
                            column_names=fk_data["columns"],
                            referenced_table=fk_data["referenced_table"],
                            referenced_schema=fk_data["referenced_schema"],
                            referenced_columns=fk_data["referenced_columns"],
                            on_delete=fk_data["on_delete"],
                            on_update=fk_data["on_update"],
                            table_name=table_name,
                            schema=schema,
                        )
                    )

                return foreign_keys

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting foreign keys: {str(e)}")

    def get_indexes(self, table_name: str, schema: Optional[str] = None) -> List[IndexMetadata]:
        """Obtiene los índices de una tabla"""
        schema = schema or self._get_default_schema()
        validate_table_name(table_name)
        validate_schema_name(schema)

        query = """
            SELECT
                INDEX_NAME,
                COLUMN_NAME,
                NON_UNIQUE,
                INDEX_TYPE,
                SEQ_IN_INDEX
            FROM information_schema.STATISTICS
            WHERE TABLE_NAME = %s
              AND TABLE_SCHEMA = %s
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (table_name, schema))
                results = cursor.fetchall()

                if not results:
                    return []

                # Agrupar por index_name
                idx_dict = {}
                for row in results:
                    index_name = row["INDEX_NAME"]
                    if index_name not in idx_dict:
                        # Mapear tipo de índice
                        index_type_str = row["INDEX_TYPE"].upper()
                        if index_type_str == "BTREE":
                            index_type = IndexType.BTREE
                        elif index_type_str == "HASH":
                            index_type = IndexType.HASH
                        elif index_type_str == "FULLTEXT":
                            index_type = IndexType.FULLTEXT
                        elif index_type_str == "SPATIAL":
                            index_type = IndexType.SPATIAL
                        else:
                            index_type = IndexType.UNKNOWN

                        idx_dict[index_name] = {
                            "columns": [],
                            "is_unique": (row["NON_UNIQUE"] == 0),
                            "is_primary": (index_name == "PRIMARY"),
                            "index_type": index_type,
                        }
                    idx_dict[index_name]["columns"].append(row["COLUMN_NAME"])

                # Crear objetos IndexMetadata
                indexes = []
                for index_name, idx_data in idx_dict.items():
                    indexes.append(
                        IndexMetadata(
                            name=index_name,
                            columns=idx_data["columns"],
                            table_name=table_name,
                            schema=schema,
                            is_unique=idx_data["is_unique"],
                            is_primary=idx_data["is_primary"],
                            index_type=idx_data["index_type"],
                        )
                    )

                return indexes

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting indexes: {str(e)}")

    def get_table_statistics(
        self, table_name: str, schema: Optional[str] = None
    ) -> TableStatistics:
        """
        Obtiene estadísticas de una tabla (aproximadas, NO ejecuta COUNT(*)).

        Usa information_schema.TABLES para obtener valores aproximados.
        """
        schema = schema or self._get_default_schema()
        validate_table_name(table_name)
        validate_schema_name(schema)

        query = """
            SELECT
                TABLE_NAME,
                TABLE_SCHEMA,
                TABLE_ROWS,
                DATA_LENGTH,
                INDEX_LENGTH,
                CREATE_TIME,
                UPDATE_TIME
            FROM information_schema.TABLES
            WHERE TABLE_NAME = %s
              AND TABLE_SCHEMA = %s
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (table_name, schema))
                result = cursor.fetchone()

                if not result:
                    # Tabla existe pero no tiene estadísticas aún
                    return TableStatistics(
                        table_name=table_name,
                        schema=schema,
                        row_count=0,
                        size_bytes=0,
                    )

                # Calcular tamaño total
                total_size = (result["DATA_LENGTH"] or 0) + (result["INDEX_LENGTH"] or 0)

                return TableStatistics(
                    table_name=table_name,
                    schema=schema,
                    row_count=result["TABLE_ROWS"] or 0,  # Aproximado
                    size_bytes=total_size,
                    last_modified=result["UPDATE_TIME"],
                )

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting table statistics: {str(e)}")

    def _get_default_schema(self) -> str:
        """Retorna el database especificado en la configuración"""
        return str(self.connection_config["database"])

    def list_tables(self, schema: Optional[str] = None) -> List[TableMetadata]:
        """Alias for get_tables() - used by tests"""
        return self.get_tables(schema)

    def get_table_columns(self, schema: str, table_name: str) -> List[ColumnMetadata]:
        """
        Alias for get_columns() with swapped parameter order.
        Used by tests which call get_table_columns(schema, table).
        """
        return self.get_columns(table_name, schema)

    def get_database_metadata(self):
        """
        Obtiene metadata completa de la base de datos.

        Returns:
            DatabaseMetadata con schemas, tablas, columnas, constraints, etc.
        """
        from app.models.db_metadata.schema import DatabaseMetadata, SchemaMetadata

        # Get all schemas
        schema_list = self.get_schemas()

        # Build SchemaMetadata for each schema
        schemas_metadata = []
        for schema_name in schema_list:
            tables = self.get_tables(schema_name)

            # Get constraints and indexes for each table
            for table in tables:
                # Note: Primary keys and foreign keys are already marked in columns
                # via _mark_key_columns in get_columns
                pass

            schemas_metadata.append(
                SchemaMetadata(
                    name=schema_name,
                    tables=tables,
                    primary_keys=[],  # Would need to aggregate from all tables
                    foreign_keys=[],  # Would need to aggregate from all tables
                    unique_constraints=[],
                    indexes=[],
                )
            )

        # Get version
        version = None
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT VERSION()")
                result = cursor.fetchone()
                if result:
                    version = result["VERSION()"]
        except Exception:
            pass

        return DatabaseMetadata(
            name=self.connection_config["database"],
            dialect="mysql",
            version=version,
            schemas=schemas_metadata,
            connection_info={
                "host": self.connection_config["host"],
                "port": str(self.connection_config["port"]),
                "database": self.connection_config["database"],
            },
        )
