# routers/locks.py
"""
API endpoints for entity locking operations
"""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.database.session import get_db_session
from app.routers.dependencies import get_current_user
from app.routers.realtime import realtime_broadcast
from app.services import locking_service

router = APIRouter(prefix="/api", tags=["locks"])


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
    """Attempt to acquire a lock on an entity"""
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error acquiring lock: {str(e)}")


@router.post("/locks/release")
def release_lock(
    payload: ReleaseLockRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Release a lock"""
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
        raise HTTPException(status_code=500, detail=f"Error releasing lock: {str(e)}")


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

        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking lock status: {str(e)}")


@router.post("/locks/{lock_id}/renew")
def renew_lock(
    lock_id: str,
    payload: RenewLockRequest,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Renew a lock (heartbeat)"""
    try:
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
        raise HTTPException(status_code=500, detail=f"Error renewing lock: {str(e)}")


@router.post("/locks/force-unlock")
def force_unlock(
    payload: ForceUnlockRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Force unlock an entity (admin action).
    Requires admin or owner permissions (checked in service/router).
    """
    # TODO: Add permission check here (must be admin or owner)
    # For now, allowing any authenticated user
    # You should add: check_user_role(db, current_user['id'], payload.project_id, ['admin', 'owner'])

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
        raise HTTPException(status_code=500, detail=f"Error force unlocking: {str(e)}")


@router.get("/locks/projects/{project_id}")
def get_active_locks(
    project_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """Get all active locks for a project"""
    try:
        locks = locking_service.get_active_locks(db, project_id)
        return locks
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching locks: {str(e)}")
