# crud/tags_crud.py
"""
CRUD operations for version_tags table
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor


def create_tag(
    db,
    version_id: str,
    project_id: str,
    name: str,
    created_by: str,
    description: Optional[str] = None,
    color: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new version tag"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        tag_id = str(uuid.uuid4())

        cur.execute(
            """
            INSERT INTO version_tags (
                id, version_id, project_id, name, description, color, created_by, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """,
            (
                tag_id,
                version_id,
                project_id,
                name,
                description,
                color,
                created_by,
                datetime.utcnow(),
            ),
        )

        result = cur.fetchone()
        db.commit()
        return dict(result)
    finally:
        cur.close()


def get_tag_by_id(db, tag_id: str) -> Optional[Dict[str, Any]]:
    """Get a tag by its ID"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT vt.*, u.username as creator_username
            FROM version_tags vt
            LEFT JOIN users u ON vt.created_by = u.id
            WHERE vt.id = %s
        """,
            (tag_id,),
        )

        result = cur.fetchone()
        return dict(result) if result else None
    finally:
        cur.close()


def get_tags_by_project(db, project_id: str) -> List[Dict[str, Any]]:
    """Get all tags for a project"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT vt.*, u.username as creator_username,
                   ev.entity_id, ev.entity_type, ev.version_number
            FROM version_tags vt
            LEFT JOIN users u ON vt.created_by = u.id
            LEFT JOIN entity_versions ev ON vt.version_id = ev.id
            WHERE vt.project_id = %s
            ORDER BY vt.created_at DESC
        """,
            (project_id,),
        )

        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def get_tags_by_version(db, version_id: str) -> List[Dict[str, Any]]:
    """Get all tags for a specific version"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT vt.*, u.username as creator_username
            FROM version_tags vt
            LEFT JOIN users u ON vt.created_by = u.id
            WHERE vt.version_id = %s
            ORDER BY vt.created_at DESC
        """,
            (version_id,),
        )

        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def delete_tag(db, tag_id: str) -> bool:
    """Delete a tag"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            DELETE FROM version_tags
            WHERE id = %s
        """,
            (tag_id,),
        )

        deleted = cur.rowcount > 0
        db.commit()
        return bool(deleted)
    finally:
        cur.close()


def check_tag_exists(db, project_id: str, name: str) -> bool:
    """Check if a tag with the given name already exists in the project"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT 1 FROM version_tags
            WHERE project_id = %s AND name = %s
            LIMIT 1
        """,
            (project_id, name),
        )

        return cur.fetchone() is not None
    finally:
        cur.close()


# ============================================================================
# SQLAlchemy ORM Versions
# ============================================================================
"""
Las siguientes funciones son versiones ORM de las funciones anteriores.
Usan SQLAlchemy Session en vez de psycopg2.connection.
Mantienen exactamente la misma interfaz (parámetros y retorno).

Nomenclatura: Todas las funciones ORM tienen sufijo _orm
Ejemplo: create_tag() → create_tag_orm()
"""


def create_tag_orm(
    db,  # SQLAlchemy Session
    version_id: str,
    project_id: str,
    name: str,
    created_by: str,
    description: Optional[str] = None,
    color: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new version tag (ORM version)

    Args:
        db: SQLAlchemy Session
        version_id: Version UUID
        project_id: Project UUID
        name: Tag name
        created_by: User UUID
        description: Optional tag description
        color: Optional hex color (#FF5733)

    Returns:
        Dict with tag data
    """
    from app.models.orm.version import VersionTag
    from app.utils.orm_helpers import model_to_dict

    new_tag = VersionTag(
        id=uuid.uuid4(),  # UUID object, no string
        version_id=version_id,
        project_id=project_id,
        name=name,
        description=description,
        color=color,
        created_by=created_by,
        created_at=datetime.utcnow(),
    )

    db.add(new_tag)
    db.commit()

    result: Dict[str, Any] = model_to_dict(new_tag)  # type: ignore[assignment]
    return result


def get_tag_by_id_orm(db, tag_id: str) -> Optional[Dict[str, Any]]:  # SQLAlchemy Session
    """
    Get a tag by its ID (ORM version)

    Args:
        db: SQLAlchemy Session
        tag_id: Tag UUID

    Returns:
        Dict with tag data and creator_username, or None if not found

    Note:
        Usa outerjoin con User para obtener creator_username (puede ser NULL si user fue eliminado)
    """
    from app.models.orm.user import User
    from app.models.orm.version import VersionTag

    result = (
        db.query(VersionTag, User.username)
        .outerjoin(User, VersionTag.created_by == User.id)
        .filter(VersionTag.id == tag_id)
        .first()
    )

    if not result:
        return None

    tag, creator_username = result

    return {
        "id": str(tag.id),
        "version_id": str(tag.version_id),
        "project_id": str(tag.project_id),
        "name": tag.name,
        "description": tag.description,
        "color": tag.color,
        "created_by": str(tag.created_by),
        "created_at": tag.created_at,
        "creator_username": creator_username,  # Puede ser None si user no existe
    }


def get_tags_by_project_orm(db, project_id: str) -> List[Dict[str, Any]]:  # SQLAlchemy Session
    """
    Get all tags for a project (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: Project UUID

    Returns:
        List of dicts with tag data, creator_username, and version info

    Note:
        Usa outerjoin con User y EntityVersion para obtener información relacionada
    """
    from app.models.orm.user import User
    from app.models.orm.version import EntityVersion, VersionTag

    results = (
        db.query(
            VersionTag,
            User.username,
            EntityVersion.entity_id,
            EntityVersion.entity_type,
            EntityVersion.version_number,
        )
        .outerjoin(User, VersionTag.created_by == User.id)
        .outerjoin(EntityVersion, VersionTag.version_id == EntityVersion.id)
        .filter(VersionTag.project_id == project_id)
        .order_by(VersionTag.created_at.desc())
        .all()
    )

    # Convertir resultados a lista de dicts
    return [
        {
            "id": str(tag.id),
            "version_id": str(tag.version_id),
            "project_id": str(tag.project_id),
            "name": tag.name,
            "description": tag.description,
            "color": tag.color,
            "created_by": str(tag.created_by),
            "created_at": tag.created_at,
            "creator_username": username,  # Puede ser None si user no existe
            "entity_id": str(entity_id) if entity_id else None,
            "entity_type": entity_type,
            "version_number": version_number,
        }
        for tag, username, entity_id, entity_type, version_number in results
    ]


def get_tags_by_version_orm(db, version_id: str) -> List[Dict[str, Any]]:  # SQLAlchemy Session
    """
    Get all tags for a specific version (ORM version)

    Args:
        db: SQLAlchemy Session
        version_id: Version UUID

    Returns:
        List of dicts with tag data and creator_username

    Note:
        Usa outerjoin con User para obtener creator_username (puede ser NULL si user fue eliminado)
    """
    from app.models.orm.user import User
    from app.models.orm.version import VersionTag

    results = (
        db.query(VersionTag, User.username)
        .outerjoin(User, VersionTag.created_by == User.id)
        .filter(VersionTag.version_id == version_id)
        .order_by(VersionTag.created_at.desc())
        .all()
    )

    # Convertir resultados a lista de dicts
    return [
        {
            "id": str(tag.id),
            "version_id": str(tag.version_id),
            "project_id": str(tag.project_id),
            "name": tag.name,
            "description": tag.description,
            "color": tag.color,
            "created_by": str(tag.created_by),
            "created_at": tag.created_at,
            "creator_username": username,  # Puede ser None si user no existe
        }
        for tag, username in results
    ]


def delete_tag_orm(db, tag_id: str) -> bool:  # SQLAlchemy Session
    """
    Delete a tag (ORM version)

    Args:
        db: SQLAlchemy Session
        tag_id: Tag UUID

    Returns:
        True if tag was deleted, False if not found
    """
    from app.models.orm.version import VersionTag

    deleted_count = db.query(VersionTag).filter(VersionTag.id == tag_id).delete()

    db.commit()
    return bool(deleted_count > 0)


def check_tag_exists_orm(db, project_id: str, name: str) -> bool:  # SQLAlchemy Session
    """
    Check if a tag with the given name already exists in the project (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: Project UUID
        name: Tag name

    Returns:
        True if tag exists, False otherwise
    """
    from app.models.orm.version import VersionTag

    exists = (
        db.query(VersionTag.id)
        .filter(VersionTag.project_id == project_id, VersionTag.name == name)
        .limit(1)
        .first()
    )

    return exists is not None
