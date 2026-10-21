"""
Migration Script Generation Service

Genera scripts SQL de migración a partir de mappings híbridos (import + connector).
Resuelve hashes SHA-256 consultando bases de datos externas en tiempo real.

IMPORTANTE:
- Los hashes SHA-256 son irreversibles (one-way)
- Solo se pueden resolver consultando la BD real usando adapters
- Si una tabla fue renombrada en BD externa, el hash no coincidirá
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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


class MigrationScriptServiceError(Exception):
    """Base exception for MigrationScriptService"""

    pass


class HashNotFoundError(MigrationScriptServiceError):
    """Hash no se encontró en la base de datos"""

    def __init__(self, hash_value: str, side: str):
        self.hash_value = hash_value
        self.side = side
        super().__init__(
            f"Hash {hash_value[:8]}... not found in {side} database. "
            f"Table/column may have been renamed or deleted."
        )


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
            HashNotFoundError: Si un hash no se encuentra en la BD
            ValueError: Si se requiere adapter pero es None
        """
        if not mappings:
            return "-- No mappings found for this project\n"

        # ============================================================================
        # FASE 1: PREPARACIÓN - Agrupar mappings por tabla y preparar metadata
        # ============================================================================

        # Agrupar mappings por tabla de destino
        table_mappings: Dict[str, List[Dict]] = {}

        for mapping in mappings:
            try:
                dest_table = MigrationScriptService._resolve_name(
                    mapping=mapping, side="destination", adapter=dest_adapter
                )

                if dest_table not in table_mappings:
                    table_mappings[dest_table] = []

                table_mappings[dest_table].append(mapping)

            except HashNotFoundError as e:
                logger.error(f"Hash not found in mapping preparation: {str(e)}")
                # Continuamos con los demás mappings

        # Obtener lista de tablas únicas
        all_tables = list(table_mappings.keys())

        # Aplicar orden de dependencias si se proporcionó
        if dependency_order:
            # Ordenar tablas según el orden topológico
            ordered_tables = [t for t in dependency_order if t in all_tables]
            # Agregar tablas que no están en dependency_order al final
            remaining_tables = [t for t in all_tables if t not in ordered_tables]
            all_tables = ordered_tables + remaining_tables

        # ============================================================================
        # FASE 2: HEADER - Generar header del script con metadata
        # ============================================================================

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
        lines.append("")

        # ============================================================================
        # FASE 3: TRANSACTION BEGIN
        # ============================================================================

        begin_stmt, commit_stmt = MigrationScriptService._generate_transaction_wrapper(dialect)
        lines.append("-- SECTION 1: Transaction Start")
        lines.append(begin_stmt)
        lines.append("")

        # ============================================================================
        # FASE 4: DISABLE CONSTRAINTS
        # ============================================================================

        if include_constraints and all_tables:
            lines.append("-- SECTION 2: Disable Constraints")
            constraint_sql = MigrationScriptService._generate_constraint_disabling(
                all_tables, dialect
            )
            lines.append(constraint_sql)
            lines.append("")

        # ============================================================================
        # FASE 5: DATA MIGRATION - Generar INSERTs por tabla
        # ============================================================================

        lines.append("-- SECTION 3: Data Migration (in dependency order)")
        lines.append("")

        table_stats = {}  # Para tracking de rows por tabla

        for table_idx, dest_table in enumerate(all_tables, start=1):
            table_mapping_list = table_mappings[dest_table]

            lines.append(f"-- Table {table_idx}/{len(all_tables)}: {sanitize_comment(dest_table)}")

            try:
                # Preparar columnas y valores para el INSERT
                dest_columns = []
                select_expressions = []

                for mapping in table_mapping_list:
                    # Resolver nombres
                    origin_table = MigrationScriptService._resolve_name(
                        mapping=mapping, side="origin", adapter=origin_adapter
                    )

                    origin_column = MigrationScriptService._resolve_name(
                        mapping=mapping, side="origin", adapter=origin_adapter, is_column=True
                    )

                    dest_column = MigrationScriptService._resolve_name(
                        mapping=mapping, side="destination", adapter=dest_adapter, is_column=True
                    )

                    # Obtener tipos (si están disponibles)
                    origin_type = mapping.get("origin_data_type")
                    dest_type = mapping.get("destination_data_type")

                    # Obtener transformación (campo encriptado que el CRUD ya descifró)
                    transformation_logic = mapping.get("transformation_logic")

                    # Aplicar transformación o conversión de tipos
                    select_expr = MigrationScriptService._apply_transformation(
                        column_name=origin_column,
                        transformation_logic=transformation_logic,
                        origin_type=origin_type,
                        dest_type=dest_type,
                        dialect=dialect,
                    )

                    dest_columns.append(dest_column)
                    select_expressions.append(select_expr)

                # IMPORTANTE: Asumir que todos los mappings de una tabla vienen de la misma tabla origen
                # (esto es una simplificación, en un caso real podríamos tener múltiples orígenes)
                first_mapping = table_mapping_list[0]
                origin_table = MigrationScriptService._resolve_name(
                    mapping=first_mapping, side="origin", adapter=origin_adapter
                )

                # Construir SELECT clause
                select_clause = (
                    f"SELECT {', '.join(select_expressions)} "
                    f"FROM {quote_identifier(origin_table, dialect)}"
                )

                # Obtener row count real del adapter si está disponible
                estimated_rows = None
                if origin_adapter:
                    try:
                        stats = origin_adapter.get_table_statistics(origin_table)
                        estimated_rows = stats.row_count
                    except Exception as e:
                        logger.warning(f"Could not get row count for {origin_table}: {e}")

                use_batching = estimated_rows is not None and estimated_rows > batch_size

                if use_batching:
                    # Generar INSERT con batching para tablas grandes
                    lines.append(
                        f"-- Large table - using batching (estimated rows: {estimated_rows})"
                    )
                    batched_insert = MigrationScriptService._generate_batched_insert(
                        table_name=dest_table,
                        columns=dest_columns,
                        select_clause=select_clause,
                        total_rows=estimated_rows,
                        batch_size=batch_size,
                        dialect=dialect,
                    )
                    lines.append(batched_insert)
                else:
                    # INSERT simple sin batching
                    quoted_columns = [quote_identifier(c, dialect) for c in dest_columns]
                    lines.append(
                        f"INSERT INTO {quote_identifier(dest_table, dialect)} "
                        f"({', '.join(quoted_columns)})"
                    )
                    lines.append(select_clause + ";")

                table_stats[dest_table] = len(table_mapping_list)
                lines.append("")

            except HashNotFoundError as e:
                logger.error(f"Hash not found for table {dest_table}: {str(e)}")
                lines.append(f"-- ERROR: {sanitize_comment(str(e))}")
                lines.append("")

        # ============================================================================
        # FASE 6: ENABLE CONSTRAINTS
        # ============================================================================

        if include_constraints and all_tables:
            lines.append("-- SECTION 4: Enable Constraints")
            constraint_sql = MigrationScriptService._generate_constraint_enabling(
                all_tables, dialect
            )
            lines.append(constraint_sql)
            lines.append("")

        # ============================================================================
        # FASE 7: VALIDATION QUERIES
        # ============================================================================

        if include_validation and all_tables:
            lines.append("-- SECTION 5: Validation")
            for table_name in all_tables:
                columns_count = table_stats.get(table_name, 0)
                lines.append(
                    f"SELECT {quote_literal(table_name, dialect)} AS table_name, "
                    f"COUNT(*) AS row_count FROM {quote_identifier(table_name, dialect)};"
                )
            lines.append("")

        # ============================================================================
        # FASE 8: TRANSACTION COMMIT
        # ============================================================================

        lines.append("-- SECTION 6: Transaction Commit")
        lines.append(commit_stmt)
        lines.append("")

        lines.append("-- ========================================")
        lines.append("-- MIGRATION COMPLETE")
        lines.append(f"-- Total tables migrated: {len(all_tables)}")
        lines.append("-- ========================================")

        return "\n".join(lines)

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
    def _generate_constraint_disabling(tables: List[str], dialect: str) -> str:
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
                lines.append(
                    f"ALTER TABLE {quote_identifier(table, dialect_lower)} DISABLE TRIGGER ALL;"
                )
        elif dialect_lower == "mysql":
            lines.append("-- Disable foreign key checks")
            lines.append("SET FOREIGN_KEY_CHECKS=0;")
            lines.append("SET AUTOCOMMIT=0;")
        elif dialect_lower == "sqlserver":
            lines.append("-- Disable constraints")
            for table in tables:
                lines.append(
                    f"ALTER TABLE {quote_identifier(table, dialect_lower)} NOCHECK CONSTRAINT ALL;"
                )
        elif dialect_lower == "oracle":
            lines.append("-- Disable triggers")
            for table in tables:
                lines.append(
                    f"ALTER TABLE {quote_identifier(table, dialect_lower)} DISABLE ALL TRIGGERS;"
                )
        else:
            logger.warning(f"Unknown dialect '{dialect}', skipping constraint disabling")

        return "\n".join(lines)

    @staticmethod
    def _generate_constraint_enabling(tables: List[str], dialect: str) -> str:
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
                lines.append(
                    f"ALTER TABLE {quote_identifier(table, dialect_lower)} ENABLE TRIGGER ALL;"
                )
        elif dialect_lower == "mysql":
            lines.append("-- Enable foreign key checks")
            lines.append("SET FOREIGN_KEY_CHECKS=1;")
        elif dialect_lower == "sqlserver":
            lines.append("-- Enable constraints")
            for table in tables:
                lines.append(
                    f"ALTER TABLE {quote_identifier(table, dialect_lower)} CHECK CONSTRAINT ALL;"
                )
        elif dialect_lower == "oracle":
            lines.append("-- Enable triggers")
            for table in tables:
                lines.append(
                    f"ALTER TABLE {quote_identifier(table, dialect_lower)} ENABLE ALL TRIGGERS;"
                )
        else:
            logger.warning(f"Unknown dialect '{dialect}', skipping constraint enabling")

        return "\n".join(lines)

    @staticmethod
    def _apply_transformation(
        column_name: str,
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
        column_name = quote_identifier(column_name, dialect)

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
        table_name: str,
        columns: List[str],
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
        columns_str = ", ".join(quote_identifier(c, dialect_lower) for c in columns)
        routine_suffix = safe_routine_suffix(table_name)
        table_name = quote_identifier(table_name, dialect_lower)
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
