"""
Data Retention Service
Servicio para gestión de retención y purga de datos cifrados

Implementa políticas de:
- Retención de datos por período de tiempo
- Purga automática de datos antiguos
- Limpieza al finalizar proyectos
- Auditoría de purgas

Autor: DataMap Security Team
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from psycopg2.extras import RealDictCursor

from app.config.security import security_settings


class DataRetentionService:
    """Servicio de retención de datos cifrados"""

    @staticmethod
    def purge_old_encrypted_data(
        db, project_id: str, retention_days: Optional[int] = None, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Purga datos cifrados antiguos según política de retención

        Elimina:
        - Snapshots de versiones antiguas (mantiene última versión)
        - Comentarios resueltos antiguos
        - Actividad antigua del proyecto

        Args:
            db: Database connection
            project_id: ID del proyecto
            retention_days: Días de retención (default: de configuración)
            user_id: Usuario que ejecuta la purga (para auditoría)

        Returns:
            Dict con estadísticas de purga

        Raises:
            HTTPException: Si falla la purga
        """
        if retention_days is None:
            retention_days = security_settings.DATA_RETENTION_DAYS

        cursor = db.cursor(cursor_factory=RealDictCursor)

        try:
            # Llamar a la función SQL de purga
            cursor.execute(
                """
                SELECT * FROM purge_old_encrypted_data(%s, %s)
            """,
                (project_id, retention_days),
            )

            result = cursor.fetchone()

            if not result:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="No se pudieron obtener estadísticas de purga",
                )

            versions_deleted = result["versions_deleted"]
            comments_deleted = result["comments_deleted"]
            activity_deleted = result["activity_deleted"]

            # Log en security_logs
            if user_id:
                from app.utils.security_logger import log_security_event

                log_security_event(  # type: ignore[call-arg, unused-coroutine]
                    db=db,
                    event_type="data_purge",
                    user_id=user_id,
                    details={
                        "project_id": project_id,
                        "retention_days": retention_days,
                        "versions_deleted": versions_deleted,
                        "comments_deleted": comments_deleted,
                        "activity_deleted": activity_deleted,
                    },
                    severity="warning",
                )

            db.commit()

            return {
                "status": "success",
                "project_id": project_id,
                "retention_days": retention_days,
                "versions_deleted": versions_deleted,
                "comments_deleted": comments_deleted,
                "activity_deleted": activity_deleted,
                "total_deleted": versions_deleted + comments_deleted + activity_deleted,
            }

        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error durante purga de datos: {str(e)}",
            )
        finally:
            cursor.close()

    @staticmethod
    def purge_project_on_completion(
        db, project_id: str, user_id: str, keep_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Purga todos los datos de un proyecto al finalizarlo

        ADVERTENCIA: Esta operación es IRREVERSIBLE

        Args:
            db: Database connection
            project_id: ID del proyecto
            user_id: Usuario que ejecuta la purga
            keep_metadata: Si True, mantiene metadata mínima para auditoría

        Returns:
            Dict con estadísticas de purga

        Raises:
            HTTPException: Si falla la purga
        """
        cursor = db.cursor(cursor_factory=RealDictCursor)

        try:
            # Verificar que el proyecto esté marcado como 'completed'
            cursor.execute(
                """
                SELECT status FROM projects WHERE id = %s
            """,
                (project_id,),
            )

            project = cursor.fetchone()
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado"
                )

            if project["status"] != "completed":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Solo se pueden purgar proyectos con status 'completed'",
                )

            deleted_counts = {
                "tables": 0,
                "columns": 0,
                "mappings": 0,
                "versions": 0,
                "comments": 0,
                "activity": 0,
            }

            # Eliminar versiones cifradas
            cursor.execute(
                """
                DELETE FROM entity_versions
                WHERE project_id = %s AND is_encrypted = TRUE
            """,
                (project_id,),
            )
            deleted_counts["versions"] = cursor.rowcount

            # Eliminar comentarios cifrados
            cursor.execute(
                """
                DELETE FROM comments
                WHERE project_id = %s AND is_encrypted = TRUE
            """,
                (project_id,),
            )
            deleted_counts["comments"] = cursor.rowcount

            # Eliminar actividad
            cursor.execute(
                """
                DELETE FROM project_activity
                WHERE project_id = %s
            """,
                (project_id,),
            )
            deleted_counts["activity"] = cursor.rowcount

            # Eliminar mappings cifrados
            cursor.execute(
                """
                DELETE FROM mappings
                WHERE project_id = %s AND is_encrypted = TRUE
            """,
                (project_id,),
            )
            deleted_counts["mappings"] = cursor.rowcount

            # Eliminar columnas cifradas
            cursor.execute(
                """
                DELETE FROM columns c
                USING tables t
                WHERE c.table_id = t.id
                  AND t.project_id = %s
                  AND c.is_encrypted = TRUE
            """,
                (project_id,),
            )
            deleted_counts["columns"] = cursor.rowcount

            # Eliminar tablas cifradas
            cursor.execute(
                """
                DELETE FROM tables
                WHERE project_id = %s AND is_encrypted = TRUE
            """,
                (project_id,),
            )
            deleted_counts["tables"] = cursor.rowcount

            # Opcional: Eliminar configuración de cifrado
            if not keep_metadata:
                cursor.execute(
                    """
                    DELETE FROM project_encryption
                    WHERE project_id = %s
                """,
                    (project_id,),
                )

            # Log en security_logs
            from app.utils.security_logger import log_security_event

            log_security_event(  # type: ignore[call-arg, unused-coroutine]
                db=db,
                event_type="project_purge_completed",
                user_id=user_id,
                details={
                    "project_id": project_id,
                    "keep_metadata": keep_metadata,
                    **deleted_counts,
                },
                severity="critical",
            )

            db.commit()

            return {
                "status": "success",
                "project_id": project_id,
                "keep_metadata": keep_metadata,
                "deleted_counts": deleted_counts,
                "total_deleted": sum(deleted_counts.values()),
            }

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error purgando proyecto: {str(e)}",
            )
        finally:
            cursor.close()

    @staticmethod
    def get_purgeable_data_stats(
        db, project_id: str, retention_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Obtiene estadísticas de datos que serían purgados

        Útil para preview antes de ejecutar purga

        Args:
            db: Database connection
            project_id: ID del proyecto
            retention_days: Días de retención (default: de configuración)

        Returns:
            Dict con estadísticas de datos purgables
        """
        if retention_days is None:
            retention_days = security_settings.DATA_RETENTION_DAYS

        cursor = db.cursor(cursor_factory=RealDictCursor)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        try:
            # Contar versiones purgables
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM entity_versions
                WHERE project_id = %s
                  AND is_encrypted = TRUE
                  AND created_at < %s
                  AND id NOT IN (
                      SELECT DISTINCT ON (entity_id) id
                      FROM entity_versions
                      WHERE project_id = %s
                      ORDER BY entity_id, created_at DESC
                  )
            """,
                (project_id, cutoff_date, project_id),
            )

            versions_purgeable = cursor.fetchone()["count"]

            # Contar comentarios purgables
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM comments
                WHERE project_id = %s
                  AND is_encrypted = TRUE
                  AND created_at < %s
                  AND is_resolved = TRUE
            """,
                (project_id, cutoff_date),
            )

            comments_purgeable = cursor.fetchone()["count"]

            # Contar actividad purgable
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM project_activity
                WHERE project_id = %s
                  AND created_at < %s
            """,
                (project_id, cutoff_date),
            )

            activity_purgeable = cursor.fetchone()["count"]

            return {
                "project_id": project_id,
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
                "purgeable": {
                    "versions": versions_purgeable,
                    "comments": comments_purgeable,
                    "activity": activity_purgeable,
                    "total": versions_purgeable + comments_purgeable + activity_purgeable,
                },
            }

        finally:
            cursor.close()

    @staticmethod
    def schedule_automatic_purge(db, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Programa purga automática para proyectos con cifrado

        Si project_id es None, purga TODOS los proyectos con cifrado habilitado
        según sus políticas de retención

        Args:
            db: Database connection
            project_id: ID del proyecto específico (opcional)

        Returns:
            Dict con estadísticas de purga
        """
        cursor = db.cursor(cursor_factory=RealDictCursor)

        try:
            # Obtener proyectos con cifrado habilitado
            if project_id:
                cursor.execute(
                    """
                    SELECT project_id
                    FROM project_encryption
                    WHERE project_id = %s AND encryption_enabled = TRUE
                """,
                    (project_id,),
                )
            else:
                cursor.execute("""
                    SELECT project_id
                    FROM project_encryption
                    WHERE encryption_enabled = TRUE
                """)

            projects = cursor.fetchall()
            results = []

            for project in projects:
                pid = project["project_id"]

                try:
                    result = DataRetentionService.purge_old_encrypted_data(db, pid, user_id=None)
                    results.append(result)
                except Exception as e:
                    results.append({"project_id": pid, "status": "error", "error": str(e)})

            return {"status": "success", "projects_processed": len(results), "results": results}

        finally:
            cursor.close()

    @staticmethod
    def export_before_purge(
        db, project_id: str, encryption_key: bytes, user_id: str
    ) -> Dict[str, Any]:
        """
        Exporta datos cifrados antes de purgarlos

        Útil para:
        - Backup antes de purga
        - Archivado de datos históricos
        - Cumplimiento legal (retención extendida)

        Args:
            db: Database connection
            project_id: ID del proyecto
            encryption_key: Clave de cifrado para descifrar datos
            user_id: Usuario que exporta

        Returns:
            Dict con datos descifrados y metadata

        Note:
            Esta función descifra TODOS los datos del proyecto
            Use con precaución y solo con permisos adecuados
        """
        # TODO: Implementar exportación completa
        # Por ahora solo retorna metadata

        stats = DataRetentionService.get_purgeable_data_stats(db, project_id)

        return {
            "status": "export_ready",
            "project_id": project_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "exported_by": user_id,
            "stats": stats,
            "note": "Implementación completa de exportación pendiente",
        }


# ============================================================================
# SCHEDULED TASKS (para usar con APScheduler o Celery)
# ============================================================================


def run_daily_purge(db):
    """
    Tarea programada para ejecutar purga diaria

    Se puede llamar desde:
    - Cron job
    - APScheduler
    - Celery task
    - Cloud Functions (AWS Lambda, Google Cloud Functions)

    Ejemplo con APScheduler:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            func=run_daily_purge,
            args=[db],
            trigger="cron",
            hour=2,  # 2 AM
            minute=0
        )
        scheduler.start()
    """
    try:
        result = DataRetentionService.schedule_automatic_purge(db)
        print(
            f"✅ Purga automática completada: {result['projects_processed']} proyectos procesados"
        )
        return result
    except Exception as e:
        print(f"❌ Error en purga automática: {e}")
        raise
