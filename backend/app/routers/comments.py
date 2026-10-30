# routers/comments.py
"""
API endpoints for comments and reactions
"""

import asyncio
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from app.database.session import get_db_session as get_db
from app.routers.dependencies import get_current_user, require_project_access
from app.routers.realtime import realtime_broadcast
from app.services import comments_service

router = APIRouter(prefix="/api", tags=["comments"])


# Helper function to schedule realtime broadcast
def schedule_broadcast(background_tasks: BackgroundTasks, project_id: str, payload: dict):
    """Schedule realtime broadcast as a background task"""

    async def _broadcast():
        try:
            await realtime_broadcast(project_id, payload)
        except Exception as e:
            print(f"[Realtime Broadcast Error] {e}")

    background_tasks.add_task(_broadcast)


def _get_accessible_comment(db, comment_id: str, current_user: dict) -> dict:
    """
    Devuelve el comentario si el usuario tiene acceso a su proyecto.

    Un comentario inexistente y uno de un proyecto ajeno responden igual (404).
    """
    from app.crud import comments_crud

    try:
        uuid.UUID(str(comment_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Comment not found")

    comment = comments_crud.get_comment_by_id_orm(db, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    try:
        require_project_access(db, comment["project_id"], current_user["id"])
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="Comment not found")
        raise
    return comment


# Pydantic models
class CreateCommentRequest(BaseModel):
    entity_id: str
    entity_type: str  # 'mapping', 'table', 'column', 'project'
    project_id: str
    content: str
    parent_id: Optional[str] = None


class UpdateCommentRequest(BaseModel):
    content: str


class ResolveCommentRequest(BaseModel):
    resolved: bool
    project_id: str


class AddReactionRequest(BaseModel):
    emoji: str


class MarkReadRequest(BaseModel):
    comment_ids: List[str]


# Endpoints
@router.post("/comments")
def create_comment(
    payload: CreateCommentRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new comment"""
    require_project_access(db, payload.project_id, current_user["id"])
    if payload.parent_id:
        parent = _get_accessible_comment(db, payload.parent_id, current_user)
        if parent["project_id"] != str(payload.project_id):
            raise HTTPException(status_code=400, detail="Parent comment belongs to another project")
    try:
        # Validate content
        if not payload.content or len(payload.content.strip()) == 0:
            raise HTTPException(status_code=400, detail="Comment content cannot be empty")

        if len(payload.content) > 4000:
            raise HTTPException(status_code=400, detail="Comment content too long (max 4000 chars)")

        comment = comments_service.create_comment(
            db=db,
            entity_id=payload.entity_id,
            entity_type=payload.entity_type,
            project_id=payload.project_id,
            user_id=current_user["id"],
            content=payload.content,
            parent_id=payload.parent_id,
        )

        # Broadcast real-time event
        schedule_broadcast(
            background_tasks,
            payload.project_id,
            {"type": "comment:added", "comment": comment, "actor_id": str(current_user["id"])},
        )

        return {
            "success": True,
            "data": {"comment": comment},
            "message": "Comment created successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating comment: {str(e)}")


@router.put("/comments/{comment_id}")
def update_comment(
    comment_id: str,
    payload: UpdateCommentRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a comment (only author can update)"""
    _get_accessible_comment(db, comment_id, current_user)
    try:
        # Validate content
        if not payload.content or len(payload.content.strip()) == 0:
            raise HTTPException(status_code=400, detail="Comment content cannot be empty")

        comment = comments_service.edit_comment(
            db=db, comment_id=comment_id, user_id=current_user["id"], content=payload.content
        )

        if not comment:
            raise HTTPException(
                status_code=403, detail="Comment not found or you don't have permission to edit it"
            )

        # Broadcast real-time event
        schedule_broadcast(
            background_tasks,
            comment["project_id"],
            {"type": "comment:edited", "comment": comment, "actor_id": str(current_user["id"])},
        )

        return {
            "success": True,
            "data": {"comment": comment},
            "message": "Comment updated successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating comment: {str(e)}")


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: str,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a comment (only author can delete)"""
    comment = _get_accessible_comment(db, comment_id, current_user)
    try:
        deleted = comments_service.delete_comment(
            db=db, comment_id=comment_id, user_id=current_user["id"]
        )

        if not deleted:
            raise HTTPException(
                status_code=403, detail="You don't have permission to delete this comment"
            )

        # Broadcast real-time event
        schedule_broadcast(
            background_tasks,
            comment["project_id"],
            {
                "type": "comment:deleted",
                "comment_id": comment_id,
                "entity_id": comment["entity_id"],
                "actor_id": str(current_user["id"]),
            },
        )

        return {
            "success": True,
            "data": {"deleted": True},
            "message": "Comment deleted successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting comment: {str(e)}")


@router.patch("/comments/{comment_id}/resolve")
def resolve_comment(
    comment_id: str,
    payload: ResolveCommentRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Mark a comment as resolved or unresolved"""
    # El proyecto sale del propio comentario, no del payload
    project_id = _get_accessible_comment(db, comment_id, current_user)["project_id"]
    try:
        comment = comments_service.resolve_comment(
            db=db,
            comment_id=comment_id,
            resolved=payload.resolved,
            resolved_by=current_user["id"],
            project_id=project_id,
        )

        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        # Broadcast real-time event
        schedule_broadcast(
            background_tasks,
            project_id,
            {
                "type": "comment:resolved" if payload.resolved else "comment:unresolved",
                "comment": comment,
                "actor_id": str(current_user["id"]),
            },
        )

        return {
            "success": True,
            "data": {"comment": comment},
            "message": f"Comment {'resolved' if payload.resolved else 'unresolved'} successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resolving comment: {str(e)}")


@router.post("/comments/{comment_id}/reactions")
def add_reaction(
    comment_id: str,
    payload: AddReactionRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Add a reaction to a comment"""
    _get_accessible_comment(db, comment_id, current_user)
    try:
        reaction = comments_service.add_reaction(
            db=db, comment_id=comment_id, user_id=current_user["id"], emoji=payload.emoji
        )

        if not reaction:
            # Reaction already exists
            return {"already_reacted": True}

        # Get comment for project_id
        from app.crud import comments_crud

        comment = comments_crud.get_comment_by_id_orm(db, comment_id)

        # Broadcast real-time event
        if comment:
            schedule_broadcast(
                background_tasks,
                comment["project_id"],
                {
                    "type": "reaction:added",
                    "comment_id": comment_id,
                    "reaction": reaction,
                    "actor_id": str(current_user["id"]),
                },
            )

        return {
            "success": True,
            "data": {"reaction": reaction},
            "message": "Reaction added successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding reaction: {str(e)}")


@router.delete("/comments/{comment_id}/reactions")
def remove_reaction(
    background_tasks: BackgroundTasks,
    comment_id: str,
    emoji: str = Query(...),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove a reaction from a comment"""
    _get_accessible_comment(db, comment_id, current_user)
    try:
        removed = comments_service.remove_reaction(
            db=db, comment_id=comment_id, user_id=current_user["id"], emoji=emoji
        )

        if not removed:
            raise HTTPException(status_code=404, detail="Reaction not found")

        # Get comment for project_id
        from app.crud import comments_crud

        comment = comments_crud.get_comment_by_id_orm(db, comment_id)

        # Broadcast real-time event
        if comment:
            schedule_broadcast(
                background_tasks,
                comment["project_id"],
                {
                    "type": "reaction:removed",
                    "comment_id": comment_id,
                    "emoji": emoji,
                    "actor_id": str(current_user["id"]),
                },
            )

        return {
            "success": True,
            "data": {"removed": True},
            "message": "Reaction removed successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing reaction: {str(e)}")


@router.get("/comments")
def get_comments(
    entity_id: str = Query(...),
    entity_type: str = Query(...),
    include_resolved: bool = Query(True),
    include_replies: bool = Query(True),
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get comments for an entity"""
    try:
        filters = {"include_resolved": include_resolved, "include_replies": include_replies}

        comments = comments_service.get_comments(
            db=db,
            entity_id=entity_id,
            entity_type=entity_type,
            filters=filters,
            viewer_id=str(current_user["id"]),
        )

        return {"success": True, "data": {"comments": comments}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching comments: {str(e)}")


@router.post("/comments/mark-read")
def mark_comments_read(
    payload: MarkReadRequest, db=Depends(get_db), current_user=Depends(get_current_user)
):
    """Mark comments as read"""
    try:
        count = comments_service.mark_as_read(
            db=db, comment_ids=payload.comment_ids, user_id=current_user["id"]
        )

        return {
            "success": True,
            "data": {"marked": count},
            "message": f"{count} comment(s) marked as read",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error marking comments as read: {str(e)}")


@router.get("/comments/unread/{project_id}")
def get_unread_count(project_id: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    """Get unread comment count for a project"""
    require_project_access(db, project_id, current_user["id"])
    try:
        count = comments_service.get_unread_count(
            db=db, project_id=project_id, user_id=current_user["id"]
        )

        return {
            "success": True,
            "data": {"unread_count": count},
            "message": "Unread count retrieved successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting unread count: {str(e)}")
