# crud/comments_crud.py
"""
CRUD operations for comments table
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


def create_comment_orm(
    db,  # SQLAlchemy Session
    entity_id: str,
    entity_type: str,
    project_id: str,
    user_id: str,
    content: str,
    parent_id: Optional[str] = None,
    mentions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a new comment (ORM version)"""
    import uuid as uuid_module
    from datetime import datetime, timezone

    from app.models.orm.comment import Comment
    from app.utils.orm_helpers import model_to_dict

    new_comment = Comment(
        id=uuid_module.uuid4(),
        entity_id=entity_id,
        entity_type=entity_type,
        project_id=project_id,
        user_id=user_id,
        parent_id=parent_id,
        content=content,
        mentions=mentions,  # JSONB array
        created_at=datetime.now(timezone.utc),
    )

    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    result: Dict[str, Any] = model_to_dict(new_comment)  # type: ignore[assignment]
    return result


def update_comment_orm(
    db, comment_id: str, user_id: str, content: str  # SQLAlchemy Session
) -> Optional[Dict[str, Any]]:
    """Update a comment. Only the author can update their comment (ORM version)"""
    from datetime import datetime, timezone

    from app.models.orm.comment import Comment
    from app.utils.orm_helpers import model_to_dict

    # Update only if user owns the comment
    updated_count = (
        db.query(Comment)
        .filter(Comment.id == comment_id)
        .filter(Comment.user_id == user_id)
        .update(
            {
                Comment.content: content,
                Comment.updated_at: datetime.now(timezone.utc),
                Comment.is_edited: True,
            }
        )
    )

    db.commit()

    if updated_count == 0:
        return None

    # Fetch updated comment
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    return model_to_dict(comment)


def delete_comment_orm(db, comment_id: str, user_id: str) -> bool:  # SQLAlchemy Session
    """Delete a comment. Only the author can delete their comment (ORM version)"""
    from app.models.orm.comment import Comment

    # Check if user owns the comment and delete
    deleted_count = (
        db.query(Comment)
        .filter(Comment.id == comment_id)
        .filter(Comment.user_id == user_id)
        .delete()
    )

    db.commit()
    return bool(deleted_count > 0)


def resolve_comment_orm(
    db, comment_id: str, resolved: bool, resolved_by: str  # SQLAlchemy Session
) -> Optional[Dict[str, Any]]:
    """Mark a comment as resolved or unresolved (ORM version)"""
    from datetime import datetime, timezone

    from app.models.orm.comment import Comment
    from app.utils.orm_helpers import model_to_dict

    update_data = {
        Comment.is_resolved: resolved,
        Comment.resolved_by: resolved_by if resolved else None,
        Comment.resolved_at: datetime.now(timezone.utc) if resolved else None,
    }

    updated_count = db.query(Comment).filter(Comment.id == comment_id).update(update_data)

    db.commit()

    if updated_count == 0:
        return None

    # Fetch updated comment
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    return model_to_dict(comment)


def get_comment_by_id_orm(db, comment_id: str) -> Optional[Dict[str, Any]]:
    """Get a comment by ID with user details (ORM version)"""
    from sqlalchemy import func

    from app.models.orm.comment import Comment, CommentReaction
    from app.models.orm.user import User

    # Query with JOINs and subqueries
    result = (
        db.query(
            Comment,
            User.username,
            User.email,
            func.coalesce(
                db.query(User.username)
                .filter(User.id == Comment.resolved_by)
                .correlate(Comment)
                .scalar_subquery(),
                None,
            ).label("resolved_by_username"),
            func.count(CommentReaction.id).label("reactions_count"),
            func.coalesce(
                db.query(func.count(Comment.id))
                .filter(Comment.parent_id == comment_id)
                .correlate(Comment)
                .scalar_subquery(),
                0,
            ).label("replies_count"),
        )
        .outerjoin(User, Comment.user_id == User.id)
        .outerjoin(CommentReaction, Comment.id == CommentReaction.comment_id)
        .filter(Comment.id == comment_id)
        .group_by(Comment.id, User.username, User.email)
        .first()
    )

    if not result:
        return None

    comment, username, email, resolved_by_username, reactions_count, replies_count = result

    comment_dict = {
        "id": str(comment.id),
        "entity_id": str(comment.entity_id),
        "entity_type": comment.entity_type,
        "project_id": str(comment.project_id),
        "user_id": str(comment.user_id),
        "parent_id": str(comment.parent_id) if comment.parent_id else None,
        "content": comment.content,
        "content_encrypted": comment.content_encrypted,
        "content_nonce": comment.content_nonce,
        "is_encrypted": comment.is_encrypted,
        "created_at": comment.created_at,
        "updated_at": comment.updated_at,
        "is_edited": comment.is_edited,
        "is_resolved": comment.is_resolved,
        "resolved_by": str(comment.resolved_by) if comment.resolved_by else None,
        "resolved_at": comment.resolved_at,
        "mentions": comment.mentions,
        "username": username,
        "user_email": email,
        "resolved_by_username": resolved_by_username,
        "reactions_count": reactions_count,
        "replies_count": replies_count,
    }

    return comment_dict


