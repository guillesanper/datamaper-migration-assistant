"""
Execution Service

Ejecuta scripts SQL de migración contra la base de datos destino con:
- Manejo de transacciones (COMMIT/ROLLBACK): todo el script es atómico
- Tracking de progreso en migration_executions (vía CRUD ORM)
- Modo dry-run (ejecuta pero hace ROLLBACK al final)
- Logging detallado de cada paso

Created: 2025-01-17
"""

import hashlib
import json
import logging
import re
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

from app.crud import migration_script_crud
from app.services.data_copy_service import DataCopyService, disable_autocommit
from app.services.migration_script_service import TablePlan
from app.utils.db_adapters.base_adapter import BaseDBAdapter
from app.utils.sql_safety import is_transaction_control, split_sql_statements

logger = logging.getLogger(__name__)


class ExecutionServiceError(Exception):
    """Base exception for ExecutionService"""

    pass


FINISHED_STATUSES = ("success", "failed", "dry_run_complete")


def execution_progress(execution: Dict[str, Any]) -> Dict[str, Any]:
    """
    Progreso de una ejecución a partir de su execution_log.

    Returns:
        {"progress_percent": int, "current_step": str}
    """
    raw_log = execution.get("execution_log") or []
    log = json.loads(raw_log) if isinstance(raw_log, str) else raw_log

    if execution.get("status") in FINISHED_STATUSES:
        progress_percent = 100
    else:
        # El primer entry de metadata trae el total de sentencias
        total_statements = next(
            (e.get("total_statements") for e in log if e.get("type") == "metadata"), None
        )
        completed = len([e for e in log if e.get("step", 0) > 0 and e.get("status") == "success"])
        if total_statements and total_statements > 0:
            progress_percent = min(int((completed / total_statements) * 100), 99)
        else:
            progress_percent = 0

    current_step = "Initializing..."
    step_entries = [e for e in log if e.get("step", 0) > 0]
    if step_entries:
        last_step = step_entries[-1]
        current_step = f"Step {last_step.get('step', 0)}: {last_step.get('table', 'Unknown')}"

    return {"progress_percent": progress_percent, "current_step": current_step}


