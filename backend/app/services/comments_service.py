# services/comments_service.py
"""
Business logic for comments and reactions
"""

import re
from typing import Any, Dict, List, Optional

from app.crud import activity_crud, comments_crud, reactions_crud


def extract_mentions(content: str) -> List[str]:
    """
    Extract @mentions from comment content.
    Returns list of usernames mentioned.
    """
    # Match @username (alphanumeric, underscore, dash)
    mention_pattern = r"@(\w+)"
    matches = re.findall(mention_pattern, content)
    return list(set(matches))  # Remove duplicates


def resolve_mentions_to_user_ids(db, usernames: List[str]) -> List[str]:
    """
    Convert usernames to user IDs.
    Returns list of user IDs.
    """
    if not usernames:
        return []

    from app.models.orm import User

    users = db.query(User.id).filter(User.username.in_(usernames)).all()
    return [str(user.id) for user in users]


def create_comment(
    db,
    entity_id: str,
    entity_type: str,
    project_id: str,
    user_id: str,
    content: str,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a comment with automatic mention extraction.
    """
    # Extract mentions
    mentioned_usernames = extract_mentions(content)
    mentioned_user_ids = resolve_mentions_to_user_ids(db, mentioned_usernames)

    # Create comment
    comment = comments_crud.create_comment_orm(
        db=db,
        entity_id=entity_id,
        entity_type=entity_type,
        project_id=project_id,
        user_id=user_id,
        content=content,
        parent_id=parent_id,
        mentions=mentioned_user_ids if mentioned_user_ids else None,
    )

    # Log activity (done by trigger, but only for top-level comments)
    # Triggers handle this automatically

    return comment


def edit_comment(db, comment_id: str, user_id: str, content: str) -> Optional[Dict[str, Any]]:
    """
    Edit a comment. Only the author can edit.
    Updates mentions if they changed.
    """
    # Extract new mentions
    mentioned_usernames = extract_mentions(content)
    mentioned_user_ids = resolve_mentions_to_user_ids(db, mentioned_usernames)

    # Update comment
    comment = comments_crud.update_comment_orm(db, comment_id, user_id, content)

    if comment:
        # Update mentions in the database using SQLAlchemy ORM
        from app.models.orm.comment import Comment

        db.query(Comment).filter(Comment.id == comment_id).update(
            {"mentions": mentioned_user_ids if mentioned_user_ids else None},
            synchronize_session=False,
        )
        db.commit()

    return comment


def delete_comment(db, comment_id: str, user_id: str) -> bool:
    """
    Delete a comment. Only the author can delete.
    Cascades to replies.
    """
    return comments_crud.delete_comment_orm(db, comment_id, user_id)


def resolve_comment(
    db, comment_id: str, resolved: bool, resolved_by: str, project_id: str
) -> Optional[Dict[str, Any]]:
    """Mark a comment as resolved or unresolved"""
    comment = comments_crud.resolve_comment_orm(db, comment_id, resolved, resolved_by)

    if comment:
        # Log activity
        activity_crud.create_activity_log_orm(
            db=db,
            project_id=project_id,
            user_id=resolved_by,
            activity_type="comment_resolved" if resolved else "comment_unresolved",
            entity_id=comment["entity_id"],
            entity_type=comment["entity_type"],
            description=f"{'Resolved' if resolved else 'Unresolved'} comment",
            metadata={"comment_id": comment_id},
        )

    return comment


def add_reaction(db, comment_id: str, user_id: str, emoji: str) -> Optional[Dict[str, Any]]:
    """Add a reaction to a comment"""
    return reactions_crud.add_reaction_orm(db, comment_id, user_id, emoji)


def remove_reaction(db, comment_id: str, user_id: str, emoji: str) -> bool:
    """Remove a reaction from a comment"""
    return reactions_crud.remove_reaction_orm(db, comment_id, user_id, emoji)


def get_comments(
    db,
    entity_id: str,
    entity_type: str,
    filters: Optional[Dict[str, Any]] = None,
    viewer_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get comments with optional filters and build tree structure.

    Con viewer_id solo se devuelven comentarios de proyectos a los que ese usuario tiene acceso.
    """
    filters = filters or {}

    comments = comments_crud.get_comments_orm(
        db=db,
        entity_id=entity_id,
        entity_type=entity_type,
        include_resolved=filters.get("include_resolved", True),
        include_replies=filters.get("include_replies", True),
        parent_id=filters.get("parent_id"),
        viewer_id=viewer_id,
    )

    # Get reactions for each comment
    for comment in comments:
        comment["reactions"] = reactions_crud.get_reactions_by_comment_orm(db, comment["id"])
        comment["reaction_counts"] = reactions_crud.get_reaction_counts_orm(db, comment["id"])

    return comments


def mark_as_read(db, comment_ids: List[str], user_id: str) -> int:
    """Mark comments as read. Returns count marked."""
    return comments_crud.mark_as_read_orm(db, comment_ids, user_id)


def get_unread_count(db, project_id: str, user_id: str) -> int:
    """Get count of unread comments for user in project"""
    return comments_crud.get_unread_count_orm(db, project_id, user_id)


def check_comment_permission(db, comment_id: str, user_id: str, action: str) -> bool:
    """
    Check if user has permission to perform action on comment.
    Actions: 'edit', 'delete'
    """
    if action in ["edit", "delete"]:
        # Only author can edit/delete their own comments
        return comments_crud.check_comment_owner_orm(db, comment_id, user_id)

    return False
