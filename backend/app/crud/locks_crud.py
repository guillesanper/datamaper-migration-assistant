# crud/locks_crud.py
"""
CRUD operations for entity_locks table
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

# Lock duration in minutes
DEFAULT_LOCK_DURATION = 15


def acquire_lock(
    db,
    entity_id: str,
    entity_type: str,
    project_id: str,
    user_id: str,
    duration_minutes: int = DEFAULT_LOCK_DURATION,
) -> Optional[Dict[str, Any]]:
    """
    Try to acquire a lock on an entity.
    Returns the lock if successful, None if entity is already locked by another user.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # First, clean up expired locks
        cleanup_expired_locks(db)

        # Check if lock exists and is still valid
        cur.execute(
            """
            SELECT * FROM entity_locks
            WHERE entity_id = %s AND entity_type = %s
            AND expires_at > NOW()
        """,
            (entity_id, entity_type),
        )

        existing_lock = cur.fetchone()

        # If lock exists and belongs to someone else, return None
        if existing_lock and str(existing_lock["user_id"]) != str(user_id):
            return None

        # If lock exists and belongs to this user, update it (renew)
        if existing_lock and str(existing_lock["user_id"]) == str(user_id):
            cur.execute(
                """
                UPDATE entity_locks
                SET expires_at = %s,
                    last_heartbeat = NOW()
                WHERE entity_id = %s AND entity_type = %s
                RETURNING *
            """,
                (datetime.utcnow() + timedelta(minutes=duration_minutes), entity_id, entity_type),
            )
        else:
            # Create new lock
            lock_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO entity_locks (
                    id, entity_id, entity_type, project_id, user_id,
                    acquired_at, expires_at, last_heartbeat
                )
                VALUES (%s, %s, %s, %s, %s, NOW(), %s, NOW())
                RETURNING *
            """,
                (
                    lock_id,
                    entity_id,
                    entity_type,
                    project_id,
                    user_id,
                    datetime.utcnow() + timedelta(minutes=duration_minutes),
                ),
            )

        result = cur.fetchone()
        db.commit()
        return dict(result) if result else None
    finally:
        cur.close()


def release_lock(db, entity_id: str, entity_type: str, user_id: str) -> bool:
    """
    Release a lock. Only the owner can release their own lock.
    Returns True if lock was released, False if no lock found or user is not owner.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            DELETE FROM entity_locks
            WHERE entity_id = %s
            AND entity_type = %s
            AND user_id = %s
        """,
            (entity_id, entity_type, user_id),
        )

        deleted = cur.rowcount > 0
        db.commit()
        return bool(deleted)
    finally:
        cur.close()


def get_lock_status(db, entity_id: str, entity_type: str) -> Optional[Dict[str, Any]]:
    """
    Get current lock status for an entity.
    Returns lock info with user details if locked, None if not locked.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Clean up expired locks first
        cleanup_expired_locks(db)

        cur.execute(
            """
            SELECT el.*, u.username, u.email as user_email
            FROM entity_locks el
            LEFT JOIN users u ON el.user_id = u.id
            WHERE el.entity_id = %s
            AND el.entity_type = %s
            AND el.expires_at > NOW()
        """,
            (entity_id, entity_type),
        )

        result = cur.fetchone()
        return dict(result) if result else None
    finally:
        cur.close()


def renew_lock(
    db, lock_id: str, user_id: str, duration_minutes: int = DEFAULT_LOCK_DURATION
) -> Optional[Dict[str, Any]]:
    """
    Renew a lock (heartbeat). Only the owner can renew their lock.
    Returns updated lock or None if lock not found or user is not owner.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            UPDATE entity_locks
            SET expires_at = %s,
                last_heartbeat = NOW()
            WHERE id = %s
            AND user_id = %s
            RETURNING *
        """,
            (datetime.utcnow() + timedelta(minutes=duration_minutes), lock_id, user_id),
        )

        result = cur.fetchone()
        db.commit()
        return dict(result) if result else None
    finally:
        cur.close()


def force_unlock(db, entity_id: str, entity_type: str) -> bool:
    """
    Force unlock an entity (admin action).
    Returns True if lock was removed, False if no lock found.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            DELETE FROM entity_locks
            WHERE entity_id = %s
            AND entity_type = %s
        """,
            (entity_id, entity_type),
        )

        deleted = cur.rowcount > 0
        db.commit()
        return bool(deleted)
    finally:
        cur.close()