class ExecutionService:
    """
    Servicio de ejecución de scripts de migración.

    Responsabilidades:
    - Ejecutar scripts SQL contra BD destino
    - Manejar transacciones (COMMIT en éxito, ROLLBACK en error)
    - Tracking de progreso en migration_executions
    - Modo dry-run para testing

    Nota sobre backups: no se hace copia de la BD destino. La protección ante fallos
    es la transacción (un error revierte todo el script). La versión anterior volcaba
    a disco, sin cifrar, tablas de la BD de la aplicación (de todos los proyectos), lo
    que no protegía el destino y exponía datos de otros clientes.

    Usage:
        service = ExecutionService()
        result = service.execute_migration(
            db=db,
            project_id='uuid',
            script='SQL script...',
            dest_adapter=dest_adapter,
            dry_run=False
        )
    """

    def execute_migration(
        self,
        db_connection,
        project_id: str,
        script: str,
        dest_adapter: BaseDBAdapter,
        dry_run: bool = False,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta script de migración contra BD destino.

        Flujo:
        1. Crear registro en migration_executions (status='running')
        2. Ejecutar script statement por statement con dest_adapter, en una transacción
        3. Si dry_run=True: ROLLBACK al final
        4. Si error durante ejecución: ROLLBACK + marcar status='failed'
        5. Si éxito: COMMIT + marcar status='success'
        6. Guardar execution_log con cada paso

        Args:
            db_connection: SQLAlchemy Session de la BD de la aplicación (migration_executions)
            project_id: UUID del proyecto
            script: Script SQL a ejecutar
            dest_adapter: Adapter conectado a la BD destino
            dry_run: Si True, ejecuta pero hace ROLLBACK al final
            user_id: UUID del usuario que ejecuta (opcional)

        Returns:
            {
                'execution_id': uuid,
                'status': 'success' | 'failed' | 'dry_run_complete',
                'rows_affected': 35000,
                'duration_seconds': 42.5,
                'backup_id': None,
                'errors': [],
                'execution_log': [
                    {'step': 1, 'table': 'customers', 'rows': 10000, 'duration': 2.5},
                    {'step': 2, 'table': 'orders', 'rows': 25000, 'duration': 5.2}
                ]
            }
        """
        return self._run_tracked(
            db_connection=db_connection,
            project_id=project_id,
            record_text=script,
            user_id=user_id,
            dry_run=dry_run,
            run=lambda: self._execute_script(adapter=dest_adapter, script=script, dry_run=dry_run),
        )

    def execute_copy(
        self,
        db_connection,
        project_id: str,
        plans: List[TablePlan],
        origin_adapter: BaseDBAdapter,
        dest_adapter: BaseDBAdapter,
        dry_run: bool = False,
        user_id: Optional[str] = None,
        batch_size: int = 10000,
        include_constraints: bool = True,
        include_validation: bool = True,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Migración entre dos BDs distintas: copia por lotes del origen al destino.

        Mismo registro de ejecución y formato de respuesta que execute_migration; el
        "script" registrado es la descripción del plan (DataCopyService.describe).
        """
        copier = DataCopyService(origin_adapter, dest_adapter, batch_size=batch_size)
        plan_text = copier.describe(
            plans,
            project_name=project_name,
            include_constraints=include_constraints,
            include_validation=include_validation,
        )
        return self._run_tracked(
            db_connection=db_connection,
            project_id=project_id,
            record_text=plan_text,
            user_id=user_id,
            dry_run=dry_run,
            run=lambda: copier.copy(
                plans,
                dry_run=dry_run,
                include_constraints=include_constraints,
                include_validation=include_validation,
            ),
        )

    def _run_tracked(
        self,
        db_connection,
        project_id: str,
        record_text: str,
        user_id: Optional[str],
        dry_run: bool,
        run: Callable[[], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Crea el registro de ejecución, ejecuta `run` y guarda el resultado o el error."""
        start_time = time.time()
        execution_id = None
        errors = []

        try:
            # PASO 1: Crear registro de ejecución
            logger.info(f"Starting migration execution for project {project_id}")
            execution_id = self._create_execution_record(
                db_connection=db_connection,
                project_id=project_id,
                script=record_text,
                user_id=user_id,
            )

            # PASO 2: Ejecutar (transacción única en la BD destino)
            logger.info(f"Executing migration (dry_run={dry_run})")
            execution_result = run()

            # PASO 3: Determinar status final
            if dry_run:
                final_status = "dry_run_complete"
                logger.info("Dry-run completed successfully (ROLLBACK executed)")
            else:
                final_status = "success"
                logger.info("Migration completed successfully (COMMIT executed)")

            # PASO 4: Actualizar registro con éxito
            self._update_execution_record(
                db_connection=db_connection,
                execution_id=execution_id,
                status=final_status,
                rows_migrated=execution_result["rows_affected"],
                execution_log=execution_result["log"],
            )

            duration = time.time() - start_time

            return {
                "execution_id": execution_id,
                "status": final_status,
                "rows_affected": execution_result["rows_affected"],
                "duration_seconds": round(duration, 2),
                "backup_id": None,
                "errors": [],
                "execution_log": execution_result["log"],
            }

        except Exception as e:
            # PASO 5: Manejar error
            logger.error(f"Migration execution failed: {str(e)}")
            logger.error(traceback.format_exc())

            error_message = f"{type(e).__name__}: {str(e)}"
            errors.append(error_message)

            # Actualizar registro con error
            if execution_id:
                try:
                    self._update_execution_record(
                        db_connection=db_connection,
                        execution_id=execution_id,
                        status="failed",
                        rows_migrated=0,
                        error_message=error_message,
                    )
                except Exception as update_error:
                    logger.error(
                        f"Could not mark execution {execution_id} as failed: {update_error}"
                    )

            duration = time.time() - start_time

            return {
                "execution_id": execution_id,
                "status": "failed",
                "rows_affected": 0,
                "duration_seconds": round(duration, 2),
                "backup_id": None,
                "errors": errors,
                "execution_log": [],
            }

    def _create_execution_record(
        self, db_connection, project_id: str, script: str, user_id: Optional[str]
    ) -> str:
        """
        Crea registro en migration_executions (status='running'), retorna execution_id.

        Args:
            db_connection: SQLAlchemy Session
            project_id: UUID del proyecto
            script: Script SQL completo
            user_id: UUID del usuario (opcional)

        Returns:
            execution_id (UUID como string)
        """
        script_hash = hashlib.sha256(script.encode("utf-8")).hexdigest()

        execution = migration_script_crud.create_migration_execution_orm(
            db_connection,
            project_id=project_id,
            script_hash=script_hash,
            created_by=str(user_id) if user_id else None,
        )
        execution_id = str(execution["id"])

        migration_script_crud.update_execution_status_orm(
            db_connection, execution_id, status="running", mark_started=True
        )
        logger.info(f"Created execution record: {execution_id}")
        return execution_id

    def _execute_script(self, adapter: BaseDBAdapter, script: str, dry_run: bool) -> Dict[str, Any]:
        """
        Ejecuta script SQL statement por statement.

        Parsea script para identificar:
        - BEGIN/COMMIT statements
        - INSERT statements (contar rows affected)
        - Comentarios (ignorar)

        Args:
            adapter: BaseDBAdapter conectado a la BD destino
            script: Script SQL completo
            dry_run: Si True, hace ROLLBACK al final

        Returns:
            {
                'rows_affected': 35000,
                'duration': 42.5,
                'log': [{'step': 1, 'sql': 'INSERT ...', 'rows': 10000, 'duration': 2.5}]
            }

        Raises:
            ExecutionServiceError: Si falla algún statement
        """
        start_time = time.time()
        total_rows_affected = 0
        execution_log: List[Any] = []

        # Obtener cursor de la conexión del adapter
        if not adapter.is_connected:
            raise ExecutionServiceError("Adapter is not connected to destination database")

        connection = adapter.connection
        assert connection is not None, "Adapter connection is None"

        # La transacción la controla este servicio (COMMIT/ROLLBACK al final), nunca
        # el script: sin esto un dry-run podría persistir cambios
        self._disable_autocommit(connection)
        cursor = connection.cursor()

        try:
            # Parsear script en statements individuales
            statements = self._parse_sql_script(script, dialect=self._adapter_dialect(adapter))

            # Filtrar statements ejecutables: el control de transacciones del script
            # (BEGIN/COMMIT/ROLLBACK/...) se ignora para no romper el dry-run
            executable_statements = [s for s in statements if not is_transaction_control(s)]
            total_statements = len(executable_statements)

            logger.info(
                f"Parsed {len(statements)} SQL statements from script ({total_statements} executable)"
            )

            # Guardar metadata de ejecución como primer entrada del log
            execution_log.append(
                {
                    "step": 0,
                    "type": "metadata",
                    "total_statements": total_statements,
                }
            )

            # Ejecutar cada statement
            for idx, stmt in enumerate(statements, start=1):
                stmt_start = time.time()

                if is_transaction_control(stmt):
                    logger.info(f"Skipping transaction control statement {idx}: {stmt[:50]}")
                    continue

                try:
                    # Ejecutar statement
                    logger.debug(f"Executing statement {idx}: {stmt[:100]}...")
                    cursor.execute(stmt)

                    # Contar rows affected (si aplica)
                    rows_affected = cursor.rowcount if cursor.rowcount > 0 else 0
                    total_rows_affected += rows_affected

                    # Detectar tabla del statement (si es INSERT)
                    table_name = self._extract_table_name(stmt)

                    stmt_duration = time.time() - stmt_start

                    execution_log.append(
                        {
                            "step": idx,
                            "table": table_name,
                            "sql_preview": stmt[:200],  # Preview para debugging
                            "rows": rows_affected,
                            "duration": round(stmt_duration, 3),
                            "status": "success",
                        }
                    )

                    logger.info(
                        f"Statement {idx} executed: {rows_affected} rows affected "
                        f"(table: {table_name}, duration: {stmt_duration:.2f}s)"
                    )

                except Exception as e:
                    logger.error(f"Error executing statement {idx}: {str(e)}")
                    execution_log.append(
                        {
                            "step": idx,
                            "sql_preview": stmt[:200],
                            "error": str(e),
                            "status": "failed",
                        }
                    )
                    raise ExecutionServiceError(f"Failed at statement {idx}: {str(e)}")

            # Determinar si hacer COMMIT o ROLLBACK
            if dry_run:
                logger.info("DRY-RUN mode: Rolling back all changes")
                connection.rollback()
            else:
                logger.info(f"Committing {total_rows_affected} rows to database")
                connection.commit()

            duration = time.time() - start_time

            return {
                "rows_affected": total_rows_affected,
                "duration": round(duration, 2),
                "log": execution_log,
            }

        except Exception as e:
            # Rollback en caso de error
            logger.error(f"Execution failed, rolling back: {str(e)}")
            connection.rollback()
            raise

        finally:
            cursor.close()

    def _parse_sql_script(self, script: str, dialect: str = "postgresql") -> List[str]:
        """
        Parsea script SQL en statements individuales.

        Respeta literales, identificadores citados, comentarios, bloques DO $$ de
        PostgreSQL y bloques PL/SQL de Oracle (ver sql_safety.split_sql_statements).

        Args:
            script: Script SQL completo
            dialect: Dialecto SQL del script

        Returns:
            Lista de statements SQL (sin comentarios)
        """
        return split_sql_statements(script, dialect)

    @staticmethod
    def _adapter_dialect(adapter: BaseDBAdapter) -> str:
        dialect = getattr(adapter, "dialect", None)
        return dialect if isinstance(dialect, str) else "postgresql"

    @staticmethod
    def _disable_autocommit(connection) -> None:
        """Desactiva autocommit en la conexión destino (psycopg2, pyodbc, pymysql, oracledb)."""
        disable_autocommit(connection)

    def _extract_table_name(self, statement: str) -> Optional[str]:
        """
        Extrae el nombre de la tabla de un statement INSERT.

        Args:
            statement: Statement SQL

        Returns:
            Nombre de la tabla o None si no se detecta

        Examples:
            "INSERT INTO customers ..." → "customers"
            "INSERT INTO public.orders ..." → "orders"
        """
        # Pattern para INSERT INTO
        insert_pattern = r"INSERT\s+INTO\s+([a-zA-Z0-9_\.]+)"
        match = re.search(insert_pattern, statement, re.IGNORECASE)

        if match:
            table_full = match.group(1)
            # Si tiene schema (public.table), extraer solo el nombre
            if "." in table_full:
                return table_full.split(".")[-1]
            return table_full

        return None

    def _update_execution_record(
        self,
        db_connection,
        execution_id: str,
        status: str,
        rows_migrated: int = 0,
        execution_log: Optional[List[Dict]] = None,
        error_message: Optional[str] = None,
    ):
        """
        Actualiza registro en migration_executions y lo marca como completado.

        Args:
            db_connection: SQLAlchemy Session
            execution_id: UUID del execution record
            status: Nuevo status ('success', 'failed', 'dry_run_complete', etc.)
            rows_migrated: Total de filas migradas
            execution_log: Log de ejecución (lista de dicts)
            error_message: Mensaje de error (si aplica)
        """
        migration_script_crud.update_execution_status_orm(
            db_connection,
            execution_id,
            status=status,
            rows_migrated=rows_migrated,
            execution_log=execution_log,
            error_message=error_message,
            mark_completed=True,
        )
        logger.info(
            f"Updated execution record {execution_id}: status={status}, rows={rows_migrated}"
        )

    def get_execution_status(self, db_connection, execution_id: str) -> Dict[str, Any]:
        """
        Consulta estado de una ejecución.

        Args:
            db_connection: SQLAlchemy Session
            execution_id: UUID del execution record

        Raises:
            ExecutionServiceError: Si no se encuentra el execution record
        """
        execution = migration_script_crud.get_migration_execution_orm(db_connection, execution_id)
        if not execution:
            raise ExecutionServiceError(f"Execution record {execution_id} not found")

        started_at = execution.get("started_at")
        completed_at = execution.get("completed_at")
        return {
            "execution_id": str(execution["id"]),
            "status": execution.get("status"),
            **execution_progress(execution),
            "rows_migrated": execution.get("rows_migrated") or 0,
            "started_at": started_at.isoformat() if started_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
            "error_message": execution.get("error_message"),
        }
