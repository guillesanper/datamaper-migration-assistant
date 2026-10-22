"""
Data Copy Service

Migración entre dos bases de datos distintas: lee del origen y escribe en el destino
por lotes con INSERT parametrizados.

El script de MigrationScriptService (INSERT INTO destino SELECT ... FROM origen) se
ejecuta en una sola conexión, así que solo funciona cuando origen y destino son la
misma BD. Aquí se parte de los mismos planes (MigrationScriptService.build_table_plans):

- Origen: un SELECT por tabla (columnas citadas o la transformation_logic validada) en
  una transacción de solo lectura, leído en streaming (cursor de servidor en PostgreSQL).
- Destino: INSERT ... VALUES con placeholders del driver (los datos nunca se interpolan
  en el SQL), conversión de tipo con CAST(placeholder AS tipo validado) cuando el tipo
  origen y destino difieren, todo en una única transacción (COMMIT al final, ROLLBACK si
  falla algo o en dry-run).
"""

import logging
import time
import uuid
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from app.services.migration_script_service import ColumnPlan, MigrationScriptService, TablePlan
from app.utils.db_adapters.base_adapter import BaseDBAdapter
from app.utils.sql_safety import (
    is_transaction_control,
    sanitize_comment,
    split_sql_statements,
    validate_sql_expression,
    validate_sql_type,
)

logger = logging.getLogger(__name__)

# Marca de los scripts que describen una copia entre BDs (no ejecutables como SQL)
COPY_PLAN_MARKER = "-- DATAMAP CROSS-DATABASE COPY PLAN"

# Transacción de solo lectura en el origen: la transformation_logic se evalúa allí
_READ_ONLY_TRANSACTION = {
    "postgresql": "SET TRANSACTION READ ONLY",
    "mysql": "START TRANSACTION READ ONLY",
    "oracle": "SET TRANSACTION READ ONLY",
}


class DataCopyError(Exception):
    """Fallo durante la copia entre BDs"""

    pass


def _placeholder(dialect: str, position: int) -> str:
    """Placeholder del driver: psycopg2/pymysql %s, pyodbc ?, oracledb :n"""
    if dialect == "sqlserver":
        return "?"
    if dialect == "oracle":
        return f":{position}"
    return "%s"


def disable_autocommit(connection) -> None:
    """Desactiva autocommit (psycopg2, pyodbc, pymysql, oracledb)."""
    autocommit = getattr(connection, "autocommit", None)
    if autocommit is False:
        # Ya desactivado; psycopg2 no permite reasignarlo con una transacción abierta
        # (p. ej. tras las queries de metadata que resuelven los mappings)
        return
    if callable(autocommit):
        # pymysql expone autocommit como método
        autocommit(False)
    else:
        connection.autocommit = False


