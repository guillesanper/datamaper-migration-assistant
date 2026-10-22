# crud/activity_crud.py
"""
CRUD operations for project_activity table
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


def create_activity_log_orm(
    db,  # SQLAlchemy Session
    project_id: str,
    user_id: str,
    activity_type: str,
    description: str,
    entity_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create an activity log entry (ORM version)"""
    import uuid as uuid_module
    from datetime import datetime, timezone

    from app.models.orm.activity import ProjectActivity

    new_activity = ProjectActivity(
        id=uuid_module.uuid4(),
        project_id=project_id,
        user_id=user_id,
        activity_type=activity_type,
        description=description,
        entity_id=entity_id,
        entity_type=entity_type,
        activity_metadata=metadata,  # Usar nombre Python
        created_at=datetime.now(timezone.utc),
    )

    db.add(new_activity)
    db.commit()
    db.refresh(new_activity)

    # Convertir a dict con mapeo manual
    return {
        "id": str(new_activity.id),
        "project_id": str(new_activity.project_id),
        "user_id": str(new_activity.user_id),
        "activity_type": new_activity.activity_type,
        "description": new_activity.description,
        "entity_id": str(new_activity.entity_id) if new_activity.entity_id else None,
        "entity_type": new_activity.entity_type,
        "metadata": new_activity.activity_metadata,  # Mapear a 'metadata'
        "created_at": new_activity.created_at,
    }


def get_project_activity_orm(
    db,  # SQLAlchemy Session
    project_id: str,
    limit: int = 50,
    offset: int = 0,
    activity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get activity feed for a project with filters (ORM version)"""
    from app.models.orm.activity import ProjectActivity
    from app.models.orm.user import User

    query = (
        db.query(ProjectActivity, User.username, User.email)
        .outerjoin(User, ProjectActivity.user_id == User.id)
        .filter(ProjectActivity.project_id == project_id)
    )

    # Filtros opcionales
    if activity_type:
        query = query.filter(ProjectActivity.activity_type == activity_type)
    if entity_id:
        query = query.filter(ProjectActivity.entity_id == entity_id)

    results = query.order_by(ProjectActivity.created_at.desc()).limit(limit).offset(offset).all()

    # Convertir con mapeo manual
    return [
        {
            "id": str(activity.id),
            "project_id": str(activity.project_id),
            "user_id": str(activity.user_id) if activity.user_id else None,
            "activity_type": activity.activity_type,
            "entity_id": str(activity.entity_id) if activity.entity_id else None,
            "entity_type": activity.entity_type,
            "description": activity.description,
            "metadata": activity.activity_metadata,  # Mapear a 'metadata'
            "created_at": activity.created_at,
            "username": username,  # De JOIN
            "user_email": email,  # De JOIN
        }
        for activity, username, email in results
    ]


def get_entity_activity_orm(
    db, entity_id: str, entity_type: str, limit: int = 50  # SQLAlchemy Session
) -> List[Dict[str, Any]]:
    """Get activity for a specific entity (ORM version)"""
    from app.models.orm.activity import ProjectActivity
    from app.models.orm.user import User

    results = (
        db.query(ProjectActivity, User.username, User.email)
        .outerjoin(User, ProjectActivity.user_id == User.id)
        .filter(ProjectActivity.entity_id == entity_id)
        .filter(ProjectActivity.entity_type == entity_type)
        .order_by(ProjectActivity.created_at.desc())
        .limit(limit)
        .all()
    )

    # Convertir con mapeo manual
    return [
        {
            "id": str(activity.id),
            "project_id": str(activity.project_id),
            "user_id": str(activity.user_id) if activity.user_id else None,
            "activity_type": activity.activity_type,
            "entity_id": str(activity.entity_id) if activity.entity_id else None,
            "entity_type": activity.entity_type,
            "description": activity.description,
            "metadata": activity.activity_metadata,  # Mapear a 'metadata'
            "created_at": activity.created_at,
            "username": username,  # De JOIN
            "user_email": email,  # De JOIN
        }
        for activity, username, email in results
    ]


def get_user_activity_orm(
    db, user_id: str, project_id: Optional[str] = None, limit: int = 50  # SQLAlchemy Session
) -> List[Dict[str, Any]]:
    """Get activity for a specific user (ORM version)"""
    from app.models.orm.activity import ProjectActivity
    from app.models.orm.user import User

    query = (
        db.query(ProjectActivity, User.username, User.email)
        .outerjoin(User, ProjectActivity.user_id == User.id)
        .filter(ProjectActivity.user_id == user_id)
    )

    # Filtro opcional por proyecto
    if project_id:
        query = query.filter(ProjectActivity.project_id == project_id)

    results = query.order_by(ProjectActivity.created_at.desc()).limit(limit).all()

    # Convertir con mapeo manual
    return [
        {
            "id": str(activity.id),
            "project_id": str(activity.project_id),
            "user_id": str(activity.user_id) if activity.user_id else None,
            "activity_type": activity.activity_type,
            "entity_id": str(activity.entity_id) if activity.entity_id else None,
            "entity_type": activity.entity_type,
            "description": activity.description,
            "metadata": activity.activity_metadata,  # Mapear a 'metadata'
            "created_at": activity.created_at,
            "username": username,  # De JOIN
            "user_email": email,  # De JOIN
        }
        for activity, username, email in results
    ]


def get_global_activity_orm(
    db,  # SQLAlchemy Session
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Get activity across all projects accessible to the user (ORM version)"""
    from sqlalchemy import or_

    from app.models.orm.activity import ProjectActivity
    from app.models.orm.project import Project, ProjectMember
    from app.models.orm.user import User

    accessible = (
        db.query(Project.id)
        .outerjoin(ProjectMember, ProjectMember.project_id == Project.id)
        .filter(
            Project.is_deleted == False,  # noqa: E712
            or_(Project.owner_id == user_id, ProjectMember.user_id == user_id),
        )
        .subquery()
        .select()
    )

    results = (
        db.query(ProjectActivity, User.username, User.email)
        .outerjoin(User, ProjectActivity.user_id == User.id)
        .filter(ProjectActivity.project_id.in_(accessible))
        .order_by(ProjectActivity.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return [
        {
            "id": str(activity.id),
            "project_id": str(activity.project_id),
            "activity_type": activity.activity_type,
            "description": activity.description,
            "created_at": activity.created_at,
            "username": username,
        }
        for activity, username, email in results
    ]


def get_activity_stats_orm(db, project_id: str) -> Dict[str, int]:  # SQLAlchemy Session
    """Get activity statistics for a project (ORM version)"""
    from sqlalchemy import func

    from app.models.orm.activity import ProjectActivity

    results = (
        db.query(ProjectActivity.activity_type, func.count().label("count"))
        .filter(ProjectActivity.project_id == project_id)
        .group_by(ProjectActivity.activity_type)
        .all()
    )

    return {activity_type: count for activity_type, count in results}


def delete_old_activity_orm(db, days: int = 90) -> int:  # SQLAlchemy Session
    """Delete activity logs older than specified days (ORM version). Returns count deleted."""
    from datetime import datetime, timedelta, timezone

    from app.models.orm.activity import ProjectActivity

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    deleted_count = (
        db.query(ProjectActivity).filter(ProjectActivity.created_at < cutoff_date).delete()
    )

    db.commit()
    return int(deleted_count)
