# routers/versions.py
"""
API endpoints for version control operations
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import UUID4, BaseModel

from app.crud import versions_crud
from app.database.session import get_db_session
from app.routers.dependencies import get_current_user, require_project_access
from app.routers.realtime import realtime_broadcast
from app.services import version_control_service
from app.utils.error_codes import ErrorCode, make_error
from app.utils.redis_session_cache import get_encryption_session_cache

router = APIRouter(prefix="/api", tags=["versions"])


# Pydantic models
class CreateVersionRequest(BaseModel):
    entity_id: str
    entity_type: str  # 'mapping', 'table', 'column', etc.
    project_id: str
    change_type: str  # 'create', 'update', 'delete'
    snapshot: Dict[str, Any]
    message: Optional[str] = None


class RestoreVersionRequest(BaseModel):
    create_backup: bool = True


class CreateTagRequest(BaseModel):
    version_id: str
    project_id: str
    name: str
    description: Optional[str] = None
    color: Optional[str] = None


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def _get_accessible_version(db, version_id: str, current_user: dict, min_role: str = "viewer"):
    """
    Devuelve la versión si el usuario tiene acceso a su proyecto (con al menos min_role).

    Una versión inexistente y una de un proyecto ajeno responden igual (404).
    """
    version = versions_crud.get_version_by_id_orm(db, version_id) if _is_uuid(version_id) else None
    if not version:
        raise HTTPException(status_code=404, detail=make_error(ErrorCode.VERSION_NOT_FOUND))
    try:
        require_project_access(db, version["project_id"], current_user["id"], min_role=min_role)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail=make_error(ErrorCode.VERSION_NOT_FOUND))
        raise
    return version


# Endpoints
@router.post("/versions")
async def create_version(
    payload: CreateVersionRequest,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Create a new version (owner o editor del proyecto)"""
    require_project_access(db, payload.project_id, current_user["id"], min_role="editor")
    try:
        version = version_control_service.create_version(
            db=db,
            project_id=payload.project_id,
            entity_id=payload.entity_id,
            entity_type=payload.entity_type,
            user_id=current_user["id"],
            change_type=payload.change_type,
            snapshot=payload.snapshot,
            message=payload.message,
        )

        # Broadcast real-time event
        await realtime_broadcast(
            payload.project_id,
            {"type": "version:created", "version": version, "actor_id": str(current_user["id"])},
        )

        return {"success": True, "data": {"version": version}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating version: {str(e)}")


@router.get("/versions/entity/{entity_id}")
def get_version_history(
    entity_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    change_type: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Get version history for an entity"""
    try:
        filters = {"limit": limit, "offset": offset, "change_type": change_type, "user_id": user_id}

        versions = version_control_service.get_version_history(
            db=db, entity_id=entity_id, filters=filters, viewer_id=str(current_user["id"])
        )

        return {"success": True, "data": {"versions": versions, "total": len(versions)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching versions: {str(e)}")


@router.get("/versions/recent")
def get_recent_versions(
    limit: int = Query(5, ge=1, le=50),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Get most recent versions across all projects accessible by the current user"""
    try:
        versions = versions_crud.get_recent_versions_for_user(
            db=db, user_id=str(current_user["id"]), limit=limit
        )
        return {"success": True, "data": versions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=make_error(ErrorCode.VERSION_OPERATION_FAILED))


@router.get("/versions/compare")
def compare_versions(
    version_a_id: str = Query(..., description="First version ID"),
    version_b_id: str = Query(..., description="Second version ID"),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Compare two versions"""
    _get_accessible_version(db, version_a_id, current_user)
    _get_accessible_version(db, version_b_id, current_user)
    try:
        comparison = version_control_service.compare_versions(
            db=db, version_a_id=version_a_id, version_b_id=version_b_id
        )

        return {
            "success": True,
            "data": {
                "diff": comparison.get("diff"),
                "version_a": comparison.get("version_a"),
                "version_b": comparison.get("version_b"),
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error comparing versions: {str(e)}")


@router.get("/versions/{version_id}")
def get_version(
    version_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """Get a specific version by ID"""
    from app.crud import versions_crud

    version = _get_accessible_version(db, version_id, current_user)

    return {"success": True, "data": {"version": version}}


@router.post("/versions/{version_id}/restore")
async def restore_version(
    version_id: str,
    payload: RestoreVersionRequest,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Restore a previous version (owner o editor del proyecto de la versión)"""
    _get_accessible_version(db, version_id, current_user, min_role="editor")
    try:
        # The restore URL (/api/versions/{id}/restore) has no /projects/{uuid} segment,
        # so the EncryptionSessionMiddleware cannot extract the project_id and never sets
        # request.state.encryption_key. We resolve the project_id from the version record
        # and look up the encryption session manually.
        encryption_key = None
        version_record = versions_crud.get_version_by_id_orm(db, version_id)
        if version_record:
            project_id = version_record["project_id"]
            session_token = request.cookies.get(f"enc_session_{project_id}")
            if session_token:
                cache = get_encryption_session_cache()
                session = cache.get_session(session_token, project_id)
                if session and str(session.get("user_id")) == str(current_user["id"]):
                    encryption_key = session["encryption_key"]

        restored_version = version_control_service.restore_version(
            db=db,
            version_id=version_id,
            user_id=current_user["id"],
            create_backup=payload.create_backup,
            encryption_key=encryption_key,
        )

        # Broadcast real-time event
        await realtime_broadcast(
            restored_version["project_id"],
            {
                "type": "version:restored",
                "version": restored_version,
                "restored_from": version_id,
                "actor_id": str(current_user["id"]),
            },
        )

        return {"success": True, "data": {"version": restored_version}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error restoring version: {str(e)}")


@router.post("/versions/tags")
def create_tag(
    payload: CreateTagRequest, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """Create a tag for a version (owner o editor del proyecto)"""
    require_project_access(db, payload.project_id, current_user["id"], min_role="editor")
    try:
        tag = version_control_service.create_tag(
            db=db,
            version_id=payload.version_id,
            project_id=payload.project_id,
            name=payload.name,
            created_by=current_user["id"],
            description=payload.description,
            color=payload.color,
        )

        return {"success": True, "data": {"tag": tag}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating tag: {str(e)}")


@router.get("/versions/projects/{project_id}")
def get_project_versions(
    project_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    entity_type: Optional[str] = Query(None),
    change_type: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Get all versions for a project"""
    require_project_access(db, project_id, current_user["id"])
    try:
        filters = {
            "limit": limit,
            "offset": offset,
            "entity_type": entity_type,
            "change_type": change_type,
            "user_id": user_id,
        }

        versions = version_control_service.get_project_versions(
            db=db, project_id=project_id, filters=filters
        )

        return {"success": True, "data": {"versions": versions, "total": len(versions)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching project versions: {str(e)}")


@router.get("/versions/projects/{project_id}/tags")
def get_project_tags(
    project_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """Get all tags for a project"""
    require_project_access(db, project_id, current_user["id"])
    try:
        tags = version_control_service.get_project_tags(db, project_id)
        return {"success": True, "data": {"tags": tags}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=make_error(ErrorCode.VERSION_OPERATION_FAILED))


@router.delete("/versions/tags/{tag_id}")
def delete_tag(tag_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)):
    """Delete a tag (solo su creador o el owner del proyecto)"""
    from app.crud import tags_crud

    tag = tags_crud.get_tag_by_id_orm(db, tag_id) if _is_uuid(tag_id) else None
    if not tag:
        raise HTTPException(status_code=404, detail=make_error(ErrorCode.TAG_NOT_FOUND))
    access = require_project_access(db, tag["project_id"], current_user["id"])
    if not access["is_owner"] and str(tag.get("created_by")) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail=make_error(ErrorCode.PROJECT_FORBIDDEN))

    try:
        deleted = version_control_service.delete_tag(
            db=db, tag_id=tag_id, user_id=current_user["id"]
        )

        if not deleted:
            raise HTTPException(status_code=404, detail=make_error(ErrorCode.TAG_NOT_FOUND))

        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=make_error(ErrorCode.VERSION_OPERATION_FAILED))
