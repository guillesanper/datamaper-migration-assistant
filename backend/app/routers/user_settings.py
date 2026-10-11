"""
Router para la sección de ajustes de usuario.

Endpoints:
- /api/settings/profile       — perfil de usuario
- /api/settings/avatar        — subir / eliminar avatar
- /api/settings/password      — cambio de contraseña
- /api/settings/notifications — preferencias de notificaciones
- /api/settings/preferences   — preferencias generales
- /api/settings/sessions      — sesiones activas
- /api/settings/access-history— historial de accesos (SecurityLog)
- /api/settings/2fa/*         — autenticación de dos factores (TOTP)
- /api/settings/api-keys      — API keys del usuario
"""

import base64
import hashlib
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional

import pyotp
import qrcode
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from PIL import Image
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.crud import session_crud
from app.crud.api_key_crud import create_api_key_orm, get_user_api_keys_orm, revoke_api_key_orm
from app.crud.user_crud import (
    get_user_by_id_orm,
    update_user_orm,
    update_user_password_orm,
    verify_user_password_orm,
)
from app.crud.user_preferences_crud import get_or_create_preferences_orm, update_preferences_orm
from app.database.session import get_db_session
from app.models.orm.security import SecurityLog
from app.routers.dependencies import get_current_user_orm
from app.utils.cookies import get_session_token_hash, verify_signed_cookie
from app.utils.error_codes import ErrorCode, make_error
from app.utils.security import SecurityUtils

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Resampling filter compatible with Pillow 9 and 10+
try:
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    _LANCZOS = Image.LANCZOS  # type: ignore[attr-defined]


# ─── Pydantic request models ──────────────────────────────────────────────────


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class NotificationPrefsRequest(BaseModel):
    email_notifications: Dict[str, Any]
    in_app_notifications: Dict[str, Any]


class UserPreferencesRequest(BaseModel):
    language: Optional[str] = None
    timezone: Optional[str] = None
    default_db_type: Optional[str] = None
    default_export_format: Optional[str] = None


class TwoFAVerifyRequest(BaseModel):
    code: str


class DisableTwoFARequest(BaseModel):
    code: str
    password: str


class CreateApiKeyRequest(BaseModel):
    name: str
    expires_in_days: Optional[int] = None


# ─── PERFIL ───────────────────────────────────────────────────────────────────


