"""
PostgreSQL Database Adapter

Implementación del adapter para PostgreSQL con queries de introspección de metadata.

SEGURIDAD: Solo queries a information_schema y pg_catalog (metadata).
NO ejecuta queries sobre datos de usuario.
"""

import logging
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from psycopg2 import InterfaceError, OperationalError, ProgrammingError
from psycopg2.errors import InvalidPassword

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
from .tls import is_tls_error, trust_file
from .type_mappers import PostgreSQLTypeMapper
from .validators import validate_schema_name, validate_table_name

logger = logging.getLogger(__name__)


class PostgreSQLAdapter(BaseDBAdapter):
    """
    Adapter para PostgreSQL 12+.

    Requisitos:
    - Usuario con permisos de lectura en information_schema
    - Usuario con permisos de lectura en pg_catalog
    - NO requiere permisos en tablas de usuario

    Ver docs/PLAN_FASE_2_CONEXION_LOCAL.md para crear usuario read-only.
    """

    @property
    def dialect(self) -> str:
        return "postgresql"

    # =============================================================================
    # CONNECTION MANAGEMENT
    # =============================================================================

    def connect(self) -> None:
        """Establece conexión con PostgreSQL"""
        try:
            # La CA propia se vuelca a un archivo temporal solo mientras dura el connect
            with trust_file(self.tls.ca_pem) as root_cert:
                self.connection = psycopg2.connect(
                    host=self.connection_config["host"],
                    port=self.connection_config["port"],
                    database=self.connection_config["database"],
                    user=self.connection_config["user"],
                    password=self.connection_config["password"],
                    connect_timeout=self.timeout,
                    # Usar RealDictCursor para retornar rows como dicts
                    cursor_factory=psycopg2.extras.RealDictCursor,
                    **self._ssl_params(root_cert),
                )
            self._is_connected = True
            logger.info(
                f"Connected to PostgreSQL: {self.connection_config['database']}@{self.connection_config['host']}"
            )

        except InvalidPassword as e:
            raise DBAuthenticationError(f"Invalid credentials for PostgreSQL: {str(e)}")
        except OperationalError as e:
            if "password authentication failed" in str(e).lower():
                raise DBAuthenticationError(f"Authentication failed: {str(e)}")
            if is_tls_error(str(e)):
                raise DBTLSError(f"TLS error connecting to PostgreSQL: {str(e)}")
            raise DBConnectionError(f"Cannot connect to PostgreSQL: {str(e)}")
        except Exception as e:
            raise DBConnectionError(f"Unexpected error connecting to PostgreSQL: {str(e)}")

    def _ssl_params(self, root_cert: str) -> Dict[str, str]:
        """
        Parámetros SSL de libpq según la política TLS de la conexión.

        verify-full comprueba certificado y hostname. El opt-out usa require (cifra sin
        verificar) y no pasa sslrootcert: con require + sslrootcert libpq verificaría la CA.
        """
        if self.tls.verify:
            return {"sslmode": "verify-full", "sslrootcert": root_cert}
        return {"sslmode": "require"}

    def disconnect(self) -> None:
        """Cierra conexión"""
        if self.connection:
            try:
                self.connection.close()
                self._is_connected = False
                logger.info("Disconnected from PostgreSQL")
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
        """Lista todos los schemas (excepto pg_* y information_schema)"""
        query = """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT LIKE 'pg_%'
              AND schema_name != 'information_schema'
            ORDER BY schema_name
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                return [row["schema_name"] for row in results]
        except Exception as e:
            raise DBQueryExecutionError(f"Error getting schemas: {str(e)}")

    def get_tables(self, schema: Optional[str] = None) -> List[TableMetadata]:
        """Lista todas las tablas de un schema"""
        schema = schema or self._get_default_schema()
        validate_schema_name(schema)

        query = """
            SELECT
                table_name,
                table_schema,
                table_type
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type IN ('BASE TABLE', 'VIEW')
            ORDER BY table_name
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (schema,))
                results = cursor.fetchall()

                tables = []
                for row in results:
                    # Mapear table_type
                    if row["table_type"] == "BASE TABLE":
                        table_type = TableType.BASE_TABLE
                    elif row["table_type"] == "VIEW":
                        table_type = TableType.VIEW
                    else:
                        table_type = TableType.BASE_TABLE

                    tables.append(
                        TableMetadata(
                            name=row["table_name"],
                            schema=row["table_schema"],
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
                column_name,
                data_type,
                udt_name,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                ordinal_position
            FROM information_schema.columns
            WHERE table_name = %s
              AND table_schema = %s
            ORDER BY ordinal_position
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
                    # Usar udt_name (tipo interno) si data_type es "USER-DEFINED"
                    native_type = (
                        row["udt_name"] if row["data_type"] == "USER-DEFINED" else row["data_type"]
                    )

                    # Mapear a tipo genérico
                    generic_type = PostgreSQLTypeMapper.map_to_generic(native_type)

                    # Detectar auto-increment (SERIAL, BIGSERIAL, IDENTITY)
                    is_auto_increment = False
                    if row["column_default"]:
                        default_lower = row["column_default"].lower()
                        is_auto_increment = (
                            "nextval(" in default_lower or "generated" in default_lower
                        )

                    columns.append(
                        ColumnMetadata(
                            name=row["column_name"],
                            data_type=generic_type,
                            native_type=native_type.upper(),
                            is_nullable=(row["is_nullable"] == "YES"),
                            is_auto_increment=is_auto_increment,
                            default_value=row["column_default"],
                            max_length=row["character_maximum_length"],
                            numeric_precision=row["numeric_precision"],
                            numeric_scale=row["numeric_scale"],
                            ordinal_position=row["ordinal_position"],
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
        # Obtener PKs - note: get_primary_keys expects (schema, table) order
        pks = self.get_primary_keys(schema, table_name)
        pk_columns = set()
        for pk in pks:
            pk_columns.update(pk.columns)

        # Obtener FKs - note: get_foreign_keys expects (schema, table) order
        fks = self.get_foreign_keys(schema, table_name)
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

    def get_primary_keys(self, schema_or_table: str, table_name: Optional[str] = None) -> List[PrimaryKeyMetadata]:  # type: ignore[override]
        """
        Obtiene las primary keys de una tabla.
        Supports both signatures: (schema, table) and (table, schema=None)
        """
        # Support both signatures: (schema, table) and (table, schema=None)
        if table_name is not None:
            # Called as (schema, table_name)
            schema = schema_or_table
            table = table_name
        else:
            # Called as (table_name, schema=None)
            table = schema_or_table
            schema = self._get_default_schema()

        validate_table_name(table)
        validate_schema_name(schema)

        query = """
            SELECT
                tc.constraint_name,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
                AND tc.table_name = kcu.table_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_name = %s
              AND tc.table_schema = %s
            ORDER BY kcu.ordinal_position
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (table, schema))
                results = cursor.fetchall()

                if not results:
                    return []

                # Agrupar columnas por constraint_name
                pk_dict: Dict[str, List[str]] = {}
                for row in results:
                    constraint_name = row["constraint_name"]
                    if constraint_name not in pk_dict:
                        pk_dict[constraint_name] = []
                    pk_dict[constraint_name].append(row["column_name"])

                # Crear objetos PrimaryKeyMetadata
                primary_keys = []
                for constraint_name, columns in pk_dict.items():
                    primary_keys.append(
                        PrimaryKeyMetadata(
                            constraint_name=constraint_name,
                            column_names=columns,
                            table_name=table,
                            schema=schema,
                        )
                    )

                return primary_keys

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting primary keys: {str(e)}")

    def get_foreign_keys(self, schema_or_table: str, table_name: Optional[str] = None) -> List[ForeignKeyMetadata]:  # type: ignore[override]
        """
        Obtiene las foreign keys de una tabla.
        Supports both signatures: (schema, table) and (table, schema=None)
        """
        # Support both signatures: (schema, table) and (table, schema=None)
        if table_name is not None:
            # Called as (schema, table_name)
            schema = schema_or_table
            table = table_name
        else:
            # Called as (table_name, schema=None)
            table = schema_or_table
            schema = self._get_default_schema()

        validate_table_name(table)
        validate_schema_name(schema)

        query = """
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_schema AS referenced_schema,
                ccu.table_name AS referenced_table,
                ccu.column_name AS referenced_column,
                rc.update_rule,
                rc.delete_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.referential_constraints rc
                ON tc.constraint_name = rc.constraint_name
                AND tc.table_schema = rc.constraint_schema
            JOIN information_schema.constraint_column_usage ccu
                ON rc.unique_constraint_name = ccu.constraint_name
                AND rc.unique_constraint_schema = ccu.constraint_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = %s
              AND tc.table_schema = %s
            ORDER BY tc.constraint_name, kcu.ordinal_position
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (table, schema))
                results = cursor.fetchall()

                if not results:
                    return []

                # Agrupar por constraint_name
                fk_dict = {}
                for row in results:
                    constraint_name = row["constraint_name"]
                    if constraint_name not in fk_dict:
                        fk_dict[constraint_name] = {
                            "columns": [],
                            "referenced_schema": row["referenced_schema"],
                            "referenced_table": row["referenced_table"],
                            "referenced_columns": [],
                            "on_update": row["update_rule"],
                            "on_delete": row["delete_rule"],
                        }
                    fk_dict[constraint_name]["columns"].append(row["column_name"])
                    fk_dict[constraint_name]["referenced_columns"].append(row["referenced_column"])

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
                            table_name=table,
                            schema=schema,
                        )
                    )

                return foreign_keys

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting foreign keys: {str(e)}")

    def get_indexes(self, schema_or_table: str, table_name: Optional[str] = None) -> List[IndexMetadata]:  # type: ignore[override]
        """
        Obtiene los índices de una tabla.
        Supports both signatures: (schema, table) and (table, schema=None)
        """
        # Support both signatures: (schema, table) and (table, schema=None)
        if table_name is not None:
            # Called as (schema, table_name)
            schema = schema_or_table
            table = table_name
        else:
            # Called as (table_name, schema=None)
            table = schema_or_table
            schema = self._get_default_schema()

        validate_table_name(table)
        validate_schema_name(schema)

        query = """
            SELECT
                i.relname AS index_name,
                a.attname AS column_name,
                ix.indisunique AS is_unique,
                ix.indisprimary AS is_primary,
                am.amname AS index_type
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_am am ON am.oid = i.relam
            WHERE t.relname = %s
              AND n.nspname = %s
            ORDER BY i.relname, a.attnum
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (table, schema))
                results = cursor.fetchall()

                if not results:
                    return []

                # Agrupar por index_name
                idx_dict = {}
                for row in results:
                    index_name = row["index_name"]
                    if index_name not in idx_dict:
                        # Mapear tipo de índice
                        index_type_str = row["index_type"].upper()
                        if index_type_str == "BTREE":
                            index_type = IndexType.BTREE
                        elif index_type_str == "HASH":
                            index_type = IndexType.HASH
                        elif index_type_str == "GIN":
                            index_type = IndexType.GIN
                        elif index_type_str == "GIST":
                            index_type = IndexType.GIST
                        elif index_type_str == "BRIN":
                            index_type = IndexType.BRIN
                        else:
                            index_type = IndexType.UNKNOWN

                        idx_dict[index_name] = {
                            "columns": [],
                            "is_unique": row["is_unique"],
                            "is_primary": row["is_primary"],
                            "index_type": index_type,
                        }
                    idx_dict[index_name]["columns"].append(row["column_name"])

                # Crear objetos IndexMetadata
                indexes = []
                for index_name, idx_data in idx_dict.items():
                    indexes.append(
                        IndexMetadata(
                            name=index_name,
                            columns=idx_data["columns"],
                            table_name=table,
                            schema=schema,
                            is_unique=idx_data["is_unique"],
                            is_primary=idx_data["is_primary"],
                            index_type=idx_data["index_type"],
                        )
                    )

                return indexes

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting indexes: {str(e)}")

    def get_table_statistics(self, schema_or_table: str, table_name: Optional[str] = None) -> TableStatistics:  # type: ignore[override]
        """
        Obtiene estadísticas de una tabla (aproximadas, NO ejecuta COUNT(*)).

        Usa pg_stat_user_tables y pg_class para obtener valores aproximados.

        Args:
            schema_or_table: Schema name if table_name is provided, otherwise table name
            table_name: Table name (optional, for compatibility)
        """
        # Support both signatures: (schema, table) and (table, schema=None)
        if table_name is not None:
            # Called as (schema, table_name)
            schema = schema_or_table
            table = table_name
        else:
            # Called as (table_name, schema=None)
            table = schema_or_table
            schema = self._get_default_schema()

        validate_table_name(table)
        validate_schema_name(schema)

        query = """
            SELECT
                schemaname,
                relname,
                n_live_tup,
                n_dead_tup,
                last_vacuum,
                last_autovacuum,
                last_analyze,
                last_autoanalyze,
                pg_total_relation_size(schemaname||'.'||relname) AS total_size
            FROM pg_stat_user_tables
            WHERE relname = %s
              AND schemaname = %s
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (table, schema))
                result = cursor.fetchone()

                if not result:
                    # Tabla existe pero no tiene estadísticas aún
                    return TableStatistics(
                        table_name=table,
                        schema=schema,
                        row_count=0,
                        size_bytes=0,
                    )

                # Última fecha de vacuum/analyze
                last_vacuum = result["last_vacuum"] or result["last_autovacuum"]
                last_analyze = result["last_analyze"] or result["last_autoanalyze"]

                return TableStatistics(
                    table_name=result["relname"],  # Nombre de la tabla
                    schema=result["schemaname"],  # Schema
                    row_count=result["n_live_tup"],  # Aproximado
                    size_bytes=result["total_size"],
                    last_vacuum=last_vacuum,
                    last_analyze=last_analyze,
                )

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting table statistics: {str(e)}")

    def _get_default_schema(self) -> str:
        """Retorna 'public' (schema por defecto de PostgreSQL)"""
        return "public"

    # =============================================================================
    # ADDITIONAL METHODS (Aliases and convenience methods for test compatibility)
    # =============================================================================

    def list_schemas(self) -> List[str]:
        """Alias for get_schemas() - used by tests"""
        return self.get_schemas()

    def list_tables(self, schema: Optional[str] = None) -> List[TableMetadata]:
        """Alias for get_tables() - used by tests"""
        return self.get_tables(schema)

    def get_table_columns(self, schema: str, table_name: str) -> List[ColumnMetadata]:
        """
        Alias for get_columns() with swapped parameter order.
        Used by tests which call get_table_columns(schema, table).
        """
        return self.get_columns(table_name, schema)

    def get_unique_constraints(
        self, schema: str, table_name: str
    ) -> List[UniqueConstraintMetadata]:
        """Obtiene las unique constraints de una tabla"""
        validate_table_name(table_name)
        validate_schema_name(schema)

        query = """
            SELECT
                tc.constraint_name,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
                AND tc.table_name = kcu.table_name
            WHERE tc.constraint_type = 'UNIQUE'
              AND tc.table_name = %s
              AND tc.table_schema = %s
            ORDER BY tc.constraint_name, kcu.ordinal_position
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (table_name, schema))
                results = cursor.fetchall()

                if not results:
                    return []

                # Agrupar columnas por constraint_name
                unique_dict: Dict[str, List[str]] = {}
                for row in results:
                    constraint_name = row["constraint_name"]
                    if constraint_name not in unique_dict:
                        unique_dict[constraint_name] = []
                    unique_dict[constraint_name].append(row["column_name"])

                # Crear objetos UniqueConstraintMetadata
                unique_constraints = []
                for constraint_name, columns in unique_dict.items():
                    unique_constraints.append(
                        UniqueConstraintMetadata(
                            constraint_name=constraint_name,
                            column_names=columns,
                            table_name=table_name,
                            schema=schema,
                        )
                    )

                return unique_constraints

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting unique constraints: {str(e)}")

    def get_check_constraints(self, schema: str, table_name: str) -> List:
        """Obtiene las check constraints de una tabla"""
        validate_table_name(table_name)
        validate_schema_name(schema)

        query = """
            SELECT
                con.conname AS constraint_name,
                pg_get_constraintdef(con.oid) AS check_clause
            FROM pg_catalog.pg_constraint con
            JOIN pg_catalog.pg_class rel ON rel.oid = con.conrelid
            JOIN pg_catalog.pg_namespace nsp ON nsp.oid = connamespace
            WHERE nsp.nspname = %s
              AND rel.relname = %s
              AND con.contype = 'c'
            ORDER BY con.conname
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, (schema, table_name))
                results = cursor.fetchall()

                # Return as simple objects with constraint_name and check_clause
                from app.models.db_metadata import CheckConstraintMetadata

                check_constraints = []
                for row in results:
                    check_constraints.append(
                        CheckConstraintMetadata(
                            constraint_name=row["constraint_name"],
                            check_clause=row["check_clause"],
                            table_name=table_name,
                            schema=schema,
                        )
                    )

                return check_constraints

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting check constraints: {str(e)}")

    def get_database_metadata(self):
        """
        Obtiene metadata completa de la base de datos.
        Returns DatabaseMetadata object.
        """
        try:
            from app.models.db_metadata import DatabaseMetadata, SchemaMetadata

            schemas = self.get_schemas()
            database_name = self.connection_config["database"]

            schema_metadata_list = []
            for schema_name in schemas:
                tables = self.get_tables(schema_name)

                # Para cada tabla, obtener información completa incluyendo índices
                for table in tables:
                    columns = self.get_columns(table.name, schema_name)
                    table.columns = columns

                    # Cargar índices de la tabla
                    try:
                        indexes = self.get_indexes(schema_name, table.name)
                        # Asignar índices directamente al objeto tabla (usando __dict__ para bypass immutability)
                        object.__setattr__(table, "_indexes", indexes)
                    except Exception:
                        # Si falla, dejar lista vacía
                        object.__setattr__(table, "_indexes", [])

                # Create SchemaMetadata object
                schema_obj = SchemaMetadata(
                    name=schema_name,
                    tables=tables,
                )
                schema_metadata_list.append(schema_obj)

            # Create DatabaseMetadata object
            return DatabaseMetadata(
                name=database_name,
                dialect="postgresql",
                schemas=schema_metadata_list,
            )

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting database metadata: {str(e)}")