class DataCopyService:
    """Copia los datos de unos planes de tabla del adapter origen al destino."""

    def __init__(
        self, origin_adapter: BaseDBAdapter, dest_adapter: BaseDBAdapter, batch_size: int = 10000
    ):
        self.origin = origin_adapter
        self.dest = dest_adapter
        self.batch_size = batch_size

    # =========================================================================
    # SQL
    # =========================================================================

    def build_select(self, plan: TablePlan) -> str:
        """SELECT en el dialecto del origen (transformación aplicada en origen)."""
        dialect = self.origin.dialect
        expressions = []
        for column in plan.columns:
            quoted = column.origin.render(dialect)
            if column.transformation_logic:
                validate_sql_expression(column.transformation_logic)
                expressions.append(column.transformation_logic.replace("{column}", quoted))
            else:
                expressions.append(quoted)
        return f"SELECT {', '.join(expressions)} FROM {plan.origin.render(dialect)}"

    def build_insert(self, plan: TablePlan) -> str:
        """INSERT parametrizado en el dialecto del destino."""
        dialect = self.dest.dialect
        values = [
            self._value_expression(column, _placeholder(dialect, position))
            for position, column in enumerate(plan.columns, start=1)
        ]
        columns = ", ".join(column.dest.render(dialect) for column in plan.columns)
        return f"INSERT INTO {plan.dest.render(dialect)} ({columns}) VALUES ({', '.join(values)})"

    @staticmethod
    def _value_expression(column: ColumnPlan, placeholder: str) -> str:
        # Con transformación, el valor ya sale convertido del origen
        if (
            not column.transformation_logic
            and column.origin_type
            and column.dest_type
            and column.origin_type.upper() != column.dest_type.upper()
        ):
            return f"CAST({placeholder} AS {validate_sql_type(column.dest_type)})"
        return placeholder

    def describe(
        self,
        plans: List[TablePlan],
        project_name: Optional[str] = None,
        include_constraints: bool = True,
        include_validation: bool = True,
    ) -> str:
        """Texto del plan (se guarda como script y en migration_executions)."""
        lines = [
            COPY_PLAN_MARKER,
            "-- Executed by DataMap: rows are read from the origin connection and inserted",
            "-- into the destination in batches, in a single destination transaction.",
            "-- This text documents the plan; it is not meant to be run as a SQL script.",
        ]
        if project_name:
            lines.append(f"-- Project: {sanitize_comment(project_name)}")
        lines.append(f"-- Origin dialect: {self.origin.dialect}")
        lines.append(f"-- Destination dialect: {self.dest.dialect}")
        lines.append(f"-- Batch size: {self.batch_size}")
        lines.append(f"-- Constraints disabled during copy: {include_constraints}")
        lines.append(f"-- Validation counts: {include_validation}")
        lines.append("")
        for idx, plan in enumerate(plans, start=1):
            lines.append(f"-- Table {idx}/{len(plans)}: {sanitize_comment(str(plan.dest))}")
            lines.append(f"-- [origin]      {self.build_select(plan)}")
            lines.append(f"-- [destination] {self.build_insert(plan)}")
            lines.append("")
        return "\n".join(lines)

    # =========================================================================
    # EJECUCIÓN
    # =========================================================================

    def copy(
        self,
        plans: List[TablePlan],
        dry_run: bool = False,
        include_constraints: bool = True,
        include_validation: bool = True,
    ) -> Dict[str, Any]:
        """
        Copia todas las tablas en una transacción del destino.

        Returns:
            {'rows_affected': int, 'duration': float, 'log': [...]} (mismo formato que
            ExecutionService._execute_script)

        Raises:
            DataCopyError: Si falla la lectura o la escritura (el destino queda intacto)
        """
        if not self.origin.is_connected or not self.dest.is_connected:
            raise DataCopyError("Origin and destination adapters must be connected")

        start_time = time.time()
        dest_connection = self.dest.connection
        disable_autocommit(dest_connection)
        dest_cursor = dest_connection.cursor()

        tables = [plan.dest for plan in plans]
        log: List[Dict[str, Any]] = [
            {"step": 0, "type": "metadata", "mode": "cross_database_copy", "tables": len(plans)}
        ]

        try:
            if include_constraints and tables:
                self._run_dest_statements(
                    dest_cursor,
                    MigrationScriptService._generate_constraint_disabling(
                        tables, self.dest.dialect
                    ),
                )

            total_rows = self._copy_tables(plans, dest_cursor, log)

            if include_constraints and tables:
                self._run_dest_statements(
                    dest_cursor,
                    MigrationScriptService._generate_constraint_enabling(tables, self.dest.dialect),
                )

            if include_validation:
                log.extend(self._validation_counts(dest_cursor, tables))

            if dry_run:
                logger.info("DRY-RUN mode: Rolling back all copied rows")
                dest_connection.rollback()
            else:
                logger.info(f"Committing {total_rows} copied rows")
                dest_connection.commit()

            return {
                "rows_affected": total_rows,
                "duration": round(time.time() - start_time, 2),
                "log": log,
            }

        except Exception:
            dest_connection.rollback()
            raise

        finally:
            dest_cursor.close()
            self._end_origin_transaction()

    def _copy_tables(self, plans: List[TablePlan], dest_cursor, log: List[Dict[str, Any]]) -> int:
        """Copia cada tabla en orden, registrando filas y duración en el log."""
        total_rows = 0
        for step, plan in enumerate(plans, start=1):
            table_start = time.time()
            try:
                rows = self._copy_table(plan, dest_cursor)
            except Exception as e:
                log.append(
                    {"step": step, "table": str(plan.dest), "error": str(e), "status": "failed"}
                )
                raise DataCopyError(f"Failed copying table '{plan.dest}': {e}") from e

            total_rows += rows
            log.append(
                {
                    "step": step,
                    "type": "copy",
                    "table": str(plan.dest),
                    "rows": rows,
                    "duration": round(time.time() - table_start, 3),
                    "status": "success",
                }
            )
            logger.info(f"Copied {rows} rows into {plan.dest}")
        return total_rows

    def _validation_counts(self, cursor, tables) -> List[Dict[str, Any]]:
        """Filas de cada tabla destino tras la copia (dentro de la transacción)."""
        entries = []
        for table in tables:
            cursor.execute(MigrationScriptService.validation_query(table, self.dest.dialect))
            row = cursor.fetchone()
            count = list(row.values())[-1] if isinstance(row, dict) else row[-1]
            entries.append({"type": "validation", "table": str(table), "rows": int(count or 0)})
        return entries

    def _copy_table(self, plan: TablePlan, dest_cursor) -> int:
        insert_sql = self.build_insert(plan)
        rows = 0
        for batch in self._iter_origin_batches(self.build_select(plan)):
            self._insert_batch(dest_cursor, insert_sql, batch)
            rows += len(batch)
        return rows

    def _run_dest_statements(self, cursor, script: str) -> None:
        for statement in split_sql_statements(script, self.dest.dialect):
            # SET AUTOCOMMIT=0 (MySQL) y similares: la transacción la lleva este servicio
            if not is_transaction_control(statement):
                cursor.execute(statement)

    def _start_origin_read_only(self) -> None:
        connection = self.origin.connection
        # Terminar la transacción implícita de las queries de metadata: SET TRANSACTION
        # tiene que ser la primera sentencia
        connection.rollback()
        disable_autocommit(connection)
        statement = _READ_ONLY_TRANSACTION.get(self.origin.dialect)
        if statement:
            cursor = connection.cursor()
            try:
                cursor.execute(statement)
            finally:
                cursor.close()

    def _end_origin_transaction(self) -> None:
        try:
            self.origin.connection.rollback()
        except Exception as e:
            logger.warning(f"Could not end origin read transaction: {e}")

    def _iter_origin_batches(self, query: str) -> Iterator[List[Tuple[Any, ...]]]:
        """Filas del origen en lotes de batch_size, sin cargar la tabla entera en memoria."""
        self._start_origin_read_only()
        cursor = self._open_origin_cursor()
        try:
            cursor.execute(query)
            while True:
                batch = cursor.fetchmany(self.batch_size)
                if not batch:
                    break
                yield [self._as_tuple(row) for row in batch]
        finally:
            cursor.close()

    def _open_origin_cursor(self):
        connection = self.origin.connection
        if self.origin.dialect == "postgresql":
            import psycopg2.extensions

            # Cursor de servidor: psycopg2 descarga el resultado entero con un cursor normal
            cursor = connection.cursor(
                name=f"datamap_copy_{uuid.uuid4().hex}",
                cursor_factory=psycopg2.extensions.cursor,
            )
            cursor.itersize = self.batch_size
            return cursor
        return connection.cursor()

    @staticmethod
    def _as_tuple(row: Any) -> Tuple[Any, ...]:
        return tuple(row.values()) if isinstance(row, dict) else tuple(row)

    def _insert_batch(self, cursor, sql: str, rows: Sequence[Tuple[Any, ...]]) -> None:
        if self.dest.dialect == "postgresql":
            import psycopg2.extras

            # executemany de psycopg2 hace un round-trip por fila
            psycopg2.extras.execute_batch(cursor, sql, rows, page_size=len(rows))
            return
        if self.dest.dialect == "sqlserver":
            cursor.fast_executemany = True
        cursor.executemany(sql, rows)