@router.get("/profile")
def get_profile(
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id = str(current_user["id"])
    user = get_user_by_id_orm(db, user_id)
    if not user:
        raise HTTPException(404, detail=make_error(ErrorCode.USER_NOT_FOUND))
    return {
        "username": user.get("username"),
        "email": user.get("email"),
        "avatar_url": user.get("avatar_url"),
        "created_at": user.get("created_at"),
        "is_verified": user.get("is_verified"),
        "totp_enabled": user.get("totp_enabled", False),
    }


@router.put("/profile")
def update_profile(
    body: UpdateProfileRequest,
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id = str(current_user["id"])
    update_data: Dict[str, Any] = {}
    if body.username is not None:
        update_data["username"] = body.username

    if update_data:
        ok = update_user_orm(db, user_id, update_data)
        if not ok:
            raise HTTPException(400, detail=make_error(ErrorCode.USER_UPDATE_FAILED))

    user = get_user_by_id_orm(db, user_id)
    if not user:
        raise HTTPException(404, detail=make_error(ErrorCode.USER_NOT_FOUND))
    return {
        "success": True,
        "user": {
            "username": user.get("username"),
            "email": user.get("email"),
            "avatar_url": user.get("avatar_url"),
        },
    }


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed_types:
        raise HTTPException(400, detail=make_error(ErrorCode.USER_IMAGE_FORMAT))

    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(400, detail=make_error(ErrorCode.USER_IMAGE_SIZE))

    user_id = str(current_user["id"])

    try:
        img = Image.open(BytesIO(content))
        img = img.convert("RGB")  # type: ignore[assignment]
        # Recorte centrado a cuadrado, luego resize a 200x200
        width, height = img.size
        min_dim = min(width, height)
        left = (width - min_dim) // 2
        top = (height - min_dim) // 2
        img = img.crop((left, top, left + min_dim, top + min_dim))  # type: ignore[assignment]
        img = img.resize((200, 200), _LANCZOS)  # type: ignore[assignment]
    except Exception:
        raise HTTPException(400, detail=make_error(ErrorCode.USER_IMAGE_PROCESS))

    avatar_dir = os.path.join("uploads", "avatars")
    os.makedirs(avatar_dir, exist_ok=True)

    buf = BytesIO()
    img.save(buf, format="WEBP", quality=85)
    avatar_path = os.path.join(avatar_dir, f"{user_id}.webp")
    with open(avatar_path, "wb") as f:
        f.write(buf.getvalue())

    avatar_url = f"/api/uploads/avatars/{user_id}.webp?v={int(time.time())}"
    update_user_orm(db, user_id, {"avatar_url": avatar_url})

    return {"success": True, "avatar_url": avatar_url}


@router.delete("/avatar")
def delete_avatar(
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id = str(current_user["id"])
    avatar_path = os.path.join("uploads", "avatars", f"{user_id}.webp")
    if os.path.exists(avatar_path):
        os.remove(avatar_path)
    update_user_orm(db, user_id, {"avatar_url": None})
    return {"success": True}


@router.put("/password")
def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    if body.new_password != body.confirm_password:
        raise HTTPException(400, detail=make_error(ErrorCode.USER_PASSWORD_MISMATCH))

    strength = SecurityUtils.validate_password_strength(body.new_password)
    if not strength["is_valid"]:
        raise HTTPException(422, {"errors": strength["errors"]})

    user_id = str(current_user["id"])
    ok = update_user_password_orm(
        db, user_id, body.new_password, old_password=body.current_password
    )
    if not ok:
        raise HTTPException(400, detail=make_error(ErrorCode.USER_WRONG_PASSWORD))

    # Una contraseña nueva cierra las demás sesiones (quien la conociera) y conserva la actual.
    # Con API key no hay cookie de sesión: except_token queda en None y se revocan todas.
    session_crud.revoke_all_user_sessions_orm(
        db,
        user_id,
        except_token=get_session_token_hash(request),
        reason="password_change",
    )

    return {"success": True, "message": "Contraseña actualizada"}


# ─── NOTIFICACIONES ───────────────────────────────────────────────────────────


@router.get("/notifications")
def get_notifications(
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id_uuid = uuid.UUID(str(current_user["id"]))
    prefs = get_or_create_preferences_orm(db, user_id_uuid)
    return {
        "email_notifications": prefs.get("email_notifications", {}),
        "in_app_notifications": prefs.get("in_app_notifications", {}),
    }


@router.put("/notifications")
def update_notifications(
    body: NotificationPrefsRequest,
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id_uuid = uuid.UUID(str(current_user["id"]))
    get_or_create_preferences_orm(db, user_id_uuid)  # ensure row exists
    updated = update_preferences_orm(
        db,
        user_id_uuid,
        {
            "email_notifications": body.email_notifications,
            "in_app_notifications": body.in_app_notifications,
        },
    )
    if updated is None:
        raise HTTPException(400, detail=make_error(ErrorCode.USER_UPDATE_FAILED))
    return {
        "success": True,
        "preferences": {
            "email_notifications": updated.get("email_notifications", {}),
            "in_app_notifications": updated.get("in_app_notifications", {}),
        },
    }


# ─── PREFERENCIAS ─────────────────────────────────────────────────────────────


@router.get("/preferences")
def get_preferences(
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id_uuid = uuid.UUID(str(current_user["id"]))
    prefs = get_or_create_preferences_orm(db, user_id_uuid)
    return {
        "language": prefs.get("language"),
        "timezone": prefs.get("timezone"),
        "default_db_type": prefs.get("default_db_type"),
        "default_export_format": prefs.get("default_export_format"),
    }


@router.put("/preferences")
def update_preferences(
    body: UserPreferencesRequest,
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id_uuid = uuid.UUID(str(current_user["id"]))
    get_or_create_preferences_orm(db, user_id_uuid)  # ensure row exists
    update_data: Dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = update_preferences_orm(db, user_id_uuid, update_data)
    if updated is None:
        raise HTTPException(400, detail=make_error(ErrorCode.USER_UPDATE_FAILED))
    return {
        "success": True,
        "preferences": {
            "language": updated.get("language"),
            "timezone": updated.get("timezone"),
            "default_db_type": updated.get("default_db_type"),
            "default_export_format": updated.get("default_export_format"),
        },
    }


# ─── SEGURIDAD ────────────────────────────────────────────────────────────────


@router.get("/sessions")
def get_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id = str(current_user["id"])

    # Determinar el hashed token de la sesión actual para marcar is_current
    current_hashed_token: Optional[str] = None
    session_cookie = request.cookies.get("session")
    if session_cookie:
        raw_token = verify_signed_cookie(session_cookie)
        if raw_token:
            current_hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

    sessions = session_crud.get_user_sessions_orm(db, user_id, active_only=True)

    result = []
    for s in sessions:
        session_token = s.get("session_token", "")
        result.append(
            {
                "id": s.get("id"),
                "ip_address": s.get("ip_address"),
                "user_agent": s.get("user_agent"),
                "created_at": s.get("created_at"),
                "last_activity": s.get("last_activity"),
                "expires_at": s.get("expires_at"),
                "is_current": session_token == current_hashed_token,
            }
        )
    return result


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id = str(current_user["id"])
    ok = session_crud.revoke_user_session_by_id_orm(db, user_id, session_id, reason="user_revoked")
    if not ok:
        raise HTTPException(404, detail=make_error(ErrorCode.USER_SESSION_NOT_FOUND))
    return {"success": True}


@router.get("/access-history")
def get_access_history(
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    user_id_uuid = uuid.UUID(str(current_user["id"]))
    logs = (
        db.query(SecurityLog)
        .filter(SecurityLog.user_id == user_id_uuid)
        .order_by(SecurityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "event_type": log.event_type,
            "ip_address": log.ip_address,
            "endpoint": log.endpoint,
            "severity": log.severity,
            "created_at": log.created_at,
            "details": log.details,
        }
        for log in logs
    ]


# ─── 2FA ──────────────────────────────────────────────────────────────────────


@router.post("/2fa/setup")
def setup_2fa(
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id = str(current_user["id"])
    user = get_user_by_id_orm(db, user_id)
    if not user:
        raise HTTPException(404, detail=make_error(ErrorCode.USER_NOT_FOUND))

    secret = pyotp.random_base32()
    update_user_orm(db, user_id, {"totp_secret": secret})

    email = user.get("email", "")
    otpauth_url = pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="Relan")

    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(otpauth_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    qr_img.save(buf, format="PNG")
    qr_code_base64 = base64.b64encode(buf.getvalue()).decode()

    return {
        "secret": secret,
        "otpauth_url": otpauth_url,
        "qr_code_base64": qr_code_base64,
    }


@router.post("/2fa/verify")
def verify_2fa(
    body: TwoFAVerifyRequest,
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id = str(current_user["id"])
    user = get_user_by_id_orm(db, user_id)
    if not user:
        raise HTTPException(404, detail=make_error(ErrorCode.USER_NOT_FOUND))

    secret = user.get("totp_secret")
    if not secret:
        raise HTTPException(400, detail=make_error(ErrorCode.USER_2FA_NOT_SETUP))

    if not pyotp.TOTP(secret).verify(body.code):
        raise HTTPException(400, detail=make_error(ErrorCode.USER_2FA_INVALID_CODE))

    update_user_orm(db, user_id, {"totp_enabled": True})
    return {"success": True}


@router.delete("/2fa")
def disable_2fa(
    body: DisableTwoFARequest,
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id = str(current_user["id"])
    user = get_user_by_id_orm(db, user_id)
    if not user:
        raise HTTPException(404, detail=make_error(ErrorCode.USER_NOT_FOUND))

    if not user.get("totp_enabled"):
        raise HTTPException(400, detail=make_error(ErrorCode.USER_2FA_NOT_ACTIVE))

    if not verify_user_password_orm(db, user_id, body.password):
        raise HTTPException(401, detail=make_error(ErrorCode.USER_WRONG_PASSWORD))

    secret = user.get("totp_secret")
    if not secret:
        raise HTTPException(400, detail=make_error(ErrorCode.USER_2FA_INVALID_STATE))

    if not pyotp.TOTP(secret).verify(body.code):
        raise HTTPException(400, detail=make_error(ErrorCode.USER_2FA_INVALID_CODE))

    update_user_orm(db, user_id, {"totp_enabled": False, "totp_secret": None})
    return {"success": True}


# ─── API KEYS ─────────────────────────────────────────────────────────────────


@router.get("/api-keys")
def list_api_keys(
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id_uuid = uuid.UUID(str(current_user["id"]))
    return get_user_api_keys_orm(db, user_id_uuid)


@router.post("/api-keys")
def create_api_key(
    body: CreateApiKeyRequest,
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id_uuid = uuid.UUID(str(current_user["id"]))
    expires_at: Optional[datetime] = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    key_dict, raw_key = create_api_key_orm(db, user_id_uuid, body.name, expires_at)
    return {
        "key_id": key_dict.get("id"),
        "name": key_dict.get("name"),
        "raw_key": raw_key,
        "key_prefix": key_dict.get("key_prefix"),
        "created_at": key_dict.get("created_at"),
    }


@router.delete("/api-keys/{key_id}")
def revoke_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user_orm),
    db: Session = Depends(get_db_session),
):
    user_id_uuid = uuid.UUID(str(current_user["id"]))
    try:
        key_id_uuid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(400, detail=make_error(ErrorCode.USER_API_KEY_INVALID))

    ok = revoke_api_key_orm(db, user_id_uuid, key_id_uuid)
    if not ok:
        raise HTTPException(404, detail=make_error(ErrorCode.USER_API_KEY_NOT_FOUND))
    return {"success": True}
