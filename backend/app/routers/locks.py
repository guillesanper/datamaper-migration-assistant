# routers/locks.py
"""
API endpoints for entity locking operations
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.database.session import get_db_session
from app.routers.dependencies import get_current_user, require_project_access
from app.routers.realtime import realtime_broadcast
from app.services import locking_service
from app.utils.exception_sanitizer import internal_server_error

router = APIRouter(prefix="/api", tags=["locks"])
logger = logging.getLogger(__name__)


# Pydantic models
class AcquireLockRequest(BaseModel):
    entity_id: str
    entity_type: str  # 'mapping', 'table', etc.
    project_id: str
    duration_minutes: Optional[int] = 15


class ReleaseLockRequest(BaseModel):
    entity_id: str
    entity_type: str
    project_id: str


class RenewLockRequest(BaseModel):
    duration_minutes: Optional[int] = 15


class ForceUnlockRequest(BaseModel):
    entity_id: str
    entity_type: str
    project_id: str


# Endpoints
@router.post("/locks/acquire")
def acquire_lock(
    payload: AcquireLockRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Attempt to acquire a lock on an entity (owner o editor del proyecto)"""
    require_project_access(db, payload.project_id, current_user["id"], min_role="editor")
    try:
        result = locking_service.acquire_lock(
            db=db,
            entity_id=payload.entity_id,
            entity_type=payload.entity_type,
            project_id=payload.project_id,
            user_id=current_user["id"],
            duration_minutes=payload.duration_minutes or 15,
        )

        if result["success"]:
            # Broadcast real-time event
            background_tasks.add_task(
                realtime_broadcast,
                payload.project_id,
                {
                    "type": "lock:acquired",
                    "lock": result["lock"],
                    "entity_id": payload.entity_id,
                    "entity_type": payload.entity_type,
                    "actor_id": str(current_user["id"]),
                },
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error acquiring lock") from e


@router.post("/locks/release")
def release_lock(
    payload: ReleaseLockRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Release a lock"""
    require_project_access(db, payload.project_id, current_user["id"])
    try:
        released = locking_service.release_lock(
            db=db,
            entity_id=payload.entity_id,
            entity_type=payload.entity_type,
            project_id=payload.project_id,
            user_id=current_user["id"],
        )

        if not released:
            raise HTTPException(status_code=400, detail="Lock not found or you don't own it")

        # Broadcast real-time event
        background_tasks.add_task(
            realtime_broadcast,
            payload.project_id,
            {
                "type": "lock:released",
                "entity_id": payload.entity_id,
                "entity_type": payload.entity_type,
                "actor_id": str(current_user["id"]),
            },
        )

        return {"released": True}
    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error releasing lock") from e


@router.get("/locks/{entity_id}/{entity_type}/status")
def get_lock_status(
    entity_id: str,
    entity_type: str,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Check lock status for an entity"""
    try:
        status = locking_service.check_lock_status(
            db=db, entity_id=entity_id, entity_type=entity_type, user_id=current_user["id"]
        )

        # Un lock de un proyecto ajeno no se muestra (ni quién lo tiene)
        if status["lock"]:
            require_project_access(db, status["lock"]["project_id"], current_user["id"])

        return status
    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error checking lock status") from e


@router.post("/locks/{lock_id}/renew")
def renew_lock(
    lock_id: str,
    payload: RenewLockRequest,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Renew a lock (heartbeat)"""
    try:
        # Quien ya no tiene acceso al proyecto no puede seguir renovando el lock
        existing = locking_service.get_lock(db, lock_id)
        if not existing or str(existing["user_id"]) != str(current_user["id"]):
            raise HTTPException(status_code=400, detail="Lock not found or you don't own it")
        require_project_access(db, existing["project_id"], current_user["id"], min_role="editor")

        lock = locking_service.renew_lock(
            db=db,
            lock_id=lock_id,
            user_id=current_user["id"],
            duration_minutes=payload.duration_minutes or 15,
        )

        if not lock:
            raise HTTPException(status_code=400, detail="Lock not found or you don't own it")

        return lock
    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error renewing lock") from e


@router.post("/locks/force-unlock")
def force_unlock(
    payload: ForceUnlockRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Force unlock an entity (admin action).
    Solo el owner del proyecto, y solo sobre locks de ese proyecto.
    """
    require_project_access(db, payload.project_id, current_user["id"], min_role="owner")

    try:
        unlocked = locking_service.force_unlock(
            db=db,
            entity_id=payload.entity_id,
            entity_type=payload.entity_type,
            project_id=payload.project_id,
            admin_user_id=current_user["id"],
        )

        if not unlocked:
            raise HTTPException(status_code=404, detail="Lock not found")

        # Broadcast real-time event
        background_tasks.add_task(
            realtime_broadcast,
            payload.project_id,
            {
                "type": "lock:force_unlocked",
                "entity_id": payload.entity_id,
                "entity_type": payload.entity_type,
                "actor_id": str(current_user["id"]),
            },
        )

        return {"unlocked": True}
    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error force unlocking") from e


@router.get("/locks/projects/{project_id}")
def get_active_locks(
    project_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """Get all active locks for a project"""
    require_project_access(db, project_id, current_user["id"])
    try:
        locks = locking_service.get_active_locks(db, project_id)
        return locks
    except Exception as e:
        raise internal_server_error(e, logger, "Error fetching locks") from e
