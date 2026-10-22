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
    CheckConstraintMetadata,
    ColumnMetadata,
    DatabaseMetadata,
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
    DBQueryExecutionError,
)
from .type_mappers import PostgreSQLTypeMapper
from .validators import validate_metadata_name

logger = logging.getLogger(__name__)

# ssl_mode del adapter -> parámetros libpq. "verify" usa el almacén de CAs del sistema
# (sslrootcert=system, libpq >= 16) y verifica también el hostname.
_SSL_PARAMS: Dict[str, Dict[str, str]] = {
    "verify": {"sslmode": "verify-full", "sslrootcert": "system"},
    "require": {"sslmode": "require"},
    "disable": {"sslmode": "disable"},
}


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
            self.connection = psycopg2.connect(
                host=self.connection_config["host"],
                port=self.connection_config["port"],
                database=self.connection_config["database"],
                user=self.connection_config["user"],
                password=self.connection_config["password"],
                connect_timeout=self.timeout,
                # Usar RealDictCursor para retornar rows como dicts
                cursor_factory=psycopg2.extras.RealDictCursor,
                **_SSL_PARAMS[self.ssl_mode],
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
            raise DBConnectionError(f"Cannot connect to PostgreSQL: {str(e)}")
        except Exception as e:
            raise DBConnectionError(f"Unexpected error connecting to PostgreSQL: {str(e)}")

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
        self.connect()
        try:
            # Test simple query
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return True
        except Exception as e:
            raise DBConnectionError(f"Connection test failed: {str(e)}")
        finally:
            # Desconectar siempre, también si falla la query (evita fugas de conexiones)
            self.disconnect()

    # =============================================================================
    # METADATA INTROSPECTION
    # =============================================================================
    #
    # Todas las queries reciben schema/tabla como parámetros enlazados. Las de constraints
    # e índices aceptan table=None para devolver el schema completo en una sola query
    # (get_full_schema_metadata) y evitar N+1.

    _COLUMNS_QUERY = """
        SELECT
            table_name,
            column_name,
            data_type,
            udt_name,
            is_nullable,
            column_default,
            is_identity,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
            ordinal_position
        FROM information_schema.columns
        WHERE table_schema = %(schema)s
          AND (%(table)s::text IS NULL OR table_name = %(table)s)
        ORDER BY table_name, ordinal_position
    """

    # PK ('p') o UNIQUE ('u'); columnas en el orden de la constraint (conkey)
    _KEY_CONSTRAINTS_QUERY = """
        SELECT
            rel.relname AS table_name,
            con.conname AS constraint_name,
            att.attname AS column_name
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class rel ON rel.oid = con.conrelid
        JOIN pg_catalog.pg_namespace nsp ON nsp.oid = rel.relnamespace
        CROSS JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_catalog.pg_attribute att
            ON att.attrelid = con.conrelid AND att.attnum = k.attnum
        WHERE con.contype = %(contype)s
          AND nsp.nspname = %(schema)s
          AND (%(table)s::text IS NULL OR rel.relname = %(table)s)
        ORDER BY rel.relname, con.conname, k.ord
    """

    # conkey/confkey se recorren en paralelo para emparejar cada columna con la
    # referenciada (el join con constraint_column_usage producía producto cartesiano
    # en FKs compuestas)
    _FOREIGN_KEYS_QUERY = """
        SELECT
            rel.relname AS table_name,
            con.conname AS constraint_name,
            att.attname AS column_name,
            fnsp.nspname AS referenced_schema,
            frel.relname AS referenced_table,
            fatt.attname AS referenced_column,
            CASE con.confupdtype
                WHEN 'a' THEN 'NO ACTION' WHEN 'r' THEN 'RESTRICT' WHEN 'c' THEN 'CASCADE'
                WHEN 'n' THEN 'SET NULL' WHEN 'd' THEN 'SET DEFAULT'
            END AS update_rule,
            CASE con.confdeltype
                WHEN 'a' THEN 'NO ACTION' WHEN 'r' THEN 'RESTRICT' WHEN 'c' THEN 'CASCADE'
                WHEN 'n' THEN 'SET NULL' WHEN 'd' THEN 'SET DEFAULT'
            END AS delete_rule
        FROM pg_catalog.pg_constraint con
        JOIN pg_catalog.pg_class rel ON rel.oid = con.conrelid
        JOIN pg_catalog.pg_namespace nsp ON nsp.oid = rel.relnamespace
        JOIN pg_catalog.pg_class frel ON frel.oid = con.confrelid
        JOIN pg_catalog.pg_namespace fnsp ON fnsp.oid = frel.relnamespace
        CROSS JOIN LATERAL unnest(con.conkey, con.confkey)
            WITH ORDINALITY AS k(attnum, ref_attnum, ord)
        JOIN pg_catalog.pg_attribute att
            ON att.attrelid = con.conrelid AND att.attnum = k.attnum
        JOIN pg_catalog.pg_attribute fatt
            ON fatt.attrelid = con.confrelid AND fatt.attnum = k.ref_attnum
        WHERE con.contype = 'f'
          AND nsp.nspname = %(schema)s
          AND (%(table)s::text IS NULL OR rel.relname = %(table)s)
        ORDER BY rel.relname, con.conname, k.ord
    """

    # Solo columnas clave del índice (no las INCLUDE), en el orden del índice. Los
    # índices formados solo por expresiones no tienen columnas y se omiten.
    _INDEXES_QUERY = """
        SELECT
            t.relname AS table_name,
            i.relname AS index_name,
            a.attname AS column_name,
            ix.indisunique AS is_unique,
            ix.indisprimary AS is_primary,
            am.amname AS index_type
        FROM pg_catalog.pg_index ix
        JOIN pg_catalog.pg_class t ON t.oid = ix.indrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_catalog.pg_class i ON i.oid = ix.indexrelid
        JOIN pg_catalog.pg_am am ON am.oid = i.relam
        CROSS JOIN LATERAL unnest(ix.indkey::int2[]) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = %(schema)s
          AND (%(table)s::text IS NULL OR t.relname = %(table)s)
          AND k.ord <= ix.indnkeyatts
        ORDER BY t.relname, i.relname, k.ord
    """

    _INDEX_TYPES = {
        "BTREE": IndexType.BTREE,
        "HASH": IndexType.HASH,
        "GIN": IndexType.GIN,
        "GIST": IndexType.GIST,
        "BRIN": IndexType.BRIN,
    }

    def _fetch(self, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Ejecuta una query de metadata y devuelve las filas como dicts."""
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())

    @staticmethod
    def _group_rows(
        rows: List[Dict[str, Any]], table: Optional[str], key: str
    ) -> Dict[tuple, List[Dict[str, Any]]]:
        """Agrupa filas por (tabla, key) manteniendo el orden de la query."""
        grouped: Dict[tuple, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault((row.get("table_name", table), row[key]), []).append(row)
        return grouped

    def _resolve_names(self, table_name: str, schema: Optional[str]) -> tuple:
        schema = schema or self._get_default_schema()
        validate_metadata_name(table_name, "Table name")
        validate_metadata_name(schema, "Schema name")
        return table_name, schema

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
        validate_metadata_name(schema, "Schema name")

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
                    if row["table_type"] == "VIEW":
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

    @staticmethod
    def _build_column(row: Dict[str, Any]) -> ColumnMetadata:
        """Convierte una fila de information_schema.columns en ColumnMetadata."""
        # Usar udt_name (tipo interno) si data_type es "USER-DEFINED"
        native_type = row["udt_name"] if row["data_type"] == "USER-DEFINED" else row["data_type"]

        # Detectar auto-increment: SERIAL/BIGSERIAL (nextval en el default) e IDENTITY
        # (que no tiene default, se marca con is_identity)
        is_auto_increment = row.get("is_identity") == "YES"
        if row["column_default"]:
            default_lower = row["column_default"].lower()
            is_auto_increment = is_auto_increment or "nextval(" in default_lower

        return ColumnMetadata(
            name=row["column_name"],
            data_type=PostgreSQLTypeMapper.map_to_generic(native_type),
            native_type=native_type.upper(),
            is_nullable=(row["is_nullable"] == "YES"),
            is_auto_increment=is_auto_increment,
            default_value=row["column_default"],
            max_length=row["character_maximum_length"],
            numeric_precision=row["numeric_precision"],
            numeric_scale=row["numeric_scale"],
            ordinal_position=row["ordinal_position"],
        )

    def get_columns(self, table_name: str, schema: Optional[str] = None) -> List[ColumnMetadata]:
        """Lista todas las columnas de una tabla"""
        table_name, schema = self._resolve_names(table_name, schema)

        try:
            results = self._fetch(self._COLUMNS_QUERY, {"schema": schema, "table": table_name})
        except Exception as e:
            raise DBQueryExecutionError(f"Error getting columns: {str(e)}")

        if not results:
            raise DBMetadataNotFoundError(
                f"Table '{schema}.{table_name}' not found or has no columns"
            )

        columns = [self._build_column(row) for row in results]

        # Marcar columnas que son PK o FK
        return self._mark_key_columns(columns, table_name, schema)

    def _mark_key_columns(
        self, columns: List[ColumnMetadata], table_name: str, schema: str
    ) -> List[ColumnMetadata]:
        """Marca columnas que son PK o FK (devuelve una lista nueva)."""
        return self._apply_key_flags(
            columns,
            self.get_primary_keys(table_name, schema),
            self.get_foreign_keys(table_name, schema),
        )

    def _query_key_constraints(
        self, contype: str, schema: str, table: Optional[str] = None
    ) -> Dict[str, List[Any]]:
        """PKs ('p') o UNIQUE ('u') agrupadas por tabla."""
        rows = self._fetch(
            self._KEY_CONSTRAINTS_QUERY, {"contype": contype, "schema": schema, "table": table}
        )
        model = PrimaryKeyMetadata if contype == "p" else UniqueConstraintMetadata

        by_table: Dict[str, List[Any]] = {}
        for (tname, constraint_name), group in self._group_rows(
            rows, table, "constraint_name"
        ).items():
            by_table.setdefault(tname, []).append(
                model(
                    constraint_name=constraint_name,
                    column_names=[row["column_name"] for row in group],
                    table_name=tname,
                    schema=schema,
                )
            )
        return by_table

    def _query_foreign_keys(
        self, schema: str, table: Optional[str] = None
    ) -> Dict[str, List[ForeignKeyMetadata]]:
        """FKs agrupadas por tabla, con columnas locales y referenciadas emparejadas."""
        rows = self._fetch(self._FOREIGN_KEYS_QUERY, {"schema": schema, "table": table})

        by_table: Dict[str, List[ForeignKeyMetadata]] = {}
        for (tname, constraint_name), group in self._group_rows(
            rows, table, "constraint_name"
        ).items():
            first = group[0]
            by_table.setdefault(tname, []).append(
                ForeignKeyMetadata(
                    constraint_name=constraint_name,
                    column_names=[row["column_name"] for row in group],
                    referenced_table=first["referenced_table"],
                    referenced_schema=first["referenced_schema"],
                    referenced_columns=[row["referenced_column"] for row in group],
                    on_delete=first["delete_rule"],
                    on_update=first["update_rule"],
                    table_name=tname,
                    schema=schema,
                )
            )
        return by_table

    def _query_indexes(
        self, schema: str, table: Optional[str] = None
    ) -> Dict[str, List[IndexMetadata]]:
        """Índices agrupados por tabla."""
        rows = self._fetch(self._INDEXES_QUERY, {"schema": schema, "table": table})

        by_table: Dict[str, List[IndexMetadata]] = {}
        for (tname, index_name), group in self._group_rows(rows, table, "index_name").items():
            first = group[0]
            by_table.setdefault(tname, []).append(
                IndexMetadata(
                    name=index_name,
                    columns=[row["column_name"] for row in group],
                    table_name=tname,
                    schema=schema,
                    is_unique=first["is_unique"],
                    is_primary=first["is_primary"],
                    index_type=self._INDEX_TYPES.get(
                        first["index_type"].upper(), IndexType.UNKNOWN
                    ),
                )
            )
        return by_table

    def get_primary_keys(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[PrimaryKeyMetadata]:
        """Obtiene las primary keys de una tabla"""
        table_name, schema = self._resolve_names(table_name, schema)
        try:
            return self._query_key_constraints("p", schema, table_name).get(table_name, [])
        except Exception as e:
            raise DBQueryExecutionError(f"Error getting primary keys: {str(e)}")

    def get_foreign_keys(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[ForeignKeyMetadata]:
        """Obtiene las foreign keys de una tabla"""
        table_name, schema = self._resolve_names(table_name, schema)
        try:
            return self._query_foreign_keys(schema, table_name).get(table_name, [])
        except Exception as e:
            raise DBQueryExecutionError(f"Error getting foreign keys: {str(e)}")

    def get_indexes(self, table_name: str, schema: Optional[str] = None) -> List[IndexMetadata]:
        """Obtiene los índices de una tabla"""
        table_name, schema = self._resolve_names(table_name, schema)
        try:
            return self._query_indexes(schema, table_name).get(table_name, [])
        except Exception as e:
            raise DBQueryExecutionError(f"Error getting indexes: {str(e)}")

    def get_unique_constraints(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[UniqueConstraintMetadata]:
        """Obtiene las unique constraints de una tabla"""
        table_name, schema = self._resolve_names(table_name, schema)
        try:
            return self._query_key_constraints("u", schema, table_name).get(table_name, [])
        except Exception as e:
            raise DBQueryExecutionError(f"Error getting unique constraints: {str(e)}")

    def get_full_schema_metadata(self, schema: Optional[str] = None) -> SchemaMetadata:
        """
        Metadata completa de un schema con un número fijo de queries (no N+1).

        Una tabla sin columnas visibles (permisos) se devuelve con columns=[] en lugar
        de hacer fallar el schema completo.
        """
        schema = schema or self._get_default_schema()
        validate_metadata_name(schema, "Schema name")
        logger.info(f"Getting full schema metadata for schema '{schema}'")

        tables = self.get_tables(schema)

        try:
            column_rows = self._fetch(self._COLUMNS_QUERY, {"schema": schema, "table": None})
            pks_by_table = self._query_key_constraints("p", schema)
            uniques_by_table = self._query_key_constraints("u", schema)
            fks_by_table = self._query_foreign_keys(schema)
            indexes_by_table = self._query_indexes(schema)
        except Exception as e:
            raise DBQueryExecutionError(f"Error getting schema metadata: {str(e)}")

        columns_by_table: Dict[str, List[ColumnMetadata]] = {}
        for row in column_rows:
            columns_by_table.setdefault(row["table_name"], []).append(self._build_column(row))

        primary_keys: List[PrimaryKeyMetadata] = []
        foreign_keys: List[ForeignKeyMetadata] = []
        unique_constraints: List[UniqueConstraintMetadata] = []
        indexes: List[IndexMetadata] = []

        for table in tables:
            pks = pks_by_table.get(table.name, [])
            fks = fks_by_table.get(table.name, [])
            if table.name not in columns_by_table:
                logger.warning(f"No visible columns for table '{schema}.{table.name}'")
            table.columns = self._apply_key_flags(columns_by_table.get(table.name, []), pks, fks)

            primary_keys.extend(pks)
            foreign_keys.extend(fks)
            unique_constraints.extend(uniques_by_table.get(table.name, []))
            indexes.extend(indexes_by_table.get(table.name, []))

        return self._build_schema_metadata(
            schema, tables, primary_keys, foreign_keys, unique_constraints, indexes
        )

    def get_table_statistics(
        self, table_name: str, schema: Optional[str] = None
    ) -> TableStatistics:
        """
        Obtiene estadísticas de una tabla (aproximadas, NO ejecuta COUNT(*)).

        Usa pg_stat_user_tables y pg_class para obtener valores aproximados.
        """
        table_name, schema = self._resolve_names(table_name, schema)

        # pg_total_relation_size(relid): con schemaname||'.'||relname fallaban los nombres
        # con mayúsculas o caracteres especiales
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
                pg_total_relation_size(relid) AS total_size
            FROM pg_stat_user_tables
            WHERE relname = %s
              AND schemaname = %s
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

    def get_check_constraints(self, table_name: str, schema: Optional[str] = None) -> List:
        """Obtiene las check constraints de una tabla"""
        table_name, schema = self._resolve_names(table_name, schema)

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

                return [
                    CheckConstraintMetadata(
                        constraint_name=row["constraint_name"],
                        check_clause=row["check_clause"],
                        table_name=table_name,
                        schema=schema,
                    )
                    for row in results
                ]

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting check constraints: {str(e)}")

    def get_database_metadata(self) -> DatabaseMetadata:
        """Obtiene metadata completa de la base de datos (todos los schemas)."""
        try:
            schema_metadata_list = []
            for schema_name in self.get_schemas():
                schema_obj = self.get_full_schema_metadata(schema_name)

                # Exponer los índices también en cada tabla (TableMetadata.indexes)
                for table in schema_obj.tables:
                    object.__setattr__(
                        table,
                        "_indexes",
                        [idx for idx in schema_obj.indexes if idx.table_name == table.name],
                    )
                schema_metadata_list.append(schema_obj)

            return DatabaseMetadata(
                name=self.connection_config["database"],
                dialect="postgresql",
                schemas=schema_metadata_list,
            )

        except Exception as e:
            raise DBQueryExecutionError(f"Error getting database metadata: {str(e)}")
