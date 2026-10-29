"""
Migration Script Generation Service

Genera scripts SQL de migración a partir de mappings híbridos (import + connector).
Resuelve hashes SHA-256 consultando bases de datos externas en tiempo real.

IMPORTANTE:
- Los hashes SHA-256 son irreversibles (one-way)
- Solo se pueden resolver consultando la BD real usando adapters
- Si una tabla fue renombrada en BD externa, el hash no coincidirá
- El script (INSERT INTO destino SELECT ... FROM origen) se ejecuta en la BD destino:
  solo sirve cuando origen y destino son la misma BD. Entre BDs distintas la
  migración la ejecuta DataMap copiando por lotes (ExecutionService.execute_copy)
  a partir de los mismos planes (build_table_plans).
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from app.services.connector_resolver import (  # noqa: F401 (re-export)
    ConnectorNameResolver,
    HashNotFoundError,
    MigrationScriptServiceError,
    SqlName,
)
from app.utils.db_adapters.base_adapter import BaseDBAdapter
from app.utils.sql_safety import (
    quote_identifier,
    quote_literal,
    safe_routine_suffix,
    sanitize_comment,
    validate_sql_expression,
    validate_sql_type,
)

logger = logging.getLogger(__name__)

# Tabla o columna: nombre ya resuelto (SqlName) o nombre de un mapping import (str)
NameLike = Union[str, SqlName]


def _render(name: NameLike, dialect: str) -> str:
    """Cita un nombre para el dialecto (SqlName respeta su modo exacto)."""
    if isinstance(name, SqlName):
        return name.render(dialect)
    return quote_identifier(name, dialect)


def _plain(name: NameLike) -> str:
    """Nombre sin citar (para comentarios, literales y sufijos)."""
    return name.name if isinstance(name, SqlName) else str(name)


@dataclass
class ColumnPlan:
    """Una columna destino y de qué columna/expresión del origen sale."""

    origin: SqlName
    dest: SqlName
    transformation_logic: Optional[str] = None
    origin_type: Optional[str] = None
    dest_type: Optional[str] = None


@dataclass
class TablePlan:
    """Qué columnas de una tabla origen se copian a una tabla destino."""

    origin: SqlName
    dest: SqlName
    columns: List[ColumnPlan] = field(default_factory=list)


class MigrationScriptService:
    """
    Servicio de generación de scripts SQL de migración.

    Responsabilidades:
    - Generar scripts INSERT INTO ... SELECT basados en mappings
    - Resolver hashes SHA-256 consultando bases de datos reales
    - Manejar mappings híbridos (import + connector)

    Usage:
        service = MigrationScriptService()
        script = service.generate_insert_script(
            mappings=mappings,
            origin_adapter=origin_adapter,
            dest_adapter=dest_adapter
        )
    """

    @staticmethod
    def build_table_plans(
        mappings: List[Dict[str, Any]],
        origin_adapter: Optional[BaseDBAdapter] = None,
        dest_adapter: Optional[BaseDBAdapter] = None,
        dependency_order: Optional[List[str]] = None,
    ) -> Tuple[List[TablePlan], List[str]]:
        """
        Agrupa los mappings por tabla destino y resuelve todos los nombres.

        Args:
            mappings: Mappings del proyecto (ya descifrados)
            origin_adapter: Adapter conectado al origen (necesario si hay mappings connector)
            dest_adapter: Adapter conectado al destino (necesario si hay mappings connector)
            dependency_order: Orden topológico de tablas destino (por nombre)

        Returns:
            (planes en orden de ejecución, errores de resolución por tabla)

        Raises:
            ValueError: Si hay mappings connector y falta el adapter de ese lado
            MigrationScriptServiceError: Si un mapping es inválido o una tabla destino
                recibe columnas de varias tablas origen
        """
        origin_resolver = (
            ConnectorNameResolver(origin_adapter, "origin") if origin_adapter else None
        )
        dest_resolver = ConnectorNameResolver(dest_adapter, "destination") if dest_adapter else None

        errors: List[str] = []
        grouped: Dict[SqlName, List[Dict[str, Any]]] = {}
        for mapping in mappings:
            try:
                dest_table = MigrationScriptService._resolve_table(
                    mapping, "destination", dest_resolver
                )
            except HashNotFoundError as e:
                logger.error(f"Hash not found in mapping preparation: {str(e)}")
                errors.append(str(e))
                continue
            grouped.setdefault(dest_table, []).append(mapping)

        dest_tables = list(grouped)
        if dependency_order:
            position = {name: idx for idx, name in enumerate(dependency_order)}
            # sorted es estable: las tablas fuera del orden quedan al final
            dest_tables.sort(key=lambda t: position.get(t.name, len(position)))

        plans: List[TablePlan] = []
        for dest_table in dest_tables:
            try:
                plans.append(
                    MigrationScriptService._build_table_plan(
                        dest_table, grouped[dest_table], origin_resolver, dest_resolver
                    )
                )
            except HashNotFoundError as e:
                logger.error(f"Hash not found for table {dest_table}: {str(e)}")
                errors.append(f"{dest_table}: {e}")

        return plans, errors

    @staticmethod
    def _build_table_plan(
        dest_table: SqlName,
        table_mappings: List[Dict[str, Any]],
        origin_resolver: Optional[ConnectorNameResolver],
        dest_resolver: Optional[ConnectorNameResolver],
    ) -> TablePlan:
        origin_tables = []
        for mapping in table_mappings:
            origin_table = MigrationScriptService._resolve_table(mapping, "origin", origin_resolver)
            if origin_table not in origin_tables:
                origin_tables.append(origin_table)

        if len(origin_tables) > 1:
            # Antes se usaba en silencio la primera tabla y el SELECT referenciaba
            # columnas de las otras (SQL roto o datos de la tabla equivocada)
            raise MigrationScriptServiceError(
                f"Destination table '{dest_table}' maps columns from several origin tables "
                f"({', '.join(str(t) for t in origin_tables)}); only one origin table per "
                f"destination table is supported"
            )
        origin_table = origin_tables[0]

        columns = [
            ColumnPlan(
                origin=MigrationScriptService._resolve_column(
                    mapping, "origin", origin_resolver, origin_table
                ),
                dest=MigrationScriptService._resolve_column(
                    mapping, "destination", dest_resolver, dest_table
                ),
                # Campo cifrado que el CRUD ya descifró
                transformation_logic=mapping.get("transformation_logic"),
                origin_type=mapping.get("origin_data_type"),
                dest_type=mapping.get("destination_data_type"),
            )
            for mapping in table_mappings
        ]
        return TablePlan(origin=origin_table, dest=dest_table, columns=columns)

    @staticmethod
    def _connector_hash(mapping: Dict[str, Any], hash_key: str, side: str, resolver) -> str:
        hash_value = mapping.get(hash_key)
        if not hash_value:
            raise MigrationScriptServiceError(
                f"Missing {hash_key} for connector mode in mapping {mapping.get('id')}"
            )
        if resolver is None:
            raise ValueError(
                f"Adapter is required for connector mode ({side}), but None was provided"
            )
        return str(hash_value)

    @staticmethod
    def _import_name(mapping: Dict[str, Any], name_key: str) -> str:
        name = mapping.get(name_key)
        if not name:
            raise MigrationScriptServiceError(
                f"Missing {name_key} for import mode in mapping {mapping.get('id')}"
            )
        return str(name)

    @staticmethod
    def _source_type(mapping: Dict[str, Any], side: str) -> str:
        source_type = mapping.get(f"{side}_source_type") or "import"
        if source_type not in ("import", "connector"):
            raise MigrationScriptServiceError(f"Unknown source_type: {source_type} for {side}")
        return str(source_type)

    @staticmethod
    def _resolve_table(
        mapping: Dict[str, Any], side: str, resolver: Optional[ConnectorNameResolver]
    ) -> SqlName:
        if MigrationScriptService._source_type(mapping, side) == "import":
            return SqlName(MigrationScriptService._import_name(mapping, f"{side}_table"))
        hash_value = MigrationScriptService._connector_hash(
            mapping, f"{side}_table_hash", side, resolver
        )
        assert resolver is not None
        return resolver.resolve_table(hash_value)

    @staticmethod
    def _resolve_column(
        mapping: Dict[str, Any],
        side: str,
        resolver: Optional[ConnectorNameResolver],
        table: SqlName,
    ) -> SqlName:
        if MigrationScriptService._source_type(mapping, side) == "import":
            return SqlName(MigrationScriptService._import_name(mapping, f"{side}_column"))
        hash_value = MigrationScriptService._connector_hash(
            mapping, f"{side}_column_hash", side, resolver
        )
        assert resolver is not None
        return resolver.resolve_column(hash_value, table)

    @staticmethod
    def generate_insert_script(
        mappings: List[Dict[str, Any]],
        origin_adapter: Optional[BaseDBAdapter] = None,
        dest_adapter: Optional[BaseDBAdapter] = None,
        project_name: Optional[str] = None,
        dependency_order: Optional[List[str]] = None,
        batch_size: int = 10000,
        include_constraints: bool = True,
        include_validation: bool = True,
        dialect: str = "postgresql",
    ) -> str:
        """
        Genera script SQL INSERT resolviendo hashes si es necesario.

        Args:
            mappings: Lista de mappings del proyecto
            origin_adapter: Adapter para resolver hashes del origen (solo si hay mappings connector)
            dest_adapter: Adapter para resolver hashes del destino (solo si hay mappings connector)
            project_name: Nombre del proyecto (opcional, para header)
            dependency_order: Orden topológico de tablas (opcional, para ejecutar en orden correcto)
            batch_size: Tamaño de batch para tablas grandes (default: 10000)
            include_constraints: Si incluir manejo de constraints (default: True)
            include_validation: Si incluir queries de validación al final (default: True)
            dialect: Dialecto SQL ('postgresql', 'mysql', 'sqlserver', 'oracle')

        Returns:
            Script SQL completo con transacciones, constraints, batching y validación

        Raises:
            ValueError: Si se requiere adapter pero es None
            MigrationScriptServiceError: Si un mapping es inválido
        """
        if not mappings:
            return "-- No mappings found for this project\n"

        plans, errors = MigrationScriptService.build_table_plans(
            mappings, origin_adapter, dest_adapter, dependency_order
        )
        all_tables = [plan.dest for plan in plans]

        # Header
        now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "-- ========================================",
            "-- MIGRATION SCRIPT",
            f"-- Generated at {now_utc} UTC",
        ]
        if project_name:
            lines.append(f"-- Project: {sanitize_comment(project_name)}")
        lines.append(f"-- Total mappings: {len(mappings)}")
        lines.append(f"-- Total tables: {len(all_tables)}")
        lines.append(f"-- Dialect: {dialect}")
        lines.append(f"-- Batch size: {batch_size}")
        lines.append("-- ========================================")
        for error in errors:
            lines.append(f"-- ERROR: {sanitize_comment(error)}")
        lines.append("")

        begin_stmt, commit_stmt = MigrationScriptService._generate_transaction_wrapper(dialect)
        lines.append("-- SECTION 1: Transaction Start")
        lines.append(begin_stmt)
        lines.append("")

        if include_constraints and all_tables:
            lines.append("-- SECTION 2: Disable Constraints")
            lines.append(MigrationScriptService._generate_constraint_disabling(all_tables, dialect))
            lines.append("")

        lines.append("-- SECTION 3: Data Migration (in dependency order)")
        lines.append("")
        for table_idx, plan in enumerate(plans, start=1):
            lines.append(f"-- Table {table_idx}/{len(plans)}: {sanitize_comment(str(plan.dest))}")
            lines.append(
                MigrationScriptService._generate_table_insert(
                    plan, origin_adapter, batch_size, dialect
                )
            )
            lines.append("")

        if include_constraints and all_tables:
            lines.append("-- SECTION 4: Enable Constraints")
            lines.append(MigrationScriptService._generate_constraint_enabling(all_tables, dialect))
            lines.append("")

        if include_validation and all_tables:
            lines.append("-- SECTION 5: Validation")
            for table in all_tables:
                lines.append(MigrationScriptService.validation_query(table, dialect) + ";")
            lines.append("")

        lines.append("-- SECTION 6: Transaction Commit")
        lines.append(commit_stmt)
        lines.append("")
        lines.append("-- ========================================")
        lines.append("-- MIGRATION COMPLETE")
        lines.append(f"-- Total tables migrated: {len(all_tables)}")
        lines.append("-- ========================================")

        return "\n".join(lines)

    @staticmethod
    def validation_query(table: NameLike, dialect: str) -> str:
        """SELECT con el número de filas de una tabla destino."""
        return (
            f"SELECT {quote_literal(_plain(table), dialect)} AS table_name, "
            f"COUNT(*) AS row_count FROM {_render(table, dialect)}"
        )

    @staticmethod
    def _generate_table_insert(
        plan: TablePlan, origin_adapter: Optional[BaseDBAdapter], batch_size: int, dialect: str
    ) -> str:
        """INSERT INTO destino SELECT ... FROM origen (con batching si la tabla es grande)."""
        select_expressions = [
            MigrationScriptService._apply_transformation(
                column_name=column.origin,
                transformation_logic=column.transformation_logic,
                origin_type=column.origin_type,
                dest_type=column.dest_type,
                dialect=dialect,
            )
            for column in plan.columns
        ]
        select_clause = f"SELECT {', '.join(select_expressions)} FROM {plan.origin.render(dialect)}"
        dest_columns = [column.dest for column in plan.columns]

        # Row count real del adapter si está disponible
        estimated_rows = None
        if origin_adapter:
            try:
                stats = origin_adapter.get_table_statistics(plan.origin.name, plan.origin.schema)
                estimated_rows = stats.row_count
            except Exception as e:
                logger.warning(f"Could not get row count for {plan.origin}: {e}")

        if estimated_rows is not None and estimated_rows > batch_size:
            return (
                f"-- Large table - using batching (estimated rows: {estimated_rows})\n"
                + MigrationScriptService._generate_batched_insert(
                    table_name=plan.dest,
                    columns=dest_columns,
                    select_clause=select_clause,
                    total_rows=estimated_rows,
                    batch_size=batch_size,
                    dialect=dialect,
                )
            )

        quoted_columns = ", ".join(_render(c, dialect) for c in dest_columns)
        return f"INSERT INTO {plan.dest.render(dialect)} ({quoted_columns})\n{select_clause};"

    @staticmethod
    def _resolve_name(
        mapping: Dict[str, Any],
        side: str,
        adapter: Optional[BaseDBAdapter],
        is_column: bool = False,
    ) -> str:
        """
        Resuelve el nombre de una tabla o columna según el modo.

        Args:
            mapping: Mapping dict con todos los campos
            side: 'origin' o 'destination'
            adapter: Adapter para resolver hashes (None si es import)
            is_column: True si es columna, False si es tabla

        Returns:
            Nombre resuelto (plaintext o resuelto desde hash)

        Raises:
            HashNotFoundError: Si hash no se encuentra en BD
            ValueError: Si se requiere adapter pero es None
        """
        source_type_key = f"{side}_source_type"
        source_type = mapping.get(source_type_key, "import")

        if is_column:
            name_key = f"{side}_column"
            hash_key = f"{side}_column_hash"
        else:
            name_key = f"{side}_table"
            hash_key = f"{side}_table_hash"

        if source_type == "import":
            # Modo import: usar nombre directamente (ya descifrado por el CRUD)
            name = mapping.get(name_key)
            if not name:
                raise MigrationScriptServiceError(
                    f"Missing {name_key} for import mode in mapping {mapping.get('id')}"
                )
            return str(name)

        elif source_type == "connector":
            # Modo connector: resolver hash usando adapter
            hash_value = mapping.get(hash_key)

            if not hash_value:
                raise MigrationScriptServiceError(
                    f"Missing {hash_key} for connector mode in mapping {mapping.get('id')}"
                )

            if adapter is None:
                raise ValueError(
                    f"Adapter is required for connector mode ({side}), but None was provided"
                )

            # Resolver hash consultando la BD
            resolved_name = MigrationScriptService._resolve_hash_from_adapter(
                adapter=adapter, hash_value=hash_value, is_column=is_column, side=side
            )

            return resolved_name

        else:
            raise MigrationScriptServiceError(f"Unknown source_type: {source_type} for {side}")

    @staticmethod
    def _resolve_hash_from_adapter(
        adapter: BaseDBAdapter, hash_value: str, is_column: bool, side: str
    ) -> str:
        """
        Resuelve un hash SHA-256 consultando metadata de la BD.

        Args:
            adapter: Adapter conectado a la BD
            hash_value: Hash SHA-256 a resolver (64 caracteres hex)
            is_column: True si es columna, False si es tabla
            side: 'origin' o 'destination' (para mensajes de error)

        Returns:
            Nombre que coincide con el hash

        Raises:
            HashNotFoundError: Si no se encuentra ningún match
        """
        try:
            if not is_column:
                # Resolver hash de tabla
                tables = adapter.get_tables()

                for table in tables:
                    table_hash = hashlib.sha256(table.name.encode()).hexdigest()
                    if table_hash == hash_value:
                        logger.info(
                            f"Hash resolved: {hash_value[:8]}... → {table.name} (table, {side})"
                        )
                        return table.name

                # No encontrado
                raise HashNotFoundError(hash_value, side)

            else:
                # Resolver hash de columna
                # NOTA: Necesitamos buscar en TODAS las tablas porque no sabemos en cuál está
                tables = adapter.get_tables()

                for table in tables:
                    columns = adapter.get_columns(table.name)

                    for column in columns:
                        column_hash = hashlib.sha256(column.name.encode()).hexdigest()
                        if column_hash == hash_value:
                            logger.info(
                                f"Hash resolved: {hash_value[:8]}... → {column.name} "
                                f"(column in {table.name}, {side})"
                            )
                            return column.name

                # No encontrado
                raise HashNotFoundError(hash_value, side)

        except HashNotFoundError:
            raise

        except Exception as e:
            logger.error(f"Error resolving hash {hash_value[:8]}...: {str(e)}")
            raise MigrationScriptServiceError(f"Error querying {side} database: {str(e)}")

    @staticmethod
    def _generate_transaction_wrapper(dialect: str) -> Tuple[str, str]:
        """
        Genera los statements de inicio y commit de transacción según el dialecto.

        Args:
            dialect: Dialecto SQL ('postgresql', 'mysql', 'sqlserver', 'oracle')

        Returns:
            Tuple de (begin_statement, commit_statement)

        Examples:
            PostgreSQL: ('BEGIN;', 'COMMIT;')
            MySQL: ('START TRANSACTION;', 'COMMIT;')
            SQL Server: ('BEGIN TRANSACTION;', 'COMMIT TRANSACTION;')
            Oracle: ('SET TRANSACTION READ WRITE;', 'COMMIT;')

        Note:
            Oracle inicia la transacción implícitamente; un "BEGIN" suelto es un
            bloque PL/SQL incompleto, por eso se usa SET TRANSACTION.
        """
        dialect_lower = dialect.lower()

        if dialect_lower == "postgresql":
            return ("BEGIN;", "COMMIT;")
        elif dialect_lower == "mysql":
            return ("START TRANSACTION;", "COMMIT;")
        elif dialect_lower == "sqlserver":
            return ("BEGIN TRANSACTION;", "COMMIT TRANSACTION;")
        elif dialect_lower == "oracle":
            return ("SET TRANSACTION READ WRITE;", "COMMIT;")
        else:
            # Default to PostgreSQL syntax
            logger.warning(f"Unknown dialect '{dialect}', using PostgreSQL syntax")
            return ("BEGIN;", "COMMIT;")

    @staticmethod
    def _generate_constraint_disabling(tables: List[NameLike], dialect: str) -> str:
        """
        Genera SQL para deshabilitar constraints y triggers antes de la migración.

        Args:
            tables: Lista de nombres de tablas únicas involucradas
            dialect: Dialecto SQL

        Returns:
            SQL para deshabilitar constraints

        Examples:
            PostgreSQL: ALTER TABLE {table} DISABLE TRIGGER ALL;
            MySQL: SET FOREIGN_KEY_CHECKS=0;
            SQL Server: ALTER TABLE {table} NOCHECK CONSTRAINT ALL;
            Oracle: ALTER TABLE {table} DISABLE ALL TRIGGERS;
        """
        dialect_lower = dialect.lower()
        lines = []

        if dialect_lower == "postgresql":
            lines.append("-- Disable triggers and constraints")
            for table in tables:
                lines.append(f"ALTER TABLE {_render(table, dialect_lower)} DISABLE TRIGGER ALL;")
        elif dialect_lower == "mysql":
            lines.append("-- Disable foreign key checks")
            lines.append("SET FOREIGN_KEY_CHECKS=0;")
            lines.append("SET AUTOCOMMIT=0;")
        elif dialect_lower == "sqlserver":
            lines.append("-- Disable constraints")
            for table in tables:
                lines.append(f"ALTER TABLE {_render(table, dialect_lower)} NOCHECK CONSTRAINT ALL;")
        elif dialect_lower == "oracle":
            lines.append("-- Disable triggers")
            for table in tables:
                lines.append(f"ALTER TABLE {_render(table, dialect_lower)} DISABLE ALL TRIGGERS;")
        else:
            logger.warning(f"Unknown dialect '{dialect}', skipping constraint disabling")

        return "\n".join(lines)

    @staticmethod
    def _generate_constraint_enabling(tables: List[NameLike], dialect: str) -> str:
        """
        Genera SQL para habilitar constraints y triggers después de la migración.

        Args:
            tables: Lista de nombres de tablas únicas involucradas
            dialect: Dialecto SQL

        Returns:
            SQL para habilitar constraints

        Examples:
            PostgreSQL: ALTER TABLE {table} ENABLE TRIGGER ALL;
            MySQL: SET FOREIGN_KEY_CHECKS=1;
            SQL Server: ALTER TABLE {table} CHECK CONSTRAINT ALL;
            Oracle: ALTER TABLE {table} ENABLE ALL TRIGGERS;
        """
        dialect_lower = dialect.lower()
        lines = []

        if dialect_lower == "postgresql":
            lines.append("-- Enable triggers and constraints")
            for table in tables:
                lines.append(f"ALTER TABLE {_render(table, dialect_lower)} ENABLE TRIGGER ALL;")
        elif dialect_lower == "mysql":
            lines.append("-- Enable foreign key checks")
            lines.append("SET FOREIGN_KEY_CHECKS=1;")
        elif dialect_lower == "sqlserver":
            lines.append("-- Enable constraints")
            for table in tables:
                lines.append(f"ALTER TABLE {_render(table, dialect_lower)} CHECK CONSTRAINT ALL;")
        elif dialect_lower == "oracle":
            lines.append("-- Enable triggers")
            for table in tables:
                lines.append(f"ALTER TABLE {_render(table, dialect_lower)} ENABLE ALL TRIGGERS;")
        else:
            logger.warning(f"Unknown dialect '{dialect}', skipping constraint enabling")

        return "\n".join(lines)

    @staticmethod
    def _apply_transformation(
        column_name: NameLike,
        transformation_logic: Optional[str],
        origin_type: Optional[str],
        dest_type: Optional[str],
        dialect: str,
    ) -> str:
        """
        Aplica transformaciones customizadas o conversiones automáticas de tipos.

        Args:
            column_name: Nombre de la columna
            transformation_logic: Lógica de transformación custom (ej: "UPPER(TRIM({column}))")
            origin_type: Tipo de dato origen (opcional)
            dest_type: Tipo de dato destino (opcional)
            dialect: Dialecto SQL

        Returns:
            Expresión SQL a usar en la cláusula SELECT

        Examples:
            Con transformación custom: "UPPER(TRIM(email))"
            Sin transformación pero tipos incompatibles: "CAST(price AS DECIMAL(10,2))"
            Sin transformación y tipos compatibles: "email"
        """
        # Si hay transformación customizada, aplicarla
        column_name = _render(column_name, dialect)

        if transformation_logic:
            # La transformación es una expresión SQL por diseño: se exige que sea
            # una única expresión (sin ';' ni comentarios) para que no pueda
            # inyectar sentencias adicionales en el script
            validate_sql_expression(transformation_logic)
            # Reemplazar placeholder {column} por el nombre real
            return transformation_logic.replace("{column}", column_name)

        # Si no hay transformación pero los tipos son incompatibles, generar conversión automática
        if origin_type and dest_type and origin_type.upper() != dest_type.upper():
            return MigrationScriptService._generate_type_conversion(
                column_name, origin_type, dest_type, dialect
            )

        # Si todo es compatible, usar la columna directamente
        return column_name

    @staticmethod
    def _generate_type_conversion(
        column_name: str, origin_type: str, dest_type: str, dialect: str
    ) -> str:
        """
        Genera conversión automática entre tipos incompatibles.

        Args:
            column_name: Nombre de la columna
            origin_type: Tipo origen
            dest_type: Tipo destino
            dialect: Dialecto SQL

        Returns:
            Expresión SQL con conversión de tipo

        Examples:
            VARCHAR -> INTEGER: "CAST(column_name AS INTEGER)"
            DATE -> TIMESTAMP: "column_name::TIMESTAMP" (PostgreSQL)
            INTEGER -> VARCHAR: "CAST(column_name AS VARCHAR(50))"
        """
        dest_type = validate_sql_type(dest_type)
        origin_upper = origin_type.upper()
        dest_upper = dest_type.upper()
        dialect_lower = dialect.lower()

        # Conversiones comunes
        conversions = {
            ("VARCHAR", "INTEGER"): f"CAST({column_name} AS INTEGER)",
            ("VARCHAR", "BIGINT"): f"CAST({column_name} AS BIGINT)",
            ("VARCHAR", "DECIMAL"): f"CAST({column_name} AS DECIMAL)",
            ("VARCHAR", "NUMERIC"): f"CAST({column_name} AS NUMERIC)",
            ("INTEGER", "VARCHAR"): f"CAST({column_name} AS VARCHAR(50))",
            ("BIGINT", "VARCHAR"): f"CAST({column_name} AS VARCHAR(50))",
            ("DATE", "TIMESTAMP"): f"CAST({column_name} AS TIMESTAMP)",
            ("TIMESTAMP", "DATE"): f"CAST({column_name} AS DATE)",
            ("TEXT", "VARCHAR"): f"CAST({column_name} AS VARCHAR(255))",
            ("VARCHAR", "TEXT"): f"CAST({column_name} AS TEXT)",
        }

        # PostgreSQL soporta sintaxis :: además de CAST
        if dialect_lower == "postgresql":
            pg_conversions = {
                ("DATE", "TIMESTAMP"): f"{column_name}::TIMESTAMP",
                ("TIMESTAMP", "DATE"): f"{column_name}::DATE",
                ("VARCHAR", "INTEGER"): f"{column_name}::INTEGER",
                ("INTEGER", "VARCHAR"): f"{column_name}::VARCHAR",
            }
            conversions.update(pg_conversions)

        # Buscar conversión exacta
        key = (origin_upper, dest_upper)
        if key in conversions:
            logger.info(f"Auto-converting {column_name} from {origin_type} to {dest_type}")
            return conversions[key]

        # Si no hay conversión específica, usar CAST genérico
        logger.warning(
            f"No specific conversion for {origin_type} -> {dest_type}, using generic CAST"
        )
        return f"CAST({column_name} AS {dest_type})"

    @staticmethod
    def _generate_batched_insert(
        table_name: NameLike,
        columns: List[NameLike],
        select_clause: str,
        total_rows: Optional[int],
        batch_size: int,
        dialect: str,
    ) -> str:
        """
        Genera INSERT con batching para tablas grandes.

        Args:
            table_name: Nombre de la tabla destino
            columns: Lista de columnas
            select_clause: Cláusula SELECT completa
            total_rows: Número total de filas (None si desconocido)
            batch_size: Tamaño de cada batch
            dialect: Dialecto SQL

        Returns:
            SQL con loop de batching y progress tracking

        Examples (PostgreSQL):
            DO $$
            DECLARE
                batch_size INT := 10000;
                offset_val INT := 0;
                total_rows INT := 50000;
            BEGIN
                WHILE offset_val < total_rows LOOP
                    INSERT INTO table_name (col1, col2)
                    SELECT col1, col2 FROM source_table
                    LIMIT batch_size OFFSET offset_val;

                    offset_val := offset_val + batch_size;
                    RAISE NOTICE 'Progress: % / %', offset_val, total_rows;
                END LOOP;
            END $$;
        """
        dialect_lower = dialect.lower()
        columns_str = ", ".join(_render(c, dialect_lower) for c in columns)
        routine_suffix = safe_routine_suffix(_plain(table_name))
        table_name = _render(table_name, dialect_lower)
        total_rows_str = str(total_rows) if total_rows else "NULL"

        if dialect_lower == "postgresql":
            return f"""DO $$
