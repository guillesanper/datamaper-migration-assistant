# crud/reactions_crud.py
"""
CRUD operations for comment_reactions table
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor


def add_reaction(db, comment_id: str, user_id: str, emoji: str) -> Optional[Dict[str, Any]]:
    """Add a reaction to a comment"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        reaction_id = str(uuid.uuid4())

        cur.execute(
            """
            INSERT INTO comment_reactions (id, comment_id, user_id, emoji, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (comment_id, user_id, emoji) DO NOTHING
            RETURNING *
        """,
            (reaction_id, comment_id, user_id, emoji, datetime.utcnow()),
        )

        result = cur.fetchone()
        db.commit()
        return dict(result) if result else None
    finally:
        cur.close()


def remove_reaction(db, comment_id: str, user_id: str, emoji: str) -> bool:
    """Remove a reaction from a comment"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            DELETE FROM comment_reactions
            WHERE comment_id = %s
            AND user_id = %s
            AND emoji = %s
        """,
            (comment_id, user_id, emoji),
        )

        deleted = cur.rowcount > 0
        db.commit()
        return bool(deleted)
    finally:
        cur.close()


def get_reactions_by_comment(db, comment_id: str) -> List[Dict[str, Any]]:
    """Get all reactions for a comment with user details"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT cr.*, u.username
            FROM comment_reactions cr
            LEFT JOIN users u ON cr.user_id = u.id
            WHERE cr.comment_id = %s
            ORDER BY cr.created_at ASC
        """,
            (comment_id,),
        )

        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def get_reaction_counts(db, comment_id: str) -> Dict[str, int]:
    """Get reaction counts grouped by emoji for a comment"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT emoji, COUNT(*) as count
            FROM comment_reactions
            WHERE comment_id = %s
            GROUP BY emoji
        """,
            (comment_id,),
        )

        results = cur.fetchall()
        return {row["emoji"]: row["count"] for row in results}
    finally:
        cur.close()


def check_user_reacted(db, comment_id: str, user_id: str, emoji: str) -> bool:
    """Check if a user has already reacted with a specific emoji"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT 1 FROM comment_reactions
            WHERE comment_id = %s
            AND user_id = %s
            AND emoji = %s
            LIMIT 1
        """,
            (comment_id, user_id, emoji),
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
Ejemplo: add_reaction() → add_reaction_orm()
"""


def add_reaction_orm(
    db, comment_id: str, user_id: str, emoji: str  # SQLAlchemy Session
) -> Optional[Dict[str, Any]]:
    """
    Add a reaction to a comment (ORM version)

    Args:
        db: SQLAlchemy Session
        comment_id: Comment UUID
        user_id: User UUID
        emoji: Emoji unicode string

    Returns:
        Dict with reaction data or None if already exists (ON CONFLICT DO NOTHING)

    Note:
        Usa IntegrityError para manejar UNIQUE constraint (comment_id, user_id, emoji)
        equivalente a ON CONFLICT DO NOTHING en la versión psycopg2
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.orm.comment import CommentReaction
    from app.utils.orm_helpers import model_to_dict

    new_reaction = CommentReaction(
        id=uuid.uuid4(),  # UUID object, no string
        comment_id=comment_id,
        user_id=user_id,
        emoji=emoji,
        created_at=datetime.utcnow(),
    )

    try:
        db.add(new_reaction)
        db.flush()  # Flush para detectar IntegrityError antes de commit
        db.commit()

        result: Dict[str, Any] = model_to_dict(new_reaction)  # type: ignore[assignment]
        return result
    except IntegrityError:
        # ON CONFLICT DO NOTHING equivalente - ya existe la reacción
        db.rollback()
        return None


def remove_reaction_orm(
    db, comment_id: str, user_id: str, emoji: str  # SQLAlchemy Session
) -> bool:
    """
    Remove a reaction from a comment (ORM version)

    Args:
        db: SQLAlchemy Session
        comment_id: Comment UUID
        user_id: User UUID
        emoji: Emoji unicode string

    Returns:
        True if reaction was deleted, False if not found
    """
    from app.models.orm.comment import CommentReaction

    deleted_count = (
        db.query(CommentReaction)
        .filter(
            CommentReaction.comment_id == comment_id,
            CommentReaction.user_id == user_id,
            CommentReaction.emoji == emoji,
        )
        .delete()
    )

    db.commit()
    return bool(deleted_count > 0)


def get_reactions_by_comment_orm(db, comment_id: str) -> List[Dict[str, Any]]:  # SQLAlchemy Session
    """
    Get all reactions for a comment with user details (ORM version)

    Args:
        db: SQLAlchemy Session
        comment_id: Comment UUID

    Returns:
        List of dicts with reaction data and username

    Note:
        Usa outerjoin con User para obtener username (puede ser NULL si user fue eliminado)
    """
    from app.models.orm.comment import CommentReaction
    from app.models.orm.user import User

    results = (
        db.query(CommentReaction, User.username)
        .outerjoin(User, CommentReaction.user_id == User.id)
        .filter(CommentReaction.comment_id == comment_id)
        .order_by(CommentReaction.created_at.asc())
        .all()
    )

    # Convertir resultados a lista de dicts
    return [
        {
            "id": str(reaction.id),
            "comment_id": str(reaction.comment_id),
            "user_id": str(reaction.user_id),
            "emoji": reaction.emoji,
            "created_at": reaction.created_at,
            "username": username,  # Puede ser None si user no existe
        }
        for reaction, username in results
    ]


def get_reaction_counts_orm(db, comment_id: str) -> Dict[str, int]:  # SQLAlchemy Session
    """
    Get reaction counts grouped by emoji for a comment (ORM version)

    Args:
        db: SQLAlchemy Session
        comment_id: Comment UUID

    Returns:
        Dict mapping emoji to count, e.g. {'👍': 5, '❤️': 3}
    """
    from sqlalchemy import func

    from app.models.orm.comment import CommentReaction

    results = (
        db.query(CommentReaction.emoji, func.count().label("count"))
        .filter(CommentReaction.comment_id == comment_id)
        .group_by(CommentReaction.emoji)
        .all()
    )

    return {emoji: count for emoji, count in results}


def check_user_reacted_orm(
    db, comment_id: str, user_id: str, emoji: str  # SQLAlchemy Session
) -> bool:
    """
    Check if a user has already reacted with a specific emoji (ORM version)

    Args:
        db: SQLAlchemy Session
        comment_id: Comment UUID
        user_id: User UUID
        emoji: Emoji unicode string

    Returns:
        True if user already reacted with this emoji, False otherwise
    """
    from app.models.orm.comment import CommentReaction

    exists = (
        db.query(CommentReaction.id)
        .filter(
            CommentReaction.comment_id == comment_id,
            CommentReaction.user_id == user_id,
            CommentReaction.emoji == emoji,
        )
        .limit(1)
        .first()
    )

    return exists is not None
