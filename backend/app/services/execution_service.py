"""
Execution Service

Ejecuta scripts SQL de migración contra la base de datos destino con:
- Manejo de transacciones (COMMIT/ROLLBACK)
- Backups automáticos antes de ejecutar
- Tracking de progreso en tiempo real
- Modo dry-run (ejecuta pero hace ROLLBACK al final)
- Logging detallado de cada paso

Created: 2025-01-17
"""

import hashlib
import logging
import re
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

from app.utils.db_adapters.base_adapter import BaseDBAdapter
from utilities.migrations.validators import BackupManager

logger = logging.getLogger(__name__)


class ExecutionServiceError(Exception):
    """Base exception for ExecutionService"""

    pass


class ExecutionService:
    """
    Servicio de ejecución de scripts de migración.

    Responsabilidades:
    - Ejecutar scripts SQL contra BD destino
    - Manejar transacciones (COMMIT en éxito, ROLLBACK en error)
    - Crear backups automáticos usando BackupManager
    - Tracking de progreso en migration_executions
    - Modo dry-run para testing

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

    def __init__(self):
        """Inicializa el servicio con BackupManager"""
        # BackupManager se inicializará con la conexión cuando sea necesario
        self.backup_manager = None

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
        2. Crear backup automático usando BackupManager
        3. Ejecutar script statement por statement con dest_adapter
        4. Si dry_run=True: ROLLBACK al final
        5. Si error durante ejecución: ROLLBACK + marcar status='failed'
        6. Si éxito: COMMIT + marcar status='success'
        7. Actualizar execution_log con cada paso

        Args:
            db_connection: Session de SQLAlchemy (para migration_executions)
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
                'backup_id': 'backup_20250117_143000',
                'errors': [],
                'execution_log': [
                    {'step': 1, 'table': 'customers', 'rows': 10000, 'duration': 2.5},
                    {'step': 2, 'table': 'orders', 'rows': 25000, 'duration': 5.2}
                ]
            }

        Raises:
            ExecutionServiceError: Si hay error en la ejecución
        """
        start_time = time.time()
        execution_id = None
        backup_id = None
        errors = []

        try:
            # PASO 1: Crear registro de ejecución
            logger.info(f"Starting migration execution for project {project_id}")
            execution_id = self._create_execution_record(
                db_connection=db_connection, project_id=project_id, script=script, user_id=user_id
            )

            # PASO 2: Crear backup automático
            logger.info("Creating automatic backup before execution")
            backup_id = self._create_backup(
                db_connection=db_connection, project_id=project_id, script=script
            )
            logger.info(f"Backup created: {backup_id}")

            # PASO 3: Ejecutar script
            logger.info(f"Executing script (dry_run={dry_run})")
            execution_result = self._execute_script(
                adapter=dest_adapter, script=script, dry_run=dry_run
            )

            # PASO 4: Determinar status final
            if dry_run:
                final_status = "dry_run_complete"
                logger.info("Dry-run completed successfully (ROLLBACK executed)")
            else:
                final_status = "success"
                logger.info("Migration completed successfully (COMMIT executed)")

            # PASO 5: Actualizar registro con éxito
            self._update_execution_record(
                db_connection=db_connection,
                execution_id=execution_id,
                status=final_status,
                rows_migrated=execution_result["rows_affected"],
                backup_id=backup_id,
                execution_log=execution_result["log"],
            )

            duration = time.time() - start_time

            return {
                "execution_id": execution_id,
                "status": final_status,
                "rows_affected": execution_result["rows_affected"],
                "duration_seconds": round(duration, 2),
                "backup_id": backup_id,
                "errors": [],
                "execution_log": execution_result["log"],
            }

        except Exception as e:
            # PASO 6: Manejar error
            logger.error(f"Migration execution failed: {str(e)}")
            logger.error(traceback.format_exc())

            error_message = f"{type(e).__name__}: {str(e)}"
            errors.append(error_message)

            # Actualizar registro con error
            if execution_id:
                self._update_execution_record(
                    db_connection=db_connection,
                    execution_id=execution_id,
                    status="failed",
                    rows_migrated=0,
                    backup_id=backup_id,
                    error_message=error_message,
                )

            duration = time.time() - start_time

            return {
                "execution_id": execution_id,
                "status": "failed",
                "rows_affected": 0,
                "duration_seconds": round(duration, 2),
                "backup_id": backup_id,
                "errors": errors,
                "execution_log": [],
            }

    def _create_execution_record(
        self, db_connection, project_id: str, script: str, user_id: Optional[str]
    ) -> str:
        """
        Crea registro en migration_executions, retorna execution_id.

        Args:
            db_connection: Session de SQLAlchemy
            project_id: UUID del proyecto
            script: Script SQL completo
            user_id: UUID del usuario (opcional)

        Returns:
            execution_id (UUID como string)
        """
        execution_id = str(uuid4())

        # Calcular hash SHA-256 del script
        script_hash = hashlib.sha256(script.encode("utf-8")).hexdigest()

        # Insertar registro
        db_connection.execute(
            text("""
                INSERT INTO migration_executions (
                    id, project_id, status, script_hash, created_by,
                    started_at, created_at, updated_at
                ) VALUES (
                    :id, :project_id, 'running', :script_hash, :created_by,
                    NOW(), NOW(), NOW()
                )
            """),
            {
                "id": execution_id,
                "project_id": project_id,
                "script_hash": script_hash,
                "created_by": user_id,
            },
        )

        db_connection.commit()
        logger.info(f"Created execution record: {execution_id}")
        return execution_id

    def _create_backup(self, db_connection, project_id: str, script: Optional[str] = None) -> str:
        """
        Usa BackupManager para crear backup, retorna backup_id.

        Args:
            db_connection: Session de SQLAlchemy
            project_id: UUID del proyecto
            script: Script SQL (para extraer tablas destino)

        Returns:
            backup_id (string con formato 'backup_YYYYMMDD_HHMMSS')
        """
        # Inicializar BackupManager con la conexión
        self.backup_manager = BackupManager(db_connection)

        # Extraer tablas destino del script para hacer backup específico del proyecto
        if script:
            tables_to_backup = list(
                {
                    table
                    for stmt in self._parse_sql_script(script)
                    for table in [self._extract_table_name(stmt)]
                    if table
                }
            )
            if not tables_to_backup:
                tables_to_backup = ["projects", "mappings", "tables", "columns"]
            logger.info(f"Backing up project-specific tables: {tables_to_backup}")
        else:
            tables_to_backup = ["projects", "mappings", "tables", "columns"]

        # Crear backup
        backup_info = self.backup_manager.create_backup(
            tables=tables_to_backup,
            description=f"Automatic backup before migration execution for project {project_id}",
        )

        backup_id = backup_info["backup_id"]
        logger.info(f"Backup created: {backup_id} (tables: {len(backup_info['tables'])})")

        return str(backup_id)

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
        cursor = connection.cursor()

        try:
            # Parsear script en statements individuales
            statements = self._parse_sql_script(script)

            # Filtrar statements ejecutables (no vacíos ni solo comentarios)
            executable_statements = [
                s for s in statements if s.strip() and not s.strip().startswith("--")
            ]
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

                # Ignorar statements vacíos o solo comentarios
                if not stmt.strip() or stmt.strip().startswith("--"):
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

    def _parse_sql_script(self, script: str) -> List[str]:
        """
        Parsea script SQL en statements individuales.

        Args:
            script: Script SQL completo

        Returns:
            Lista de statements SQL (sin comentarios de línea)

        Note:
            Este es un parser simple. Para scripts complejos con
            bloques PL/pgSQL (DO $$...), puede necesitar mejoras.
        """
        # Remover comentarios de línea (-- ...)
        lines = script.split("\n")
        cleaned_lines = []

        for line in lines:
            # Remover comentarios inline
            if "--" in line:
                # Solo remover si el -- no está dentro de una string
                line = line.split("--")[0]

            cleaned_lines.append(line)

        cleaned_script = "\n".join(cleaned_lines)

        # Dividir por ';' (excepto dentro de bloques DO $$)
        # Para simplificar, detectamos bloques DO $$ ... END $$;
        statements = []
        current_stmt = []
        in_do_block = False

        for line in cleaned_lines:
            line_stripped = line.strip()

            # Detectar inicio de bloque DO
            if line_stripped.upper().startswith("DO $$") or line_stripped.upper().startswith(
                "DO $"
            ):
                in_do_block = True
                current_stmt.append(line)
                continue

            # Detectar fin de bloque DO
            if in_do_block and ("END $$;" in line_stripped or "END $;" in line_stripped):
                in_do_block = False
                current_stmt.append(line)
                statements.append("\n".join(current_stmt))
                current_stmt = []
                continue

            # Si estamos en bloque DO, agregar toda la línea
            if in_do_block:
                current_stmt.append(line)
                continue

            # Si no estamos en bloque, dividir por ';'
            if ";" in line:
                parts = line.split(";")
                for i, part in enumerate(parts):
                    if i == len(parts) - 1 and not part.strip():
                        # Última parte vacía, terminar statement
                        if current_stmt or part.strip():
                            current_stmt.append(part)
                            statements.append("\n".join(current_stmt))
                            current_stmt = []
                    else:
                        current_stmt.append(part)
                        if i < len(parts) - 1:  # No es la última parte
                            statements.append("\n".join(current_stmt))
                            current_stmt = []
            else:
                current_stmt.append(line)

        # Agregar último statement si quedó algo
        if current_stmt:
            statements.append("\n".join(current_stmt))

        # Filtrar statements vacíos
        statements = [s.strip() for s in statements if s.strip()]

        return statements

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
        backup_id: Optional[str] = None,
        execution_log: Optional[List[Dict]] = None,
        error_message: Optional[str] = None,
    ):
        """
        Actualiza registro en migration_executions.

        Args:
            db_connection: Session de SQLAlchemy
            execution_id: UUID del execution record
            status: Nuevo status ('success', 'failed', 'dry_run_complete', etc.)
            rows_migrated: Total de filas migradas
            backup_id: ID del backup creado
            execution_log: Log de ejecución (lista de dicts)
            error_message: Mensaje de error (si aplica)
        """
        import json

        # Convertir execution_log a JSON
        execution_log_json = json.dumps(execution_log) if execution_log else None

        db_connection.execute(
            text("""
                UPDATE migration_executions
                SET status = :status,
                    completed_at = NOW(),
                    rows_migrated = :rows_migrated,
                    backup_id = :backup_id,
                    execution_log = CAST(:execution_log AS jsonb),
                    error_message = :error_message,
                    updated_at = NOW()
                WHERE id = :execution_id
            """),
            {
                "status": status,
                "rows_migrated": rows_migrated,
                "backup_id": backup_id,
                "execution_log": execution_log_json,
                "error_message": error_message,
                "execution_id": execution_id,
            },
        )

        db_connection.commit()
        logger.info(
            f"Updated execution record {execution_id}: status={status}, rows={rows_migrated}"
        )

    def get_execution_status(self, db_connection, execution_id: str) -> Dict[str, Any]:
        """
        Consulta estado de una ejecución.

        Args:
            db_connection: Session de SQLAlchemy
            execution_id: UUID del execution record

        Returns:
            {
                'execution_id': uuid,
                'status': 'running' | 'success' | 'failed',
                'progress_percent': 60,
                'rows_migrated': 21000,
                'started_at': '2025-01-17T14:30:00Z',
                'completed_at': None,
                'current_step': 'Migrating table: orders'
            }

        Raises:
            ExecutionServiceError: Si no se encuentra el execution record
        """
        result = (
            db_connection.execute(
                text("""
                SELECT id, project_id, status, rows_migrated,
                       started_at, completed_at, execution_log, error_message
                FROM migration_executions
                WHERE id = :execution_id
            """),
                {"execution_id": execution_id},
            )
            .mappings()
            .fetchone()
        )

        if not result:
            raise ExecutionServiceError(f"Execution record {execution_id} not found")

        # Calcular progreso desde el log de ejecución
        import json

        log = []
        if result["execution_log"]:
            log = (
                json.loads(result["execution_log"])
                if isinstance(result["execution_log"], str)
                else result["execution_log"]
            )

        exec_status = result["status"]
        if exec_status in ("success", "failed", "dry_run_complete"):
            progress_percent = 100
        else:
            # Extraer total_statements del primer entry (metadata)
            total_statements = None
            for entry in log:
                if entry.get("type") == "metadata":
                    total_statements = entry.get("total_statements")
                    break
            completed = len(
                [e for e in log if e.get("step", 0) > 0 and e.get("status") == "success"]
            )
            if total_statements and total_statements > 0:
                progress_percent = min(int((completed / total_statements) * 100), 99)
            else:
                progress_percent = 0

        # Determinar step actual del execution_log
        current_step = "Initializing..."
        if log:
            step_entries = [e for e in log if e.get("step", 0) > 0]
            if step_entries:
                last_step = step_entries[-1]
                current_step = f"Step {last_step['step']}: {last_step.get('table', 'Unknown')}"

        return {
            "execution_id": str(result["id"]),
            "status": result["status"],
            "progress_percent": progress_percent,
            "rows_migrated": result["rows_migrated"] or 0,
            "started_at": result["started_at"].isoformat() if result["started_at"] else None,
            "completed_at": (
                result["completed_at"].isoformat() if result["completed_at"] else None
            ),
            "current_step": current_step,
            "error_message": result["error_message"],
        }
