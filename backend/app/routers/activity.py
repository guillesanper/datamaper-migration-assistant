# routers/activity.py
"""
API endpoints for project activity feed
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database.session import get_db_session
from app.routers.dependencies import get_current_user, require_project_access
from app.services import activity_service
from app.utils.exception_sanitizer import internal_server_error

router = APIRouter(prefix="/api", tags=["activity"])
logger = logging.getLogger(__name__)


@router.get("/activity/projects/{project_id}")
def get_project_activity(
    project_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    activity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    grouped: bool = Query(False),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Get activity feed for a project.
    Set grouped=true to get activities grouped by date.
    """
    require_project_access(db, project_id, current_user["id"])
    try:
        filters = {
            "limit": limit,
            "offset": offset,
            "activity_type": activity_type,
            "entity_id": entity_id,
        }

        activities: Any
        if grouped:
            activities = activity_service.get_grouped_activity(
                db=db, project_id=project_id, filters=filters
            )
        else:
            activities = activity_service.get_project_activity(
                db=db, project_id=project_id, filters=filters
            )

        return {"success": True, "data": activities, "message": "Activity retrieved successfully"}
    except Exception as e:
        raise internal_server_error(e, logger, "Error fetching activity") from e


@router.get("/activity/entity/{entity_id}")
def get_entity_activity(
    entity_id: str,
    entity_type: str = Query(...),
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Get activity for a specific entity"""
    try:
        activities = activity_service.get_entity_activity(
            db=db,
            entity_id=entity_id,
            entity_type=entity_type,
            limit=limit,
            viewer_id=str(current_user["id"]),
        )

        return {
            "success": True,
            "data": activities,
            "message": "Entity activity retrieved successfully",
        }
    except Exception as e:
        raise internal_server_error(e, logger, "Error fetching entity activity") from e


@router.get("/activity/users/{user_id}")
def get_user_activity(
    user_id: str,
    project_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Get activity for a specific user (solo la de proyectos accesibles para quien consulta)"""
    if project_id:
        require_project_access(db, project_id, current_user["id"])
    try:
        activities = activity_service.get_user_activity(
            db=db,
            user_id=user_id,
            project_id=project_id,
            limit=limit,
            viewer_id=str(current_user["id"]),
        )

        return {
            "success": True,
            "data": activities,
            "message": "User activity retrieved successfully",
        }
    except Exception as e:
        raise internal_server_error(e, logger, "Error fetching user activity") from e


@router.get("/activity/global")
def get_global_activity(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Get activity feed across all projects accessible to the current user"""
    try:
        activities = activity_service.get_global_activity(
            db=db, user_id=current_user["id"], limit=limit, offset=offset
        )
        return {
            "success": True,
            "data": activities,
            "message": "Global activity retrieved successfully",
        }
    except Exception as e:
        raise internal_server_error(e, logger, "Error fetching global activity") from e


@router.get("/activity/projects/{project_id}/stats")
def get_activity_stats(
    project_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """Get activity statistics for a project"""
    require_project_access(db, project_id, current_user["id"])
    try:
        stats = activity_service.get_activity_stats(db, project_id)
        return {"success": True, "data": stats, "message": "Activity stats retrieved successfully"}
    except Exception as e:
        raise internal_server_error(e, logger, "Error fetching activity stats") from e
