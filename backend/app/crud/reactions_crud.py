# crud/reactions_crud.py
"""
CRUD operations for comment_reactions table
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


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
        equivalente a ON CONFLICT DO NOTHING
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