DECLARE
    batch_size INT := {batch_size};
    offset_val INT := 0;
    total_rows INT := {total_rows_str};
BEGIN
    WHILE offset_val < total_rows LOOP
        INSERT INTO {table_name} ({columns_str})
        {select_clause}
        LIMIT batch_size OFFSET offset_val;

        offset_val := offset_val + batch_size;
        RAISE NOTICE 'Progress: % / %', offset_val, total_rows;
    END LOOP;
END $$;"""

        elif dialect_lower == "mysql":
            # MySQL no tiene DO blocks, usar procedimiento temporal
            return f"""-- Batched insert for MySQL
DELIMITER $$
CREATE PROCEDURE batch_insert_{routine_suffix}()
BEGIN
    DECLARE batch_size INT DEFAULT {batch_size};
    DECLARE offset_val INT DEFAULT 0;
    DECLARE total_rows INT DEFAULT {total_rows_str};

    WHILE offset_val < total_rows DO
        INSERT INTO {table_name} ({columns_str})
        {select_clause}
        LIMIT batch_size OFFSET offset_val;

        SET offset_val = offset_val + batch_size;
        SELECT CONCAT('Progress: ', offset_val, ' / ', total_rows) AS status;
    END WHILE;
END$$
DELIMITER ;

CALL batch_insert_{routine_suffix}();
DROP PROCEDURE batch_insert_{routine_suffix};"""

        elif dialect_lower == "sqlserver":
            return f"""-- Batched insert for SQL Server
