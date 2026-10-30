# app/routers/project_router.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.database.session import get_db_session
from app.routers.dependencies import get_current_user
from app.services.project_service import ProjectService
from app.utils.error_codes import ErrorCode, make_error

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ==================== Schemas de Request ====================


class CreateProjectRequest(BaseModel):
    """Schema para crear un proyecto"""

    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(default="", max_length=500)
    origin_db: str = Field(..., min_length=1)
    destination_db: str = Field(..., min_length=1)
    status: Optional[str] = Field(default="active", pattern="^(active|paused|completed)$")
    progress: Optional[int] = Field(default=0, ge=0, le=100)
    budget: Optional[float] = Field(default=0.0, ge=0)


class UpdateProjectRequest(BaseModel):
    """Schema para actualizar un proyecto"""

    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    origin_db: Optional[str] = Field(None, min_length=1)
    destination_db: Optional[str] = Field(None, min_length=1)
    status: Optional[str] = Field(None, pattern="^(active|paused|completed)$")
    progress: Optional[int] = Field(None, ge=0, le=100)
    budget: Optional[float] = Field(None, ge=0)


# ==================== Endpoints ====================
# IMPORTANTE: Las rutas específicas deben ir ANTES de las rutas con parámetros

# app/routers/project_router.py
# Reemplazar el endpoint /stats con esta versión debug:

# app/routers/project_router.py
# Reemplazar el endpoint /stats con esta versión limpia:


