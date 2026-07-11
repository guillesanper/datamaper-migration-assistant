# crud/comments_crud.py
"""
CRUD operations for comments table
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json, RealDictCursor


def create_comment(
    db,
    entity_id: str,
    entity_type: str,
    project_id: str,
    user_id: str,
    content: str,
    parent_id: Optional[str] = None,
    mentions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a new comment"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        comment_id = str(uuid.uuid4())

        cur.execute(
            """
            INSERT INTO comments (
                id, entity_id, entity_type, project_id, user_id,
                parent_id, content, mentions, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """,
            (
                comment_id,
                entity_id,
                entity_type,
                project_id,
                user_id,
                parent_id,
                content,
                Json(mentions) if mentions else None,
                datetime.utcnow(),
            ),
        )

        result = cur.fetchone()
        db.commit()
        return dict(result)
    finally:
        cur.close()


def update_comment(db, comment_id: str, user_id: str, content: str) -> Optional[Dict[str, Any]]:
    """Update a comment. Only the author can update their comment."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            UPDATE comments
            SET content = %s,
                updated_at = %s,
                is_edited = TRUE
            WHERE id = %s
            AND user_id = %s
            RETURNING *
        """,
            (content, datetime.utcnow(), comment_id, user_id),
        )

        result = cur.fetchone()
        db.commit()
        return dict(result) if result else None
    finally:
        cur.close()


def delete_comment(db, comment_id: str, user_id: str) -> bool:
    """Delete a comment. Only the author can delete their comment."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Check if user owns the comment
        cur.execute(
            """
            SELECT 1 FROM comments
            WHERE id = %s AND user_id = %s
        """,
            (comment_id, user_id),
        )

        if not cur.fetchone():
            return False

        # Delete comment (cascade will delete replies)
        cur.execute(
            """
            DELETE FROM comments
            WHERE id = %s
        """,
            (comment_id,),
        )

        deleted = cur.rowcount > 0
        db.commit()
        return bool(deleted)
    finally:
        cur.close()


def resolve_comment(
    db, comment_id: str, resolved: bool, resolved_by: str
) -> Optional[Dict[str, Any]]:
    """Mark a comment as resolved or unresolved"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            UPDATE comments
            SET is_resolved = %s,
                resolved_by = %s,
                resolved_at = %s
            WHERE id = %s
            RETURNING *
        """,
            (
                resolved,
                resolved_by if resolved else None,
                datetime.utcnow() if resolved else None,
                comment_id,
            ),
        )

        result = cur.fetchone()
        db.commit()
        return dict(result) if result else None
    finally:
        cur.close()


def get_comment_by_id(db, comment_id: str) -> Optional[Dict[str, Any]]:
    """Get a comment by ID with user details"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT c.*, u.username, u.email as user_email,
                   resolver.username as resolved_by_username,
                   (SELECT COUNT(*) FROM comment_reactions WHERE comment_id = c.id) as reactions_count,
                   (SELECT COUNT(*) FROM comments WHERE parent_id = c.id) as replies_count
            FROM comments c
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN users resolver ON c.resolved_by = resolver.id
            WHERE c.id = %s
        """,
            (comment_id,),
        )

        result = cur.fetchone()
        return dict(result) if result else None
    finally:
        cur.close()


def get_comments(
    db,
    entity_id: str,
    entity_type: str,
    include_resolved: bool = True,
    include_replies: bool = True,
    parent_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get comments for an entity with filters"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
            SELECT c.*, u.username, u.email as user_email,
                   resolver.username as resolved_by_username,
                   (SELECT COUNT(*) FROM comment_reactions WHERE comment_id = c.id) as reactions_count,
                   (SELECT COUNT(*) FROM comments WHERE parent_id = c.id) as replies_count
            FROM comments c
            LEFT JOIN users u ON c.user_id = u.id
            LEFT JOIN users resolver ON c.resolved_by = resolver.id
            WHERE c.entity_id = %s AND c.entity_type = %s
        """
        params = [entity_id, entity_type]

        if not include_resolved:
            query += " AND c.is_resolved = FALSE"

        if not include_replies:
            query += " AND c.parent_id IS NULL"
        elif parent_id:
            query += " AND c.parent_id = %s"
            params.append(parent_id)

        query += " ORDER BY c.created_at ASC"

        cur.execute(query, params)
        results = cur.fetchall()
        return [dict(row) for row in results]
    finally:
        cur.close()


def mark_as_read(db, comment_ids: List[str], user_id: str) -> int:
    """Mark comments as read for a user. Returns count of marked comments."""
    if not comment_ids:
        return 0

    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Use ON CONFLICT to avoid duplicates
        query = """
            INSERT INTO comment_reads (comment_id, user_id, read_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (comment_id, user_id) DO NOTHING
        """

        count = 0
        for comment_id in comment_ids:
            cur.execute(query, (comment_id, user_id, datetime.utcnow()))
            count += cur.rowcount

        db.commit()
        return count
    finally:
        cur.close()


def get_unread_count(db, project_id: str, user_id: str) -> int:
    """Get count of unread comments in a project for a user"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT COUNT(*) as count FROM comments c
            WHERE c.project_id = %s
            AND c.user_id != %s
            AND NOT EXISTS (
                SELECT 1 FROM comment_reads cr
                WHERE cr.comment_id = c.id
                AND cr.user_id = %s
            )
        """,
            (project_id, user_id, user_id),
        )

        result = cur.fetchone()
        return int(result["count"]) if result else 0
    finally:
        cur.close()


def check_comment_owner(db, comment_id: str, user_id: str) -> bool:
    """Check if user owns the comment"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT 1 FROM comments
            WHERE id = %s AND user_id = %s
            LIMIT 1
        """,
            (comment_id, user_id),
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
Ejemplo: create_comment() → create_comment_orm()
"""


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
