# crud/activity_crud.py
"""
CRUD operations for project_activity table
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json, RealDictCursor


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
    """Create an activity log entry"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        activity_id = str(uuid.uuid4())

        cur.execute(
            """
            INSERT INTO project_activity (
                id, project_id, user_id, activity_type, entity_id,
                entity_type, description, metadata, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """,
            (
                activity_id,
                project_id,
                user_id,
                activity_type,
                entity_id,
                entity_type,
                description,
                Json(metadata) if metadata else None,
                datetime.utcnow(),
            ),
        )

        result = cur.fetchone()
        db.commit()
        return dict(result)
    finally:
        cur.close()


def get_project_activity(
    db,
    project_id: str,
    limit: int = 50,
    offset: int = 0,
    activity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get activity feed for a project with filters"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
            SELECT pa.*, u.username, u.email as user_email
            FROM project_activity pa
            LEFT JOIN users u ON pa.user_id = u.id
            WHERE pa.project_id = %s
        """
        params: List[Any] = [project_id]

        if activity_type:
            query += " AND pa.activity_type = %s"
            params.append(activity_type)

        if entity_id:
            query += " AND pa.entity_id = %s"
            params.append(entity_id)

        query += " ORDER BY pa.created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def get_entity_activity(
    db, entity_id: str, entity_type: str, limit: int = 50
) -> List[Dict[str, Any]]:
    """Get activity for a specific entity"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT pa.*, u.username, u.email as user_email
            FROM project_activity pa
            LEFT JOIN users u ON pa.user_id = u.id
            WHERE pa.entity_id = %s
            AND pa.entity_type = %s
            ORDER BY pa.created_at DESC
            LIMIT %s
        """,
            (entity_id, entity_type, limit),
        )

        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def get_user_activity(
    db, user_id: str, project_id: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """Get activity for a specific user"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
            SELECT pa.*, u.username, u.email as user_email
            FROM project_activity pa
            LEFT JOIN users u ON pa.user_id = u.id
            WHERE pa.user_id = %s
        """
        params: List[Any] = [user_id]

        if project_id:
            query += " AND pa.project_id = %s"
            params.append(project_id)

        query += " ORDER BY pa.created_at DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def get_activity_stats(db, project_id: str) -> Dict[str, int]:
    """Get activity statistics for a project"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT activity_type, COUNT(*) as count
            FROM project_activity
            WHERE project_id = %s
            GROUP BY activity_type
        """,
            (project_id,),
        )

        results = cur.fetchall()
        return {row["activity_type"]: row["count"] for row in results}
    finally:
        cur.close()


def delete_old_activity(db, days: int = 90) -> int:
    """Delete activity logs older than specified days. Returns count deleted."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            DELETE FROM project_activity
            WHERE created_at < NOW() - INTERVAL '%s days'
        """,
            (days,),
        )

        deleted = cur.rowcount
        db.commit()
        return int(deleted)
    finally:
        cur.close()


# ============================================================================
# SQLAlchemy ORM Versions
# ============================================================================
"""
Las siguientes funciones son versiones ORM de las funciones anteriores.
Usan SQLAlchemy Session en vez de psycopg2.connection.
Mantienen exactamente la misma interfaz (parámetros y retorno).

IMPORTANTE: El campo 'metadata' en BD se llama 'activity_metadata' en el modelo ORM.
Al retornar dicts, se mapea manualmente activity_metadata → 'metadata' para mantener
compatibilidad con la interfaz antigua.

Nomenclatura: Todas las funciones ORM tienen sufijo _orm
Ejemplo: create_activity_log() → create_activity_log_orm()
"""


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
