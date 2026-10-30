"""
Operaciones CRUD para tablas de migration system.
Maneja scripts de migración y sus ejecuciones.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ============================================================================
# MIGRATION SCRIPT OPERATIONS
# ============================================================================


def create_migration_script_orm(
    db: Session,
    project_id: str,
    script_content: str,
    batch_size: int = 10000,
    include_constraints: bool = True,
    include_validation: bool = True,
    dialect: str = "postgresql",
    dependency_order: Optional[List[str]] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crea un nuevo script de migración (ORM version).

    Args:
        db: SQLAlchemy Session
        project_id: UUID del proyecto
        script_content: Contenido SQL del script
        batch_size: Tamaño del batch (default: 10000)
        include_constraints: Incluir constraints (default: True)
        include_validation: Incluir validación (default: True)
        dialect: Dialecto SQL (default: 'postgresql')
        dependency_order: Orden de ejecución de tablas (opcional)
        created_by: UUID del usuario creador (opcional)

    Returns:
        Dict con los datos del script creado

    Raises:
        HTTPException: Si hay error al crear el script
    """
    from app.models.orm.migration import MigrationScript
    from app.utils.orm_helpers import model_to_dict

    try:
        # Calcular hash SHA-256 del script
        script_hash = hashlib.sha256(script_content.encode("utf-8")).hexdigest()

        # Crear nuevo script
        new_script = MigrationScript(
            id=uuid.uuid4(),
            project_id=project_id,
            script_content=script_content,
            script_hash=script_hash,
            batch_size=batch_size,
            include_constraints=include_constraints,
            include_validation=include_validation,
            dialect=dialect,
            dependency_order=dependency_order,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db.add(new_script)
        db.commit()
        db.refresh(new_script)

        result = model_to_dict(new_script)
        logger.debug(f"Script de migración creado: {new_script.id}")

        return result  # type: ignore[return-value]

    except Exception as e:
        db.rollback()
        logger.error(f"Error al crear script de migración: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al crear script de migración: {str(e)}")


def get_migration_script_by_id_orm(
    db: Session, script_id: str, project_id: str
) -> Optional[Dict[str, Any]]:
    """
    Obtiene un script de migración por ID (ORM version).

    Valida que el script pertenezca al proyecto especificado.

    Args:
        db: SQLAlchemy Session
        script_id: UUID del script
        project_id: UUID del proyecto (para validar pertenencia)

    Returns:
        Dict con los datos del script, o None si no existe/no pertenece al proyecto

    Raises:
        Exception: Si hay error al obtener el script
    """
    from app.models.orm.migration import MigrationScript
    from app.utils.orm_helpers import model_to_dict

    try:
        script = (
            db.query(MigrationScript)
            .filter(and_(MigrationScript.id == script_id, MigrationScript.project_id == project_id))
            .first()
        )

        if not script:
            logger.warning(f"Script no encontrado: {script_id} para proyecto {project_id}")
            return None

        result = model_to_dict(script)
        return result

    except Exception as e:
        logger.error(f"Error al obtener script de migración: {str(e)}")
        raise


def get_migration_scripts_orm(
    db: Session, project_id: str, limit: int = 50, offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Obtiene todos los scripts de un proyecto (ORM version).

    Ordena por fecha de creación (más recientes primero).

    Args:
        db: SQLAlchemy Session
        project_id: UUID del proyecto
        limit: Número máximo de scripts a retornar (default: 50)
        offset: Número de scripts a saltar (default: 0)

    Returns:
        Lista de dicts con los datos de los scripts

    Raises:
        Exception: Si hay error al obtener los scripts
    """
    from app.models.orm.migration import MigrationScript
    from app.utils.orm_helpers import model_to_dict

    try:
        scripts = (
            db.query(MigrationScript)
            .filter(MigrationScript.project_id == project_id)
            .order_by(MigrationScript.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        result = [model_to_dict(script) for script in scripts]
        logger.debug(f"Obtenidos {len(result)} scripts para proyecto {project_id}")

        return result  # type: ignore[return-value]

    except Exception as e:
        logger.error(f"Error al obtener scripts de migración: {str(e)}")
        raise


# ============================================================================
# MIGRATION EXECUTION OPERATIONS
# ============================================================================


def create_migration_execution_orm(
    db: Session,
    project_id: str,
    script_hash: str,
    created_by: Optional[str] = None,
    backup_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crea un nuevo registro de ejecución de migración (ORM version).

    Args:
        db: SQLAlchemy Session
        project_id: UUID del proyecto
        script_hash: SHA-256 hash del script ejecutado
        created_by: UUID del usuario que ejecuta (opcional)
        backup_id: ID del backup creado antes de ejecutar (opcional)

    Returns:
        Dict con los datos de la ejecución creada

    Raises:
        HTTPException: Si hay error al crear la ejecución
    """
    from app.models.orm.migration import MigrationExecution
    from app.utils.orm_helpers import model_to_dict

    try:
        # Crear nueva ejecución
        new_execution = MigrationExecution(
            id=uuid.uuid4(),
            project_id=project_id,
            script_hash=script_hash,
            status="pending",
            rows_migrated=0,
            backup_id=backup_id,
            execution_log=[],
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db.add(new_execution)
        db.commit()
        db.refresh(new_execution)

        result = model_to_dict(new_execution)
        logger.debug(f"Ejecución de migración creada: {new_execution.id}")

        return result  # type: ignore[return-value]

    except Exception as e:
        db.rollback()
        logger.error(f"Error al crear ejecución de migración: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error al crear ejecución de migración: {str(e)}"
        )


def get_migration_execution_orm(db: Session, execution_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene una ejecución de migración por ID (ORM version).

    Args:
        db: SQLAlchemy Session
        execution_id: UUID de la ejecución

    Returns:
        Dict con los datos de la ejecución, o None si no existe

    Raises:
        Exception: Si hay error al obtener la ejecución
    """
    from app.models.orm.migration import MigrationExecution
    from app.utils.orm_helpers import model_to_dict

    try:
        execution = (
            db.query(MigrationExecution).filter(MigrationExecution.id == execution_id).first()
        )

        if not execution:
            logger.warning(f"Ejecución no encontrada: {execution_id}")
            return None

        result = model_to_dict(execution)
        return result

    except Exception as e:
        logger.error(f"Error al obtener ejecución de migración: {str(e)}")
        raise


def update_execution_status_orm(
    db: Session,
    execution_id: str,
    status: str,
    rows_migrated: Optional[int] = None,
    execution_log: Optional[List[Dict]] = None,
    error_message: Optional[str] = None,
    mark_completed: bool = False,
    mark_started: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Actualiza el estado de una ejecución (ORM version).

    Args:
        db: SQLAlchemy Session
        execution_id: UUID de la ejecución
        status: Nuevo estado (pending, running, success, failed, rolled_back, dry_run_complete)
        rows_migrated: Número de filas migradas (opcional)
        execution_log: Log de ejecución actualizado (opcional)
        error_message: Mensaje de error si falló (opcional)
        mark_completed: Si True, establece completed_at a NOW (default: False)
        mark_started: Si True, establece started_at a NOW (default: False)

    Returns:
        Dict con los datos actualizados, o None si no se encontró

    Raises:
        HTTPException: Si hay error al actualizar
    """
    from app.models.orm.migration import MigrationExecution
    from app.utils.orm_helpers import model_to_dict

    try:
        execution = (
            db.query(MigrationExecution).filter(MigrationExecution.id == execution_id).first()
        )

        if not execution:
            logger.warning(f"Ejecución no encontrada para actualizar: {execution_id}")
            return None

        # Actualizar campos
        execution.status = status  # type: ignore[assignment]

        if rows_migrated is not None:
            execution.rows_migrated = rows_migrated  # type: ignore[assignment]

        if execution_log is not None:
            execution.execution_log = execution_log  # type: ignore[assignment]

        if error_message is not None:
            execution.error_message = error_message  # type: ignore[assignment]

        if mark_started and not execution.started_at:
            execution.started_at = datetime.now(timezone.utc)  # type: ignore[assignment]

        if mark_completed and not execution.completed_at:
            execution.completed_at = datetime.now(timezone.utc)  # type: ignore[assignment]

        execution.updated_at = datetime.now(timezone.utc)  # type: ignore[assignment]

        db.commit()
        db.refresh(execution)

        result = model_to_dict(execution)
        logger.debug(f"Ejecución actualizada: {execution_id} - status: {status}")

        return result

    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar ejecución: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al actualizar ejecución: {str(e)}")


def get_execution_logs_orm(db: Session, execution_id: str) -> Dict[str, Any]:
    """
    Obtiene los logs de ejecución y mensaje de error (ORM version).

    Args:
        db: SQLAlchemy Session
        execution_id: UUID de la ejecución

    Returns:
        Dict con execution_log y error_message

    Raises:
        HTTPException: Si no se encuentra la ejecución
    """
    from app.models.orm.migration import MigrationExecution

    try:
        execution = (
            db.query(MigrationExecution).filter(MigrationExecution.id == execution_id).first()
        )

        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")

        return {
            "execution_log": execution.execution_log if execution.execution_log else [],
            "error_message": execution.error_message,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener logs de ejecución: {str(e)}")
        raise


def count_executions_orm(db: Session, project_id: str, status_filter: Optional[str] = None) -> int:
    """
    Cuenta el número de ejecuciones de un proyecto (ORM version).

    Args:
        db: SQLAlchemy Session
        project_id: UUID del proyecto
        status_filter: Filtrar por estado específico (opcional)

    Returns:
        Número de ejecuciones que cumplen los criterios

    Raises:
        Exception: Si hay error al contar
    """
    from app.models.orm.migration import MigrationExecution

    try:
        query = db.query(MigrationExecution).filter(MigrationExecution.project_id == project_id)

        if status_filter:
            query = query.filter(MigrationExecution.status == status_filter)

        count = query.count()
        return count

    except Exception as e:
        logger.error(f"Error al contar ejecuciones: {str(e)}")
        raise


def get_executions_paginated_orm(
    db: Session,
    project_id: str,
    status_filter: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Obtiene ejecuciones paginadas de un proyecto (ORM version).

    Ordena por started_at (más recientes primero).
    Incluye cálculo de duration_seconds.

    Args:
        db: SQLAlchemy Session
        project_id: UUID del proyecto
        status_filter: Filtrar por estado específico (opcional)
        limit: Número máximo de ejecuciones a retornar (default: 10)
        offset: Número de ejecuciones a saltar (default: 0)

    Returns:
        Lista de dicts con los datos de las ejecuciones

    Raises:
        Exception: Si hay error al obtener las ejecuciones
    """
    from sqlalchemy import case, extract, literal

    from app.models.orm.migration import MigrationExecution

    try:
        query = db.query(
            MigrationExecution.id,
            MigrationExecution.started_at,
            MigrationExecution.completed_at,
            MigrationExecution.status,
            MigrationExecution.rows_migrated,
            # Calcular duration_seconds: COALESCE(completed_at, NOW()) - started_at
            extract(
                "epoch",
                func.coalesce(MigrationExecution.completed_at, func.now())
                - MigrationExecution.started_at,
            ).label("duration_seconds"),
        ).filter(MigrationExecution.project_id == project_id)

        if status_filter:
            query = query.filter(MigrationExecution.status == status_filter)

        query = query.order_by(MigrationExecution.started_at.desc())
        query = query.limit(limit).offset(offset)

        executions = query.all()

        # Formatear resultados
        result = [
            {
                "id": str(e.id),
                "started_at": e.started_at,
                "completed_at": e.completed_at,
                "status": e.status,
                "rows_migrated": e.rows_migrated or 0,
                "duration_seconds": int(e.duration_seconds) if e.duration_seconds else 0,
            }
            for e in executions
        ]

        logger.debug(f"Obtenidas {len(result)} ejecuciones para proyecto {project_id}")

        return result

    except Exception as e:
        logger.error(f"Error al obtener ejecuciones paginadas: {str(e)}")
        raise


def get_recent_executions_for_user(
    db: Session, user_id: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Returns the most recent migration executions across all projects accessible by the user.

    A project is accessible if the user is owner OR a project member.
    """
    from sqlalchemy import or_, select

    from app.models.orm.migration import MigrationExecution
    from app.models.orm.project import Project, ProjectMember

    try:
        accessible_projects = select(Project.id).where(
            or_(
                Project.owner_id == user_id,
                Project.id.in_(
                    select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
                ),
            ),
            Project.is_deleted.is_(False),
        )

        rows = (
            db.query(
                MigrationExecution.id,
                MigrationExecution.project_id,
                Project.name.label("project_name"),
                MigrationExecution.status,
                MigrationExecution.started_at,
                MigrationExecution.completed_at,
            )
            .join(Project, Project.id == MigrationExecution.project_id)
            .filter(MigrationExecution.project_id.in_(accessible_projects))
            .order_by(MigrationExecution.started_at.desc().nullslast())
            .limit(limit)
            .all()
        )

        return [
            {
                "execution_id": str(r.id),
                "project_id": str(r.project_id),
                "project_name": r.project_name,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in rows
        ]

    except Exception as e:
        logger.error(f"Error fetching recent executions for user {user_id}: {str(e)}")
        raise


def get_execution_by_project_orm(
    db: Session, execution_id: str, project_id: str
) -> Optional[Dict[str, Any]]:
    """
    Obtiene una ejecución validando que pertenezca al proyecto (ORM version).

    Args:
        db: SQLAlchemy Session
        execution_id: UUID de la ejecución
        project_id: UUID del proyecto (para validar pertenencia)

    Returns:
        Dict con los datos de la ejecución, o None si no existe/no pertenece

    Raises:
        Exception: Si hay error al obtener la ejecución
    """
    from app.models.orm.migration import MigrationExecution
    from app.utils.orm_helpers import model_to_dict

    try:
        execution = (
            db.query(MigrationExecution)
            .filter(
                and_(
                    MigrationExecution.id == execution_id,
                    MigrationExecution.project_id == project_id,
                )
            )
            .first()
        )

        if not execution:
            logger.warning(f"Ejecución no encontrada: {execution_id} para proyecto {project_id}")
            return None

        result = model_to_dict(execution)
        return result

    except Exception as e:
        logger.error(f"Error al obtener ejecución por proyecto: {str(e)}")
        raise