@router.get("/stats")
async def get_project_stats(
    comparison_days: int = Query(default=30, ge=1, le=365),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Obtiene estadísticas de proyectos con comparación histórica

    Query params:
        - comparison_days: Días hacia atrás para comparar (1-365, por defecto 30)
    """
    from datetime import datetime, timedelta

    from sqlalchemy import text

    user_id = current_user["id"]

    try:
        # Estadísticas actuales
        current = (
            db.execute(
                text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'active') as active,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COALESCE(SUM(budget), 0) as budget
            FROM projects
            WHERE owner_id = :user_id
            AND is_deleted = FALSE
        """),
                {"user_id": user_id},
            )
            .mappings()
            .fetchone()
        )

        # Estadísticas de hace X días (para calcular el cambio)
        comparison_date = datetime.now() - timedelta(days=comparison_days)

        previous = (
            db.execute(
                text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'active') as active,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COALESCE(SUM(budget), 0) as budget
            FROM projects
            WHERE owner_id = :user_id
            AND is_deleted = FALSE
            AND created_at < :comparison_date
        """),
                {"user_id": user_id, "comparison_date": comparison_date},
            )
            .mappings()
            .fetchone()
        )

        # Función para calcular cambio porcentual
        def calc_change(curr, prev):
            if prev == 0:
                return 100.0 if curr > 0 else 0.0
            return round(((curr - prev) / prev) * 100, 1)

        # Construir respuesta
        stats = {
            "total_projects": {
                "value": current["total"],
                "change": calc_change(current["total"], previous["total"]),
                "positive": current["total"] >= previous["total"],
            },
            "active_projects": {
                "value": current["active"],
                "change": calc_change(current["active"], previous["active"]),
                "positive": current["active"] >= previous["active"],
            },
            "completed_projects": {
                "value": current["completed"],
                "change": calc_change(current["completed"], previous["completed"]),
                "positive": current["completed"] >= previous["completed"],
            },
            "total_budget": {
                "value": float(current["budget"]),
                "change": calc_change(float(current["budget"]), float(previous["budget"])),
                "positive": current["budget"] >= previous["budget"],
            },
        }

        return {"success": True, "data": stats}

    except Exception as e:
        raise HTTPException(status_code=500, detail=make_error(ErrorCode.PROJECT_STATS_ERROR))


@router.get("/metrics/history")
async def get_metrics_history(
    days: int = Query(default=30, ge=7, le=365),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Obtiene el historial de métricas para gráficos

    Query params:
        - days: Número de días de historial (7-365, por defecto 30)
    """
    metrics = ProjectService.get_metrics_history(db=db, user_id=current_user["id"], days=days)

    return {"success": True, "data": {"metrics": metrics, "period_days": days}}


@router.get("/recent")
async def get_recent_projects(
    limit: int = Query(default=5, ge=1, le=20),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Obtiene los proyectos más recientemente accedidos por el usuario

    Query params:
        - limit: Número máximo de proyectos (1-20, por defecto 5)
    """
    projects = ProjectService.get_recent_projects(db=db, user_id=current_user["id"], limit=limit)

    return {"success": True, "data": {"projects": projects, "total": len(projects)}}


@router.get("")
async def list_projects(
    status: Optional[str] = Query(None, pattern="^(active|paused|completed)$"),
    sort_by: str = Query("name", pattern="^(name|status|progress|budget|updated_at)$"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Obtiene la lista de proyectos del usuario actual
    Incluye proyectos propios y aquellos donde es miembro

    Query params:
        - status: Filtrar por estado (active, paused, completed)
        - sort_by: Campo por el cual ordenar
        - sort_order: Orden de ordenamiento (asc, desc)
    """
    projects = ProjectService.get_user_projects(
        db=db,
        user_id=current_user["id"],
        status_filter=status,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return {"success": True, "data": {"projects": projects, "total": len(projects)}}


@router.get("/{project_id}")
async def get_project(
    project_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """
    Obtiene un proyecto por su ID
    Solo accesible para el owner o miembros del proyecto
    """
    project = ProjectService.get_project_by_id(
        db=db, project_id=project_id, user_id=current_user["id"]
    )

    # Actualizar timestamp de último acceso (no bloquea la respuesta si falla)
    try:
        ProjectService.update_project_last_accessed(
            db=db, project_id=project_id, user_id=current_user["id"]
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to update last_accessed_at for project %s", project_id
        )

    return {"success": True, "data": {"project": project}}


@router.post("")
async def create_project(
    data: CreateProjectRequest, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """
    Crea un nuevo proyecto
    El usuario actual será el propietario
    """
    project = ProjectService.create_project(
        db=db,
        user_id=current_user["id"],
        name=data.name,
        description=data.description or "",
        origin_db=data.origin_db,
        destination_db=data.destination_db,
        status=data.status or "active",
        progress=data.progress or 0,
        budget=data.budget or 0.0,
    )

    return {
        "success": True,
        "message": "Proyecto creado exitosamente",
        "data": {"project": project},
    }


@router.put("/{project_id}")
async def update_project(
    project_id: str,
    data: UpdateProjectRequest,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Actualiza un proyecto existente
    Solo accesible para el owner o editores del proyecto
    """
    # Convertir el modelo a dict y filtrar valores None
    update_data = {k: v for k, v in data.dict().items() if v is not None}

    project = ProjectService.update_project(
        db=db, project_id=project_id, user_id=current_user["id"], **update_data
    )

    return {
        "success": True,
        "message": "Proyecto actualizado exitosamente",
        "data": {"project": project},
    }


@router.delete("/{project_id}")
async def delete_project(
    project_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """
    Elimina un proyecto (soft delete)
    Solo accesible para el propietario
    No se puede eliminar si tiene miembros
    """
    ProjectService.delete_project(db=db, project_id=project_id, user_id=current_user["id"])

    return {"success": True, "message": "Proyecto eliminado exitosamente"}


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """
    Obtiene los miembros de un proyecto
    Solo accesible para el propietario
    """
    members = ProjectService.get_project_members(
        db=db, project_id=project_id, user_id=current_user["id"]
    )

    return {"success": True, "data": {"members": members}}


@router.delete("/{project_id}/members/{user_id}")
async def remove_project_member(
    project_id: str,
    user_id: str,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Elimina un miembro de un proyecto
    Solo accesible para el propietario
    """
    ProjectService.remove_member(
        db=db, project_id=project_id, member_user_id=user_id, user_id=current_user["id"]
    )

    return {"success": True, "message": "Miembro eliminado exitosamente"}


@router.post("/{project_id}/leave")
async def leave_project(
    project_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """
    Permite a un miembro salir de un proyecto
    No disponible para propietarios
    """
    ProjectService.leave_project(db=db, project_id=project_id, user_id=current_user["id"])

    return {"success": True, "message": "Has salido del proyecto exitosamente"}


# Añadir estos endpoints al archivo app/routers/project_router.py


@router.post("/{project_id}/members")
async def add_project_member(
    project_id: str,
    data: dict,  # {identifier: str, role: str}
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Añade un miembro al proyecto
    Solo accesible para el propietario
    """
    identifier = data.get("identifier", "").strip()
    role = data.get("role", "viewer")

    if not identifier:
        raise HTTPException(status_code=400, detail=make_error(ErrorCode.PROJECT_EMAIL_REQUIRED))

    if role not in ["viewer", "editor"]:
        raise HTTPException(status_code=400, detail=make_error(ErrorCode.PROJECT_INVALID_ROLE))

    ProjectService.add_member(
        db=db,
        project_id=project_id,
        owner_user_id=current_user["id"],
        identifier=identifier,
        role=role,
    )

    return {"success": True, "message": "Miembro añadido exitosamente"}


@router.put("/{project_id}/members/{user_id}")
async def update_member_role(
    project_id: str,
    user_id: str,
    data: dict,  # {role: str}
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Actualiza el rol de un miembro
    Solo accesible para el propietario
    """
    role = data.get("role")

    if not role or role not in ["viewer", "editor"]:
        raise HTTPException(status_code=400, detail=make_error(ErrorCode.PROJECT_INVALID_ROLE))

    ProjectService.update_member_role(
        db=db,
        project_id=project_id,
        member_user_id=user_id,
        new_role=role,
        owner_user_id=current_user["id"],
    )

    return {"success": True, "message": "Rol actualizado exitosamente"}