def get_active_locks(db, project_id: str) -> List[Dict[str, Any]]:
    """Get all active locks for a project"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Clean up expired first
        cleanup_expired_locks(db)

        cur.execute(
            """
            SELECT el.*, u.username, u.email as user_email
            FROM entity_locks el
            LEFT JOIN users u ON el.user_id = u.id
            WHERE el.project_id = %s
            AND el.expires_at > NOW()
            ORDER BY el.acquired_at DESC
        """,
            (project_id,),
        )

        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def get_user_locks(db, user_id: str) -> List[Dict[str, Any]]:
    """Get all active locks for a user"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT * FROM entity_locks
            WHERE user_id = %s
            AND expires_at > NOW()
            ORDER BY acquired_at DESC
        """,
            (user_id,),
        )

        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def cleanup_expired_locks(db) -> int:
    """
    Clean up expired locks.
    Returns number of locks deleted.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT cleanup_expired_locks() as deleted_count")
        result = cur.fetchone()
        db.commit()
        return int(result["deleted_count"]) if result else 0
    finally:
        cur.close()


def check_lock_owner(db, entity_id: str, entity_type: str, user_id: str) -> bool:
    """Check if the specified user owns the lock on the entity"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT 1 FROM entity_locks
            WHERE entity_id = %s
            AND entity_type = %s
            AND user_id = %s
            AND expires_at > NOW()
            LIMIT 1
        """,
            (entity_id, entity_type, user_id),
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
Ejemplo: acquire_lock() → acquire_lock_orm()
"""


def cleanup_expired_locks_orm(db) -> int:
    """
    Clean up expired locks (ORM version).
    Returns number of locks deleted.
    """
    from datetime import datetime, timezone

    from app.models.orm.lock import EntityLock

    deleted_count = (
        db.query(EntityLock).filter(EntityLock.expires_at <= datetime.now(timezone.utc)).delete()
    )

    db.commit()
    return int(deleted_count)


def acquire_lock_orm(
    db,  # SQLAlchemy Session
    entity_id: str,
    entity_type: str,
    project_id: str,
    user_id: str,
    duration_minutes: int = DEFAULT_LOCK_DURATION,
) -> Optional[Dict[str, Any]]:
    """
    Try to acquire a lock on an entity (ORM version).
    Returns the lock if successful, None if entity is already locked by another user.
    """
    import uuid as uuid_module
    from datetime import datetime, timedelta, timezone

    from app.models.orm.lock import EntityLock
    from app.utils.orm_helpers import model_to_dict

    # First, clean up expired locks
    cleanup_expired_locks_orm(db)

    # Check if lock exists and is still valid
    existing_lock = (
        db.query(EntityLock)
        .filter(EntityLock.entity_id == entity_id)
        .filter(EntityLock.entity_type == entity_type)
        .filter(EntityLock.expires_at > datetime.now(timezone.utc))
        .first()
    )

    # If lock exists and belongs to someone else, return None
    if existing_lock and str(existing_lock.user_id) != str(user_id):
        return None

    # If lock exists and belongs to this user, update it (renew)
    if existing_lock and str(existing_lock.user_id) == str(user_id):
        existing_lock.expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        existing_lock.last_heartbeat = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing_lock)
        return model_to_dict(existing_lock)

    # Create new lock
    new_lock = EntityLock(
        id=uuid_module.uuid4(),
        entity_id=entity_id,
        entity_type=entity_type,
        project_id=project_id,
        user_id=user_id,
        acquired_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=duration_minutes),
        last_heartbeat=datetime.now(timezone.utc),
    )

    db.add(new_lock)
    db.commit()
    db.refresh(new_lock)

    return model_to_dict(new_lock)


def release_lock_orm(
    db, entity_id: str, entity_type: str, user_id: str  # SQLAlchemy Session
) -> bool:
    """
    Release a lock (ORM version). Only the owner can release their own lock.
    Returns True if lock was released, False if no lock found or user is not owner.
    """
    from app.models.orm.lock import EntityLock

    deleted_count = (
        db.query(EntityLock)
        .filter(EntityLock.entity_id == entity_id)
        .filter(EntityLock.entity_type == entity_type)
        .filter(EntityLock.user_id == user_id)
        .delete()
    )

    db.commit()
    return bool(deleted_count > 0)


def get_lock_status_orm(
    db, entity_id: str, entity_type: str  # SQLAlchemy Session
) -> Optional[Dict[str, Any]]:
    """
    Get current lock status for an entity (ORM version).
    Returns lock info with user details if locked, None if not locked.
    """
    from datetime import datetime, timezone

    from app.models.orm.lock import EntityLock
    from app.models.orm.user import User

    # Clean up expired locks first
    cleanup_expired_locks_orm(db)

    result = (
        db.query(EntityLock, User.username, User.email)
        .outerjoin(User, EntityLock.user_id == User.id)
        .filter(EntityLock.entity_id == entity_id)
        .filter(EntityLock.entity_type == entity_type)
        .filter(EntityLock.expires_at > datetime.now(timezone.utc))
        .first()
    )

    if not result:
        return None

    lock, username, email = result

    return {
        "id": str(lock.id),
        "entity_id": str(lock.entity_id),
        "entity_type": lock.entity_type,
        "project_id": str(lock.project_id),
        "user_id": str(lock.user_id),
        "acquired_at": lock.acquired_at,
        "expires_at": lock.expires_at,
        "last_heartbeat": lock.last_heartbeat,
        "username": username,
        "user_email": email,
    }


def renew_lock_orm(
    db,  # SQLAlchemy Session
    lock_id: str,
    user_id: str,
    duration_minutes: int = DEFAULT_LOCK_DURATION,
) -> Optional[Dict[str, Any]]:
    """
    Renew a lock (heartbeat) (ORM version). Only the owner can renew their lock.
    Returns updated lock or None if lock not found or user is not owner.
    """
    from datetime import datetime, timedelta, timezone

    from app.models.orm.lock import EntityLock
    from app.utils.orm_helpers import model_to_dict

    lock = (
        db.query(EntityLock)
        .filter(EntityLock.id == lock_id)
        .filter(EntityLock.user_id == user_id)
        .first()
    )

    if not lock:
        return None

    lock.expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
    lock.last_heartbeat = datetime.now(timezone.utc)

    db.commit()
    db.refresh(lock)

    return model_to_dict(lock)


def force_unlock_orm(db, entity_id: str, entity_type: str) -> bool:  # SQLAlchemy Session
    """
    Force unlock an entity (admin action) (ORM version).
    Returns True if lock was removed, False if no lock found.
    """
    from app.models.orm.lock import EntityLock

    deleted_count = (
        db.query(EntityLock)
        .filter(EntityLock.entity_id == entity_id)
        .filter(EntityLock.entity_type == entity_type)
        .delete()
    )

    db.commit()
    return bool(deleted_count > 0)


def get_active_locks_orm(db, project_id: str) -> List[Dict[str, Any]]:  # SQLAlchemy Session
    """Get all active locks for a project (ORM version)"""
    from datetime import datetime, timezone

    from app.models.orm.lock import EntityLock
    from app.models.orm.user import User

    # Clean up expired first
    cleanup_expired_locks_orm(db)

    results = (
        db.query(EntityLock, User.username, User.email)
        .outerjoin(User, EntityLock.user_id == User.id)
        .filter(EntityLock.project_id == project_id)
        .filter(EntityLock.expires_at > datetime.now(timezone.utc))
        .order_by(EntityLock.acquired_at.desc())
        .all()
    )

    return [
        {
            "id": str(lock.id),
            "entity_id": str(lock.entity_id),
            "entity_type": lock.entity_type,
            "project_id": str(lock.project_id),
            "user_id": str(lock.user_id),
            "acquired_at": lock.acquired_at,
            "expires_at": lock.expires_at,
            "last_heartbeat": lock.last_heartbeat,
            "username": username,
            "user_email": email,
        }
        for lock, username, email in results
    ]


def get_user_locks_orm(db, user_id: str) -> List[Dict[str, Any]]:  # SQLAlchemy Session
    """Get all active locks for a user (ORM version)"""
    from datetime import datetime, timezone

    from app.models.orm.lock import EntityLock
    from app.utils.orm_helpers import models_to_dict_list

    locks = (
        db.query(EntityLock)
        .filter(EntityLock.user_id == user_id)
        .filter(EntityLock.expires_at > datetime.now(timezone.utc))
        .order_by(EntityLock.acquired_at.desc())
        .all()
    )

    return models_to_dict_list(locks)


def check_lock_owner_orm(
    db, entity_id: str, entity_type: str, user_id: str  # SQLAlchemy Session
) -> bool:
    """Check if the specified user owns the lock on the entity (ORM version)"""
    from datetime import datetime, timezone

    from app.models.orm.lock import EntityLock

    exists = (
        db.query(EntityLock.id)
        .filter(EntityLock.entity_id == entity_id)
        .filter(EntityLock.entity_type == entity_type)
        .filter(EntityLock.user_id == user_id)
        .filter(EntityLock.expires_at > datetime.now(timezone.utc))
        .limit(1)
        .first()
    )

    return exists is not None