def get_comments_orm(
    db,  # SQLAlchemy Session
    entity_id: str,
    entity_type: str,
    include_resolved: bool = True,
    include_replies: bool = True,
    parent_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get comments for an entity with filters (ORM version)"""
    from sqlalchemy import func, literal

    from app.models.orm.comment import Comment, CommentReaction
    from app.models.orm.user import User

    # Build base query with JOINs
    query = (
        db.query(
            Comment,
            User.username,
            User.email,
            func.coalesce(
                db.query(User.username)
                .filter(User.id == Comment.resolved_by)
                .correlate(Comment)
                .scalar_subquery(),
                None,
            ).label("resolved_by_username"),
            func.count(CommentReaction.id).label("reactions_count"),
            func.coalesce(
                db.query(func.count())
                .select_from(Comment)
                .filter(Comment.parent_id == Comment.id)
                .correlate(Comment)
                .scalar_subquery(),
                0,
            ).label("replies_count"),
        )
        .outerjoin(User, Comment.user_id == User.id)
        .outerjoin(CommentReaction, Comment.id == CommentReaction.comment_id)
        .filter(Comment.entity_id == entity_id)
        .filter(Comment.entity_type == entity_type)
    )

    # Apply filters
    if not include_resolved:
        query = query.filter(Comment.is_resolved == False)

    if not include_replies:
        query = query.filter(Comment.parent_id.is_(None))
    elif parent_id:
        query = query.filter(Comment.parent_id == parent_id)

    # Group and order
    query = query.group_by(Comment.id, User.username, User.email)
    query = query.order_by(Comment.created_at.asc())

    results = query.all()

    # Convert to dict list
    comments = []
    for comment, username, email, resolved_by_username, reactions_count, replies_count in results:
        comment_dict = {
            "id": str(comment.id),
            "entity_id": str(comment.entity_id),
            "entity_type": comment.entity_type,
            "project_id": str(comment.project_id),
            "user_id": str(comment.user_id),
            "parent_id": str(comment.parent_id) if comment.parent_id else None,
            "content": comment.content,
            "content_encrypted": comment.content_encrypted,
            "content_nonce": comment.content_nonce,
            "is_encrypted": comment.is_encrypted,
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "is_edited": comment.is_edited,
            "is_resolved": comment.is_resolved,
            "resolved_by": str(comment.resolved_by) if comment.resolved_by else None,
            "resolved_at": comment.resolved_at,
            "mentions": comment.mentions,
            "username": username,
            "user_email": email,
            "resolved_by_username": resolved_by_username,
            "reactions_count": reactions_count,
            "replies_count": replies_count,
        }
        comments.append(comment_dict)

    return comments


def mark_as_read_orm(db, comment_ids: List[str], user_id: str) -> int:  # SQLAlchemy Session
    """Mark comments as read for a user. Returns count of marked comments (ORM version)"""
    if not comment_ids:
        return 0

    from datetime import datetime, timezone

    from sqlalchemy.exc import IntegrityError

    from app.models.orm.comment import CommentRead

    count = 0
    for comment_id in comment_ids:
        new_read = CommentRead(
            comment_id=comment_id, user_id=user_id, read_at=datetime.now(timezone.utc)
        )

        try:
            db.add(new_read)
            db.flush()  # Detect IntegrityError before commit
            count += 1
        except IntegrityError:
            # ON CONFLICT DO NOTHING equivalent
            db.rollback()

    db.commit()
    return count


def get_unread_count_orm(db, project_id: str, user_id: str) -> int:  # SQLAlchemy Session
    """Get count of unread comments in a project for a user (ORM version)"""
    from sqlalchemy import exists

    from app.models.orm.comment import Comment, CommentRead

    # Count comments where NOT EXISTS in comment_reads
    count = (
        db.query(Comment)
        .filter(Comment.project_id == project_id)
        .filter(Comment.user_id != user_id)
        .filter(
            ~exists().where(CommentRead.comment_id == Comment.id, CommentRead.user_id == user_id)
        )
        .count()
    )

    return int(count)


def check_comment_owner_orm(db, comment_id: str, user_id: str) -> bool:  # SQLAlchemy Session
    """Check if user owns the comment (ORM version)"""
    from app.models.orm.comment import Comment

    comment = (
        db.query(Comment)
        .filter(Comment.id == comment_id)
        .filter(Comment.user_id == user_id)
        .first()
    )

    return comment is not None
