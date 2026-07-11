import json
import uuid
from datetime import datetime
from typing import Annotated, List, Literal, Optional

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from psycopg2.extras import Json, RealDictCursor
from pydantic import (
    UUID4,
    AnyUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    StringConstraints,
    model_validator,
)

from app.crud import notification_crud, user_crud
from app.utils.error_codes import ErrorCode, make_error

# CRUDs ORM
from app.crud.project_crud import ProjectCRUD
from app.database.session import get_db_session
from app.routers.dependencies import get_current_user

router = APIRouter()


# MANDAR NOTIFICACION DE INVITACION A USUARIO
class InviteRequest(BaseModel):
    email: EmailStr
    role: str  # 'viewer' o 'editor'
    project_id: uuid.UUID


@router.post("/notifications/invite")
def send_project_invite(
    project_id: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),  # 'viewer' | 'editor'
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    # Validación de rol
    if role not in ("viewer", "editor"):
        r = RedirectResponse(url="/projects", status_code=303)
        r.set_cookie("flash", "Rol inválido", max_age=3)
        return r

    # Evitar invitarte a ti mismo
    if email.strip().lower() == current_user["email"].strip().lower():
        r = RedirectResponse(url="/projects", status_code=303)
        r.set_cookie("flash", "No puedes invitarte a ti mismo", max_age=3)
        return r

    # 1) Verificar que el proyecto existe y que el current_user es el owner usando CRUD ORM
    proj = ProjectCRUD.get_project_by_id_orm(db, project_id)
    if not proj:
        r = RedirectResponse(url="/projects", status_code=303)
        r.set_cookie("flash", "Proyecto no encontrado", max_age=3)
        return r

    if str(proj["owner_id"]) != str(current_user["id"]):
        r = RedirectResponse(url="/projects", status_code=303)
        r.set_cookie("flash", "Solo el propietario puede enviar invitaciones", max_age=3)
        return r

    # 2) Buscar destinatario por email usando CRUD ORM
    user = user_crud.get_user_by_email_orm(db, email)
    if not user:
        r = RedirectResponse(url="/projects", status_code=303)
        r.set_cookie("flash", "Usuario no encontrado", max_age=3)
        return r

    # 3) Comprobar si ya existe una invitación pendiente usando CRUD ORM
    exists = notification_crud.check_existing_invite_orm(db, project_id, str(user["id"]))
    if exists:
        r = RedirectResponse(url="/projects", status_code=303)
        r.set_cookie("flash", "Ya has enviado una invitación a este usuario", max_age=3)
        return r

    # 4) Insertar notificación usando CRUD ORM
    title = f"Invitación a proyecto: {proj['name']}"
    body = f"{current_user['email']} te invita como {role}."

    metadata = {
        "project_id": project_id,
        "role": role,
        "invited_by": str(current_user["id"]),
        "actions": [
            {"action": "accept_invite", "label": "Aceptar"},
            {"action": "reject_invite", "label": "Rechazar"},
        ],
    }

    notification_crud.create_notification_orm(
        db=db,
        recipient_id=str(user["id"]),
        notification_kind="invite",
        title=title,
        body=body,
        data=metadata,
    )

    r = RedirectResponse(url="/projects", status_code=303)
    r.set_cookie("flash_success", "Invitación enviada correctamente", max_age=3)
    return r


