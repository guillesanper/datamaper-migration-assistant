# services/activity_service.py
"""
Business logic for activity feed
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.crud import activity_crud


def get_project_activity(
    db, project_id: str, filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Get activity feed for a project with optional filters"""
    filters = filters or {}

    return activity_crud.get_project_activity_orm(
        db=db,
        project_id=project_id,
        limit=filters.get("limit", 50),
        offset=filters.get("offset", 0),
        activity_type=filters.get("activity_type"),
        entity_id=filters.get("entity_id"),
    )


def get_grouped_activity(
    db, project_id: str, filters: Optional[Dict[str, Any]] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get activity grouped by date (Today, Yesterday, This Week, etc.)
    """
    activities = get_project_activity(db, project_id, filters)

    now = datetime.utcnow()
    today = now.date()
    yesterday = (now - timedelta(days=1)).date()
    week_ago = (now - timedelta(days=7)).date()

    grouped: Dict[str, List[Dict[str, Any]]] = {
        "today": [],
        "yesterday": [],
        "this_week": [],
        "older": [],
    }

    for activity in activities:
        activity_date = activity["created_at"].date()

        if activity_date == today:
            grouped["today"].append(activity)
        elif activity_date == yesterday:
            grouped["yesterday"].append(activity)
        elif activity_date >= week_ago:
            grouped["this_week"].append(activity)
        else:
            grouped["older"].append(activity)

    return grouped


def get_entity_activity(
    db, entity_id: str, entity_type: str, limit: int = 50
) -> List[Dict[str, Any]]:
    """Get activity for a specific entity"""
    return activity_crud.get_entity_activity_orm(db, entity_id, entity_type, limit)


def get_user_activity(
    db, user_id: str, project_id: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """Get activity for a specific user"""
    return activity_crud.get_user_activity_orm(db, user_id, project_id, limit)


def get_global_activity(db, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    """Get activity across all projects accessible to the user"""
    return activity_crud.get_global_activity_orm(db, user_id, limit, offset)


def get_activity_stats(db, project_id: str) -> Dict[str, Any]:
    """Get activity statistics for a project"""
    stats = activity_crud.get_activity_stats_orm(db, project_id)

    # Calculate totals
    total_activities = sum(stats.values())

    return {"total": total_activities, "by_type": stats}


def create_activity_log(
    db,
    project_id: str,
    user_id: str,
    activity_type: str,
    description: str,
    entity_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a custom activity log entry"""
    return activity_crud.create_activity_log_orm(
        db=db,
        project_id=project_id,
        user_id=user_id,
        activity_type=activity_type,
        description=description,
        entity_id=entity_id,
        entity_type=entity_type,
        metadata=metadata,
    )
