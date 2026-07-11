# crud/versions_crud.py
"""
CRUD operations for entity_versions table
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json, RealDictCursor


def create_version(
    db,
    project_id: str,
    entity_id: str,
    entity_type: str,
    user_id: str,
    version_number: int,
    change_type: str,
    snapshot: Dict[str, Any],
    hash: str,
    message: Optional[str] = None,
    diff: Optional[Dict[str, Any]] = None,
    parent_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new version entry"""
    print(f"[VERSION CRUD] create_version called")
    print(f"[VERSION CRUD] - project_id: {project_id}")
    print(f"[VERSION CRUD] - entity_id: {entity_id}")
    print(f"[VERSION CRUD] - entity_type: {entity_type}")
    print(f"[VERSION CRUD] - version_number: {version_number}")
    print(f"[VERSION CRUD] - change_type: {change_type}")

    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        version_id = str(uuid.uuid4())
        print(f"[VERSION CRUD] Generated version ID: {version_id}")

        print(f"[VERSION CRUD] Executing INSERT query...")
        cur.execute(
            """
            INSERT INTO entity_versions (
                id, hash, project_id, entity_id, entity_type, user_id,
                version_number, change_type, message, snapshot, diff,
                parent_version_id, is_encrypted, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """,
            (
                version_id,
                hash,
                project_id,
                entity_id,
                entity_type,
                user_id,
                version_number,
                change_type,
                message,
                Json(snapshot),
                Json(diff) if diff else None,
                parent_version_id,
                False,
                datetime.utcnow(),
            ),
        )

        result = cur.fetchone()
        print(f"[VERSION CRUD] INSERT successful, committing transaction...")
        db.commit()
        print(f"[VERSION CRUD] ✓ Version committed to database: {version_id}")
        return dict(result)
    except Exception as e:
        print(f"[VERSION CRUD] ✗ Database error occurred")
        print(f"[VERSION CRUD] Error type: {type(e).__name__}")
        print(f"[VERSION CRUD] Error message: {str(e)}")
        db.rollback()
        raise
    finally:
        cur.close()


def get_version_by_id(db, version_id: str) -> Optional[Dict[str, Any]]:
    """Get a version by its ID"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT ev.*, u.username, u.email as user_email
            FROM entity_versions ev
            LEFT JOIN users u ON ev.user_id = u.id
            WHERE ev.id = %s
        """,
            (version_id,),
        )

        result = cur.fetchone()
        return dict(result) if result else None
    finally:
        cur.close()


def get_version_by_hash(db, hash: str) -> Optional[Dict[str, Any]]:
    """Get a version by its hash (for deduplication)"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT * FROM entity_versions
            WHERE hash = %s
            LIMIT 1
        """,
            (hash,),
        )

        result = cur.fetchone()
        return dict(result) if result else None
    finally:
        cur.close()