@router.post("/notifications/{notif_id}/accept")
def accept_invite(
    notif_id: str,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    # 1) Cargar notificación usando CRUD ORM
    notif = notification_crud.get_notification_by_id_orm(db, notif_id, str(current_user["id"]))

    if not notif:
        return JSONResponse({"ok": False, "error": "Notificación no encontrada"}, status_code=404)

    if str(notif["recipient_id"]) != str(current_user["id"]):
        return JSONResponse(
            {"ok": False, "error": "No puedes operar esta notificación"}, status_code=403
        )

    if notif["notification_kind"] != "invite":
        return JSONResponse(
            {"ok": False, "error": "Tipo de notificación inválido"}, status_code=400
        )

    if notif.get("expires_at") and notif["expires_at"] <= datetime.utcnow():
        # Si está expirada, la borramos usando CRUD ORM
        notification_crud.delete_notification_orm(db, notif_id, str(current_user["id"]))
        return JSONResponse({"ok": False, "error": "La invitación ha expirado"}, status_code=410)

    metadata = notif.get("metadata") or {}
    project_id = metadata.get("project_id")
    role = metadata.get("role")
    invited_by = metadata.get("invited_by")

    if role not in ("viewer", "editor"):
        return JSONResponse({"ok": False, "error": "Rol inválido"}, status_code=400)

    # 2) Verificar que el proyecto existe y que invited_by es el owner usando CRUD ORM
    proj = ProjectCRUD.get_project_by_id_orm(db, str(project_id) if project_id else "")
    if not proj:
        return JSONResponse({"ok": False, "error": "Proyecto no encontrado"}, status_code=404)

    if str(proj["owner_id"]) != str(invited_by):
        return JSONResponse(
            {"ok": False, "error": "Invitación inválida (owner no coincide)"}, status_code=400
        )

    # 3) Añadir/actualizar membership usando CRUD ORM
    ProjectCRUD.add_project_member_orm(
        db=db,
        project_id=str(project_id) if project_id else "",
        user_id=str(current_user["id"]),
        role=role,
        added_by=invited_by,
    )

    # 4) Borrar notificación (ya procesada) usando CRUD ORM
    notification_crud.delete_notification_orm(db, notif_id, str(current_user["id"]))

    r = RedirectResponse(url="/projects", status_code=303)  # POST -> GET
    r.set_cookie("flash_success", "¡Te has unido al proyecto!", max_age=3)
    return r


@router.post("/notifications/{notif_id}/reject")
def reject_invite(
    notif_id: str,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    # Obtener notificación usando CRUD ORM
    notif = notification_crud.get_notification_by_id_orm(db, notif_id, str(current_user["id"]))

    if not notif:
        return JSONResponse({"ok": False, "error": "Notificación no encontrada"}, status_code=404)

    if str(notif["recipient_id"]) != str(current_user["id"]):
        return JSONResponse(
            {"ok": False, "error": "No puedes operar esta notificación"}, status_code=403
        )

    if notif["notification_kind"] != "invite":
        return JSONResponse(
            {"ok": False, "error": "Tipo de notificación inválido"}, status_code=400
        )

    # Eliminar notificación usando CRUD ORM
    notification_crud.delete_notification_orm(db, notif_id, str(current_user["id"]))
    return JSONResponse({"ok": True})


# =========================
# Pydantic v2: tipos string
# =========================
TitleStr = Annotated[str, StringConstraints(min_length=1, max_length=160, strip_whitespace=True)]
BodyStr = Annotated[str, StringConstraints(min_length=1, max_length=4000, strip_whitespace=True)]
LabelStr = Annotated[str, StringConstraints(min_length=1, max_length=60, strip_whitespace=True)]
ActionStr = Annotated[str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)]


class Action(BaseModel):
    label: LabelStr
    action: ActionStr
    payload: Optional[dict] = None


class CreateNotificationIn(BaseModel):
    """Payload para crear notificaciones"""

    model_config = ConfigDict(extra="forbid")  # rechaza campos desconocidos

    recipient_id: UUID4
    notification_kind: Literal["system", "invitation"]
    title: TitleStr
    body: BodyStr
    project_id: Optional[UUID4] = None
    invitation_id: Optional[UUID4] = None
    link_url: Optional[AnyUrl] = None
    data: Optional[dict] = None
    actions: Optional[List[Action]] = None
    expires_at: Optional[datetime] = None  # TIMESTAMPTZ en BD

    @model_validator(mode="after")
    def check_invitation_pair(self):
        if self.notification_kind == "invitation" and self.invitation_id is None:
            raise ValueError("invitation_id es obligatorio cuando notification_kind='invitation'")
        if self.notification_kind != "invitation" and self.invitation_id is not None:
            raise ValueError("invitation_id debe ser NULL cuando notification_kind!='invitation'")
        return self


# =========================
# Helpers
# =========================
def deny_or_redirect(request: Request, message: str = "No tienes acceso a ese recurso"):
    """
    Si la petición espera HTML (navegación), redirige a /projects con cookie flash.
    Si es JSON/XHR (Accept application/json), devuelve 403.
    """
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        raise HTTPException(status_code=403, detail=message)
    resp = RedirectResponse(url="/projects", status_code=303)
    resp.set_cookie("flash", message, max_age=3)
    return resp


def fetch_notification_for_user(db, notif_id: str, user_id: str):
    """Obtiene una notificación específica para un usuario usando CRUD ORM"""
    notif = notification_crud.get_notification_by_id_orm(db, notif_id, user_id)
    return notif


# =========================
# Endpoints
# =========================


@router.get("/notifications")
def list_notifications(
    request: Request,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Devuelve las notificaciones del usuario autenticado usando CRUD ORM:
    - primero no leídas, luego leídas
    - dentro de cada grupo, las más recientes primero
    """
    notifications = notification_crud.get_user_notifications_orm(
        db=db, user_id=str(current_user["id"]), unread_only=False, limit=limit, offset=offset
    )
    return notifications


@router.get("/notifications/unread_count")
def unread_count(
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Obtiene el conteo de notificaciones no leídas usando CRUD ORM"""
    count = notification_crud.get_unread_count_orm(db, str(current_user["id"]))
    return {"unread": count}


@router.patch("/notifications/{notification_id}/read")
def mark_read(
    notification_id: str,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Marca una notificación como leída usando CRUD ORM"""
    # Verificar pertenencia
    notif = fetch_notification_for_user(db, notification_id, str(current_user["id"]))
    if not notif:
        return deny_or_redirect(request, "No tienes permiso para esa notificación")

    # Marcar como leída
    success = notification_crud.mark_as_read_orm(db, notification_id, str(current_user["id"]))
    if not success:
        raise HTTPException(status_code=404, detail=make_error(ErrorCode.NOTIFICATION_NOT_FOUND))

    # Obtener la notificación actualizada para devolver read_at
    updated_notif = notification_crud.get_notification_by_id_orm(
        db, notification_id, str(current_user["id"])
    )
    if updated_notif is None:
        return {"id": notification_id, "read_at": None}
    return {
        "id": updated_notif["id"],
        "read_at": updated_notif["read_at"].isoformat() if updated_notif.get("read_at") else None,
    }


@router.post("/notifications/mark_all_read")
def mark_all_read(
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Marca todas las notificaciones como leídas usando CRUD ORM"""
    updated = notification_crud.mark_all_as_read_orm(db, str(current_user["id"]))
    return {"updated": updated}


@router.delete("/notifications/{notification_id}")
def delete_notification(
    notification_id: str,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Elimina una notificación usando CRUD ORM"""
    # Verificar pertenencia
    notif = fetch_notification_for_user(db, notification_id, str(current_user["id"]))
    if not notif:
        return deny_or_redirect(request, "No tienes permiso para esa notificación")

    # Eliminar notificación
    success = notification_crud.delete_notification_orm(
        db, notification_id, str(current_user["id"])
    )
    if not success:
        raise HTTPException(status_code=404, detail=make_error(ErrorCode.NOTIFICATION_NOT_FOUND))

    return {"deleted": True}


@router.post("/notifications")
def create_notification(
    request: Request,
    payload: CreateNotificationIn = Body(...),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Crea una notificación usando CRUD ORM. Por ahora solo permitimos que el usuario
    autenticado se cree notificaciones a sí mismo.
    """
    if str(payload.recipient_id) != str(current_user["id"]):
        return deny_or_redirect(request, "No puedes crear notificaciones para otro usuario")

    # Preparar metadata con todos los campos adicionales
    metadata = payload.data or {}
    metadata.update(
        {
            "project_id": str(payload.project_id) if payload.project_id else None,
            "invitation_id": str(payload.invitation_id) if payload.invitation_id else None,
            "link_url": str(payload.link_url) if payload.link_url else None,
            "actions": (
                [a.model_dump() for a in (payload.actions or [])] if payload.actions else None
            ),
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
        }
    )

    # Crear notificación usando CRUD ORM
    notification = notification_crud.create_notification_orm(
        db=db,
        recipient_id=str(payload.recipient_id),
        notification_kind=payload.notification_kind,
        title=payload.title,
        body=payload.body,
        data=metadata,
    )

    return notification