DECLARE @batch_size INT = {batch_size};
DECLARE @offset_val INT = 0;
DECLARE @total_rows INT = {total_rows_str};

WHILE @offset_val < @total_rows
BEGIN
    INSERT INTO {table_name} ({columns_str})
    {select_clause}
    ORDER BY (SELECT NULL)
    OFFSET @offset_val ROWS
    FETCH NEXT @batch_size ROWS ONLY;

    SET @offset_val = @offset_val + @batch_size;
    PRINT 'Progress: ' + CAST(@offset_val AS VARCHAR) + ' / ' + CAST(@total_rows AS VARCHAR);
END;"""

        elif dialect_lower == "oracle":
            return f"""-- Batched insert for Oracle
DECLARE
    batch_size NUMBER := {batch_size};
    offset_val NUMBER := 0;
    total_rows NUMBER := {total_rows_str};
BEGIN
    WHILE offset_val < total_rows LOOP
        INSERT INTO {table_name} ({columns_str})
        {select_clause}
        OFFSET offset_val ROWS FETCH NEXT batch_size ROWS ONLY;

        offset_val := offset_val + batch_size;
        DBMS_OUTPUT.PUT_LINE('Progress: ' || offset_val || ' / ' || total_rows);
    END LOOP;
END;
/"""

        else:
            # Fallback: INSERT simple sin batching
            logger.warning(
                f"Unknown dialect '{dialect}', generating simple INSERT without batching"
            )
            return f"INSERT INTO {table_name} ({columns_str})\n{select_clause};"