def get_version_history(
    db,
    entity_id: str,
    limit: int = 50,
    offset: int = 0,
    change_type: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get version history for an entity with optional filters"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
            SELECT ev.*, u.username, u.email as user_email,
                   (SELECT COUNT(*) FROM version_tags WHERE version_id = ev.id) as tags_count
            FROM entity_versions ev
            LEFT JOIN users u ON ev.user_id = u.id
            WHERE ev.entity_id = %s
        """
        params: List[Any] = [entity_id]

        if change_type:
            query += " AND ev.change_type = %s"
            params.append(change_type)

        if user_id:
            query += " AND ev.user_id = %s"
            params.append(user_id)

        query += " ORDER BY ev.created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def get_project_versions(
    db,
    project_id: str,
    limit: int = 100,
    offset: int = 0,
    entity_type: Optional[str] = None,
    change_type: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get all versions for a project with optional filters"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
            SELECT ev.*, u.username, u.email as user_email,
                   (SELECT COUNT(*) FROM version_tags WHERE version_id = ev.id) as tags_count
            FROM entity_versions ev
            LEFT JOIN users u ON ev.user_id = u.id
            WHERE ev.project_id = %s
        """
        params: List[Any] = [project_id]

        if entity_type:
            query += " AND ev.entity_type = %s"
            params.append(entity_type)

        if change_type:
            query += " AND ev.change_type = %s"
            params.append(change_type)

        if user_id:
            query += " AND ev.user_id = %s"
            params.append(user_id)

        query += " ORDER BY ev.created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def get_next_version_number(db, entity_id: str) -> int:
    """Get the next version number for an entity"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT get_next_version_number(%s) as next_version", (entity_id,))
        result = cur.fetchone()
        if result:
            return int(result["next_version"])
        return 1
    finally:
        cur.close()


def get_latest_version(db, entity_id: str) -> Optional[Dict[str, Any]]:
    """Get the latest version for an entity"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT ev.*, u.username, u.email as user_email
            FROM entity_versions ev
            LEFT JOIN users u ON ev.user_id = u.id
            WHERE ev.entity_id = %s
            ORDER BY ev.version_number DESC
            LIMIT 1
        """,
            (entity_id,),
        )

        result = cur.fetchone()
        return dict(result) if result else None
    finally:
        cur.close()


def delete_version(db, version_id: str) -> bool:
    """Delete a version (soft delete by marking as deleted)"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            DELETE FROM entity_versions
            WHERE id = %s
        """,
            (version_id,),
        )

        deleted = cur.rowcount > 0
        db.commit()
        return bool(deleted)
    finally:
        cur.close()


def get_versions_count(db, entity_id: str) -> int:
    """Get total count of versions for an entity"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT COUNT(*) as count FROM entity_versions
            WHERE entity_id = %s
        """,
            (entity_id,),
        )

        result = cur.fetchone()
        return int(result["count"]) if result else 0
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
Ejemplo: create_version() → create_version_orm()
"""


def create_version_orm(
    db,  # SQLAlchemy Session
    project_id: str,
    entity_id: str,
    entity_type: str,
    user_id: str,
    version_number: int,
    change_type: str,
    snapshot: Dict[str, Any],
    hash: str,
    message: Optional[str] = None,
    diff: Optional[Dict[str, Any]] = None,
    parent_version_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new version entry (ORM version)"""
    import uuid as uuid_module
    from datetime import datetime, timezone

    from app.models.orm.version import EntityVersion
    from app.utils.orm_helpers import model_to_dict

    print(f"[VERSION CRUD ORM] create_version_orm called")
    print(f"[VERSION CRUD ORM] - project_id: {project_id}")
    print(f"[VERSION CRUD ORM] - entity_id: {entity_id}")
    print(f"[VERSION CRUD ORM] - entity_type: {entity_type}")
    print(f"[VERSION CRUD ORM] - version_number: {version_number}")
    print(f"[VERSION CRUD ORM] - change_type: {change_type}")

    version_id = uuid_module.uuid4()
    print(f"[VERSION CRUD ORM] Generated version ID: {version_id}")

    new_version = EntityVersion(
        id=version_id,
        hash=hash,
        project_id=project_id,
        entity_id=entity_id,
        entity_type=entity_type,
        user_id=user_id,
        version_number=version_number,
        change_type=change_type,
        message=message,
        snapshot=snapshot,
        diff=diff,
        parent_version_id=parent_version_id,
        created_at=datetime.now(timezone.utc),
    )

    print(f"[VERSION CRUD ORM] Adding version to session...")
    db.add(new_version)
    db.commit()
    db.refresh(new_version)

    print(f"[VERSION CRUD ORM] ✓ Version committed to database: {version_id}")
    result: Dict[str, Any] = model_to_dict(new_version)  # type: ignore[assignment]
    return result


def get_version_by_id_orm(db, version_id: str) -> Optional[Dict[str, Any]]:
    """Get a version by its ID (ORM version)"""
    from app.models.orm.user import User
    from app.models.orm.version import EntityVersion

    result = (
        db.query(EntityVersion, User.username, User.email)
        .outerjoin(User, EntityVersion.user_id == User.id)
        .filter(EntityVersion.id == version_id)
        .first()
    )

    if not result:
        return None

    version, username, email = result

    version_dict = {
        "id": str(version.id),
        "hash": version.hash,
        "project_id": str(version.project_id),
        "entity_id": str(version.entity_id),
        "entity_type": version.entity_type,
        "user_id": str(version.user_id),
        "version_number": version.version_number,
        "change_type": version.change_type,
        "message": version.message,
        "snapshot": version.snapshot,
        "diff": version.diff,
        "snapshot_encrypted": version.snapshot_encrypted,
        "snapshot_nonce": version.snapshot_nonce,
        "diff_encrypted": version.diff_encrypted,
        "diff_nonce": version.diff_nonce,
        "is_encrypted": version.is_encrypted,
        "parent_version_id": str(version.parent_version_id) if version.parent_version_id else None,
        "created_at": version.created_at,
        "username": username,
        "user_email": email,
    }

    return version_dict


def get_version_by_hash_orm(db, hash: str) -> Optional[Dict[str, Any]]:
    """Get a version by its hash (for deduplication) (ORM version)"""
    from app.models.orm.version import EntityVersion
    from app.utils.orm_helpers import model_to_dict

    version = db.query(EntityVersion).filter(EntityVersion.hash == hash).first()

    return model_to_dict(version) if version else None


def get_version_history_orm(
    db,
    entity_id: str,
    limit: int = 50,
    offset: int = 0,
    change_type: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get version history for an entity with optional filters (ORM version)"""
    from sqlalchemy import func

    from app.models.orm.user import User
    from app.models.orm.version import EntityVersion, VersionTag

    # Build base query with user info and tags count
    query = (
        db.query(
            EntityVersion, User.username, User.email, func.count(VersionTag.id).label("tags_count")
        )
        .outerjoin(User, EntityVersion.user_id == User.id)
        .outerjoin(VersionTag, EntityVersion.id == VersionTag.version_id)
        .filter(EntityVersion.entity_id == entity_id)
    )

    # Apply filters
    if change_type:
        query = query.filter(EntityVersion.change_type == change_type)

    if user_id:
        query = query.filter(EntityVersion.user_id == user_id)

    # Group by all EntityVersion columns and user info
    query = query.group_by(EntityVersion.id, User.username, User.email)

    # Order and paginate
    query = query.order_by(EntityVersion.created_at.desc())
    query = query.limit(limit).offset(offset)

    results = query.all()

    # Convert to dict list
    versions = []
    for version, username, email, tags_count in results:
        version_dict = {
            "id": str(version.id),
            "hash": version.hash,
            "project_id": str(version.project_id),
            "entity_id": str(version.entity_id),
            "entity_type": version.entity_type,
            "user_id": str(version.user_id),
            "version_number": version.version_number,
            "change_type": version.change_type,
            "message": version.message,
            "snapshot": version.snapshot,
            "diff": version.diff,
            "snapshot_encrypted": version.snapshot_encrypted,
            "snapshot_nonce": version.snapshot_nonce,
            "diff_encrypted": version.diff_encrypted,
            "diff_nonce": version.diff_nonce,
            "is_encrypted": version.is_encrypted,
            "parent_version_id": (
                str(version.parent_version_id) if version.parent_version_id else None
            ),
            "created_at": version.created_at,
            "username": username,
            "user_email": email,
            "tags_count": tags_count,
        }
        versions.append(version_dict)

    return versions


def get_project_versions_orm(
    db,
    project_id: str,
    limit: int = 100,
    offset: int = 0,
    entity_type: Optional[str] = None,
    change_type: Optional[str] = None,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get all versions for a project with optional filters (ORM version)"""
    from sqlalchemy import func

    from app.models.orm.user import User
    from app.models.orm.version import EntityVersion, VersionTag

    # Build base query with user info and tags count
    query = (
        db.query(
            EntityVersion, User.username, User.email, func.count(VersionTag.id).label("tags_count")
        )
        .outerjoin(User, EntityVersion.user_id == User.id)
        .outerjoin(VersionTag, EntityVersion.id == VersionTag.version_id)
        .filter(EntityVersion.project_id == project_id)
    )

    # Apply filters
    if entity_type:
        query = query.filter(EntityVersion.entity_type == entity_type)

    if change_type:
        query = query.filter(EntityVersion.change_type == change_type)

    if user_id:
        query = query.filter(EntityVersion.user_id == user_id)

    # Group by all EntityVersion columns and user info
    query = query.group_by(EntityVersion.id, User.username, User.email)

    # Order and paginate
    query = query.order_by(EntityVersion.created_at.desc())
    query = query.limit(limit).offset(offset)

    results = query.all()

    # Convert to dict list
    versions = []
    for version, username, email, tags_count in results:
        version_dict = {
            "id": str(version.id),
            "hash": version.hash,
            "project_id": str(version.project_id),
            "entity_id": str(version.entity_id),
            "entity_type": version.entity_type,
            "user_id": str(version.user_id),
            "version_number": version.version_number,
            "change_type": version.change_type,
            "message": version.message,
            "snapshot": version.snapshot,
            "diff": version.diff,
            "snapshot_encrypted": version.snapshot_encrypted,
            "snapshot_nonce": version.snapshot_nonce,
            "diff_encrypted": version.diff_encrypted,
            "diff_nonce": version.diff_nonce,
            "is_encrypted": version.is_encrypted,
            "parent_version_id": (
                str(version.parent_version_id) if version.parent_version_id else None
            ),
            "created_at": version.created_at,
            "username": username,
            "user_email": email,
            "tags_count": tags_count,
        }
        versions.append(version_dict)

    return versions


def get_next_version_number_orm(db, entity_id: str) -> int:
    """Get the next version number for an entity (ORM version)"""
    from sqlalchemy import func

    from app.models.orm.version import EntityVersion

    max_version = (
        db.query(func.max(EntityVersion.version_number))
        .filter(EntityVersion.entity_id == entity_id)
        .scalar()
    )

    return (max_version or 0) + 1


def get_latest_version_orm(db, entity_id: str) -> Optional[Dict[str, Any]]:
    """Get the latest version for an entity (ORM version)"""
    from app.models.orm.user import User
    from app.models.orm.version import EntityVersion

    result = (
        db.query(EntityVersion, User.username, User.email)
        .outerjoin(User, EntityVersion.user_id == User.id)
        .filter(EntityVersion.entity_id == entity_id)
        .order_by(EntityVersion.version_number.desc())
        .first()
    )

    if not result:
        return None

    version, username, email = result

    version_dict = {
        "id": str(version.id),
        "hash": version.hash,
        "project_id": str(version.project_id),
        "entity_id": str(version.entity_id),
        "entity_type": version.entity_type,
        "user_id": str(version.user_id),
        "version_number": version.version_number,
        "change_type": version.change_type,
        "message": version.message,
        "snapshot": version.snapshot,
        "diff": version.diff,
        "snapshot_encrypted": version.snapshot_encrypted,
        "snapshot_nonce": version.snapshot_nonce,
        "diff_encrypted": version.diff_encrypted,
        "diff_nonce": version.diff_nonce,
        "is_encrypted": version.is_encrypted,
        "parent_version_id": str(version.parent_version_id) if version.parent_version_id else None,
        "created_at": version.created_at,
        "username": username,
        "user_email": email,
    }

    return version_dict


def delete_version_orm(db, version_id: str) -> bool:
    """Delete a version (ORM version)"""
    from app.models.orm.version import EntityVersion

    deleted_count = db.query(EntityVersion).filter(EntityVersion.id == version_id).delete()

    db.commit()
    return bool(deleted_count > 0)


def get_versions_count_orm(db, entity_id: str) -> int:
    """Get total count of versions for an entity (ORM version)"""
    from app.models.orm.version import EntityVersion

    count = db.query(EntityVersion).filter(EntityVersion.entity_id == entity_id).count()

    return int(count)


def get_recent_versions_for_user(
    db, user_id: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Returns the most recent entity versions across all projects accessible by the user.

    A project is accessible if the user is owner OR a project member.
    """
    from sqlalchemy import or_, select

    from app.models.orm.project import Project, ProjectMember
    from app.models.orm.user import User
    from app.models.orm.version import EntityVersion

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
            EntityVersion.id,
            EntityVersion.project_id,
            Project.name.label("project_name"),
            EntityVersion.entity_type,
            EntityVersion.change_type,
            EntityVersion.message,
            EntityVersion.created_at,
            User.username.label("created_by_username"),
        )
        .join(Project, Project.id == EntityVersion.project_id)
        .outerjoin(User, User.id == EntityVersion.user_id)
        .filter(EntityVersion.project_id.in_(accessible_projects))
        .order_by(EntityVersion.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": str(r.id),
            "project_id": str(r.project_id),
            "project_name": r.project_name,
            "entity_type": r.entity_type,
            "change_type": r.change_type,
            "message": r.message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "created_by_username": r.created_by_username,
        }
        for r in rows
    ]
