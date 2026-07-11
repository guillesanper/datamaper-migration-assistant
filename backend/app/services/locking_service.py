# services/locking_service.py
"""
Business logic for entity locking operations

CONVENCIÓN DE LOCKS:
- Para locks de COLUMNA individual:
  - entity_id = "table_name:column_name" (ej: "users:email")
  - entity_type = "column"

- Para locks de TABLA completa:
  - entity_id = "table_name"
  - entity_type = "table"

Esta granularidad permite que múltiples usuarios trabajen en diferentes
columnas de la misma tabla simultáneamente.
"""

from typing import Any, Dict, List, Optional

from app.crud import activity_crud, locks_crud


def acquire_lock(
    db, entity_id: str, entity_type: str, project_id: str, user_id: str, duration_minutes: int = 15
) -> Dict[str, Any]:
    """
    Attempt to acquire a lock on an entity.
    Returns lock info with status.
    """
    lock = locks_crud.acquire_lock_orm(
        db=db,
        entity_id=entity_id,
        entity_type=entity_type,
        project_id=project_id,
        user_id=user_id,
        duration_minutes=duration_minutes,
    )

    if not lock:
        # Lock failed, get current lock info
        current_lock = locks_crud.get_lock_status_orm(db, entity_id, entity_type)
        return {"success": False, "locked_by_another": True, "current_lock": current_lock}

    # Log activity
    activity_crud.create_activity_log_orm(
        db=db,
        project_id=project_id,
        user_id=user_id,
        activity_type="lock_acquired",
        entity_id=entity_id,
        entity_type=entity_type,
        description=f"Acquired lock on {entity_type}",
        metadata={"lock_id": lock["id"]},
    )

    return {"success": True, "locked_by_another": False, "lock": lock}


def release_lock(db, entity_id: str, entity_type: str, project_id: str, user_id: str) -> bool:
    """
    Release a lock. Only the owner can release their lock.
    """
    released = locks_crud.release_lock_orm(db, entity_id, entity_type, user_id)

    if released:
        # Log activity
        activity_crud.create_activity_log_orm(
            db=db,
            project_id=project_id,
            user_id=user_id,
            activity_type="lock_released",
            entity_id=entity_id,
            entity_type=entity_type,
            description=f"Released lock on {entity_type}",
        )

    return released


def check_lock_status(db, entity_id: str, entity_type: str, user_id: str) -> Dict[str, Any]:
    """
    Check lock status and return user-friendly info.
    """
    lock = locks_crud.get_lock_status_orm(db, entity_id, entity_type)

    if not lock:
        return {"is_locked": False, "is_locked_by_me": False, "can_edit": True, "lock": None}

    is_locked_by_me = str(lock["user_id"]) == str(user_id)

    return {
        "is_locked": True,
        "is_locked_by_me": is_locked_by_me,
        "can_edit": is_locked_by_me,
        "lock": lock,
    }


def renew_lock(
    db, lock_id: str, user_id: str, duration_minutes: int = 15
) -> Optional[Dict[str, Any]]:
    """
    Renew a lock (heartbeat). Only the owner can renew.
    """
    return locks_crud.renew_lock_orm(db, lock_id, user_id, duration_minutes)


def force_unlock(db, entity_id: str, entity_type: str, project_id: str, admin_user_id: str) -> bool:
    """
    Force unlock an entity. Should only be called after permission check.
    Logs who forced the unlock.
    """
    # Get lock info before removing for logging
    lock = locks_crud.get_lock_status_orm(db, entity_id, entity_type)
    if not lock:
        return False

    unlocked = locks_crud.force_unlock_orm(db, entity_id, entity_type)

    if unlocked:
        # Log activity
        activity_crud.create_activity_log_orm(
            db=db,
            project_id=project_id,
            user_id=admin_user_id,
            activity_type="lock_force_unlocked",
            entity_id=entity_id,
            entity_type=entity_type,
            description=f"Force unlocked {entity_type}",
            metadata={"original_lock_user": str(lock["user_id"]), "forced_by": admin_user_id},
        )

    return unlocked


def get_active_locks(db, project_id: str) -> List[Dict[str, Any]]:
    """Get all active locks for a project"""
    return locks_crud.get_active_locks_orm(db, project_id)


def cleanup_expired_locks(db) -> int:
    """Clean up expired locks. Returns count of cleaned locks."""
    return locks_crud.cleanup_expired_locks_orm(db)


def check_user_can_edit(db, entity_id: str, entity_type: str, user_id: str) -> bool:
    """
    Check if user can edit an entity (either not locked or locked by them).
    """
    lock = locks_crud.get_lock_status_orm(db, entity_id, entity_type)

    if not lock:
        return True

    return str(lock["user_id"]) == str(user_id)


# ==================== HELPERS PARA LOCKS DE COLUMNAS ====================


def make_column_entity_id(table_name: str, column_name: str) -> str:
    """
    Crea un entity_id para lock de columna.
    Formato: "table_name:column_name"
    """
    return f"{table_name}:{column_name}"


def parse_column_entity_id(entity_id: str) -> tuple[str, str] | None:
    """
    Parsea un entity_id de columna.
    Retorna (table_name, column_name) o None si no es formato válido.
    """
    parts = entity_id.split(":", 1)
    if len(parts) == 2:
        return (parts[0], parts[1])
    return None


def acquire_column_lock(
    db,
    table_name: str,
    column_name: str,
    project_id: str,
    user_id: str,
    duration_minutes: int = 3,  # 3 minutos por defecto para columnas
) -> Dict[str, Any]:
    """
    Adquiere lock de una columna específica.
    """
    entity_id = make_column_entity_id(table_name, column_name)
    return acquire_lock(
        db=db,
        entity_id=entity_id,
        entity_type="column",
        project_id=project_id,
        user_id=user_id,
        duration_minutes=duration_minutes,
    )


def release_column_lock(
    db, table_name: str, column_name: str, project_id: str, user_id: str
) -> bool:
    """
    Libera lock de una columna específica.
    """
    entity_id = make_column_entity_id(table_name, column_name)
    return release_lock(
        db=db, entity_id=entity_id, entity_type="column", project_id=project_id, user_id=user_id
    )


def get_column_lock_status(db, table_name: str, column_name: str, user_id: str) -> Dict[str, Any]:
    """
    Obtiene el estado de lock de una columna.
    """
    entity_id = make_column_entity_id(table_name, column_name)
    return check_lock_status(db=db, entity_id=entity_id, entity_type="column", user_id=user_id)
