# app/routers/realtime.py
import hashlib
from typing import Dict, Set

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from psycopg2.extras import RealDictCursor
from starlette.websockets import WebSocketState

from app.crud import session_crud

# CRUDs ORM
from app.crud.project_crud import ProjectCRUD
from app.database.session import get_db_session
from app.routers.dependencies import get_current_user
from app.utils.cookies import verify_signed_cookie
from app.utils.error_codes import ErrorCode, make_error

router = APIRouter()


class ProjectWSManager:
    def __init__(self):
        # project_id -> set[WebSocket]
        self.active: Dict[str, Set[WebSocket]] = {}

    async def connect(self, project_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(project_id, set()).add(ws)

    def disconnect(self, project_id: str, ws: WebSocket):
        try:
            self.active.get(project_id, set()).discard(ws)
            if not self.active.get(project_id):
                self.active.pop(project_id, None)
        except Exception:
            pass

    async def broadcast_json(
        self, project_id: str, message: dict, exclude: WebSocket | None = None
    ):
        # Envía a todos los sockets del proyecto (opcionalmente excluyendo uno)
        conns = list(self.active.get(project_id, set()))
        for ws in conns:
            if exclude is not None and ws is exclude:
                continue
            if ws.application_state == WebSocketState.CONNECTED:
                try:
                    await ws.send_json(message)
                except Exception:
                    # Si falla, lo retiramos silenciosamente
                    self.disconnect(project_id, ws)


manager = ProjectWSManager()


async def _user_can_access(project_id: str, db, current_user) -> dict:
    """Verifica que el usuario tenga acceso al proyecto usando CRUD ORM"""
    # Obtener proyecto usando CRUD ORM
    p = ProjectCRUD.get_project_by_id_orm(db, project_id)
    if not p:
        raise HTTPException(404, detail=make_error(ErrorCode.PROJECT_NOT_FOUND))

    is_owner = str(p["owner_id"]) == str(current_user["id"])
    member_role = None

    # Si no es owner, verificar acceso usando CRUD ORM
    if not is_owner:
        has_access = ProjectCRUD.check_user_access_orm(db, project_id, str(current_user["id"]))
        if not has_access:
            raise HTTPException(403, detail=make_error(ErrorCode.PROJECT_NO_ACCESS))

        # Obtener members para encontrar el rol
        members = ProjectCRUD.get_project_members_orm(db, project_id)
        for member in members:
            if str(member.get("user_id")) == str(current_user["id"]):
                member_role = member.get("role")
                break

    return {"project": p, "is_owner": is_owner, "member_role": member_role}


async def get_current_user_from_websocket(websocket: WebSocket, db) -> dict:
    """
    Extrae y valida el usuario actual desde las cookies del WebSocket usando CRUD ORM
    """
    # Obtener cookie de sesión desde el WebSocket
    session_cookie = websocket.cookies.get("session")

    if not session_cookie:
        raise HTTPException(401, detail=make_error(ErrorCode.NOT_AUTHENTICATED))

    # Verificar cookie firmada
    session_token = verify_signed_cookie(session_cookie)
    if not session_token:
        raise HTTPException(401, detail=make_error(ErrorCode.SESSION_INVALID))

    # Hash del token
    hashed_token = hashlib.sha256(session_token.encode()).hexdigest()

    # Obtener sesión usando CRUD ORM
    session_data = session_crud.get_session_by_token_orm(db, hashed_token)

    if not session_data or session_data.get("is_revoked"):
        raise HTTPException(401, detail=make_error(ErrorCode.SESSION_INVALID))

    # Actualizar última actividad usando CRUD ORM
    session_crud.update_session_activity_orm(db, hashed_token)

    # Retornar datos de usuario de la sesión
    # El CRUD get_session_by_token_orm ya incluye los datos del usuario
    return {
        "id": session_data.get("user_id"),
        "username": session_data.get("username"),
        "email": session_data.get("email"),
        "is_verified": session_data.get("is_verified"),
        "created_at": session_data.get("created_at"),
        "last_activity": session_data.get("last_activity"),
        "expires_at": session_data.get("expires_at"),
    }


@router.websocket("/ws/projects/{project_id}")
async def project_ws(websocket: WebSocket, project_id: str, db=Depends(get_db_session)):
    try:
        # Autenticación manual desde cookies del WebSocket
        current_user = await get_current_user_from_websocket(websocket, db)

        # Autenticación/autorización
        _ = await _user_can_access(project_id, db, current_user)
    except HTTPException as e:
        # Rechazar conexión si no está autenticado
        await websocket.close(code=1008, reason=str(e.detail))
        return

    await manager.connect(project_id, websocket)
    # Enviar un hello con info mínima por si el cliente la usa
    await websocket.send_json(
        {"type": "hello", "project_id": project_id, "actor_id": str(current_user["id"])}
    )
    try:
        while True:
            # Recibir mensajes del cliente (JSON)
            data = await websocket.receive_json()

            # Manejar eventos de cursor colaborativo
            if data.get("type") in ["cursor_move", "cursor_leave"]:
                # Agregar información del usuario que envía el evento
                data["actor_id"] = str(current_user["id"])
                data["actor_name"] = current_user.get("username", "Usuario")

                # Broadcast a todos los usuarios del proyecto excepto al emisor
                await manager.broadcast_json(project_id, data, exclude=websocket)

            # Otros tipos de mensajes pueden ser ignorados o manejados aquí
    except WebSocketDisconnect:
        manager.disconnect(project_id, websocket)


# Helper público para emitir desde otros endpoints
async def realtime_broadcast(project_id: str, payload: dict):
    # payload debe incluir al menos: type, actor_id, ts y los datos de dominio
    await manager.broadcast_json(project_id, payload)
