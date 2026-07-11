# app/routers/auth.py
from datetime import datetime
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator

# CRUDs ORM
from app.crud import session_crud, user_crud
from app.database.session import get_db_session as get_db
from app.middleware.rate_limiting import rate_limit
from app.routers.dependencies import get_current_user, get_current_user_optional
from app.services.auth_service import AuthenticationError, AuthService, DatabaseError
from app.utils.cookies import SESSION_COOKIE_CONFIG, sign_cookie
from app.utils.email_verification import send_verification_code
from app.utils.security import SecurityUtils
from app.utils.security_logger import (
    SecurityLogger,
    log_login_failed,
    log_login_success,
    log_registration_failed,
    log_registration_success,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# Modelos Pydantic


class RegisterRequest(BaseModel):
    username: Annotated[str, Field(min_length=3, max_length=50)]
    email: EmailStr
    password: Annotated[str, Field(min_length=8)]
    confirm_password: str

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Las contraseñas no coinciden")
        return v


class LoginRequest(BaseModel):
    identifier: Annotated[str, Field(min_length=1)]
    password: Annotated[str, Field(min_length=1)]


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: Annotated[str, Field(min_length=8, max_length=8)]


class ResendCodeRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: Annotated[str, Field(min_length=8, max_length=8)]
    new_password: Annotated[str, Field(min_length=8)]


class StandardResponse(BaseModel):
    success: bool
    message: str
    data: Dict[str, Any] | None = None
    error: str | None = None


# Utilidades


def create_success_response(
    message: str, data: Dict[str, Any] | None = None, status_code: int = 200
) -> JSONResponse:
    """Crea una respuesta exitosa estándar"""
    return JSONResponse(
        status_code=status_code, content={"success": True, "message": message, "data": data}
    )


def create_error_response(message: str, error_code: str, status_code: int = 400) -> JSONResponse:
    """Crea una respuesta de error estándar"""
    return JSONResponse(
        status_code=status_code, content={"success": False, "error": error_code, "message": message}
    )


def serialize_user(user_dict: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Convierte campos datetime a strings para serialización JSON
    Necesario porque JSON.dumps no puede serializar objetos datetime
    """
    if not user_dict:
        return None

    serialized = dict(user_dict)

    datetime_fields = ["created_at", "updated_at", "last_login_at", "locked_until"]

    for field in datetime_fields:
        if serialized.get(field):
            if isinstance(serialized[field], datetime):
                serialized[field] = serialized[field].isoformat()

    return serialized


# Endpoints


@router.post("/register", response_model=StandardResponse, status_code=201)
async def register(request: Request, data: RegisterRequest, db=Depends(get_db)):
    """Registro de nuevo usuario"""

    auth_service = AuthService(db)

    try:
        result = auth_service.create_user(
            username=data.username, email=data.email, password=data.password
        )

        await log_registration_success(
            request, result["username"], result["email"], result["user_id"]
        )

        return create_success_response(
            message="Usuario registrado exitosamente", data=result, status_code=201
        )

    except ValueError as e:
        await log_registration_failed(
            request, data.username, data.email, f"weak_password: {str(e)}"
        )
        return create_error_response(message=str(e), error_code="weak_password", status_code=400)

    except AuthenticationError as e:
        await log_registration_failed(request, data.username, data.email, str(e))
        return create_error_response(
            message=str(e), error_code="registration_failed", status_code=409
        )

    except DatabaseError as e:
        await log_registration_failed(
            request, data.username, data.email, f"database_error: {str(e)}"
        )
        return create_error_response(
            message="Error interno del servidor", error_code="internal_error", status_code=500
        )


@router.post("/login", response_model=StandardResponse)
async def login(request: Request, data: LoginRequest, db=Depends(get_db)):
    """Login de usuario"""
    import hashlib
    import secrets
    from datetime import datetime, timedelta, timezone

    auth_service = AuthService(db)
    client_ip = SecurityUtils.get_client_ip(request)

    try:
        user = auth_service.authenticate_user(
            identifier=data.identifier, password=data.password, client_ip=client_ip
        )

        await log_login_success(request, user["username"], user["id"])
        serialized_user = serialize_user(user)

        # CREAR SESIÓN EN BASE DE DATOS
        from datetime import datetime, timedelta, timezone

        session_token = secrets.token_urlsafe(32)
        hashed_token = hashlib.sha256(session_token.encode()).hexdigest()

        # Crear sesión usando CRUD ORM
        session_crud.create_session_orm(
            db=db,
            user_id=str(user["id"]),
            session_token=hashed_token,
            refresh_token=None,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent", ""),
            device_fingerprint=None,
        )

        # Firmar el token de sesión
        cookie_value = sign_cookie(session_token)

        response = create_success_response(message="Login exitoso", data={"user": serialized_user})

        response.set_cookie(key="session", value=cookie_value, **SESSION_COOKIE_CONFIG)

        return response

    except AuthenticationError as e:
        error_message = str(e)

        await log_login_failed(request, data.identifier, error_message)

        if "bloqueada" in error_message.lower():
            status_code = 423
            error_code = "account_locked"
            response_data = None
        elif "verificar" in error_message.lower():
            status_code = 403
            error_code = "email_not_verified"

            try:
                # Intentar buscar por email primero
                user_data = user_crud.get_user_by_email_orm(db, data.identifier)
                if not user_data:
                    # Si no es email, intentar por username
                    user_data = user_crud.get_user_by_username_orm(db, data.identifier)
                response_data = {"email": user_data["email"]} if user_data else None
            except:
                response_data = None
        else:
            status_code = 401
            error_code = "invalid_credentials"
            response_data = None

        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "error": error_code,
                "message": error_message,
                "data": response_data,
            },
        )

    except Exception as e:
        await SecurityLogger.log_suspicious_activity(request, "login_error", {"error": str(e)})
        return create_error_response(
            message="Error interno del servidor", error_code="internal_error", status_code=500
        )


@router.post("/verify-code")
async def verify_code(request: Request, db=Depends(get_db)):
    """Verificación de código OTP con login automático"""

    try:
        # Leer body
        body = await request.json()

        # Validar con Pydantic
        data = VerifyCodeRequest(**body)

        # Llamar al servicio
        auth_service = AuthService(db)
        result = auth_service.verify_email_code(email=data.email, code=data.code)

        # Obtener datos del usuario usando CRUD ORM
        user = user_crud.get_user_by_id_orm(db, result["user_id"])

        # Serializar usuario
        user_data = serialize_user(user)

        # Log de seguridad
        await SecurityLogger.log_email_verification_attempt(
            request, data.email, True, user_id=result["user_id"]
        )

        # Crear respuesta
        response = create_success_response(
            message="Email verificado exitosamente", data={"user": user_data}
        )

        # Crear sesión en base de datos (igual que en login)
        import hashlib
        import secrets

        client_ip = SecurityUtils.get_client_ip(request)
        session_token = secrets.token_urlsafe(32)
        hashed_token = hashlib.sha256(session_token.encode()).hexdigest()

        session_crud.create_session_orm(
            db=db,
            user_id=str(result["user_id"]),
            session_token=hashed_token,
            refresh_token=None,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent", ""),
            device_fingerprint=None,
        )

        cookie_value = sign_cookie(session_token)
        response.set_cookie(key="session", value=cookie_value, **SESSION_COOKIE_CONFIG)

        return response

    except ValidationError as e:
        return create_error_response(
            message=f"Datos inválidos: {e.errors()[0]['msg']}",
            error_code="validation_error",
            status_code=400,
        )

    except AuthenticationError as e:
        await SecurityLogger.log_email_verification_attempt(
            request, body.get("email", ""), False, failure_reason=str(e)
        )

        if "no encontrado" in str(e).lower():
            status_code = 404
        else:
            status_code = 400

        return create_error_response(
            message=str(e), error_code="verification_failed", status_code=status_code
        )

    except Exception as e:
        print(f"Error inesperado en verify_code: {type(e).__name__} - {str(e)}")
        import traceback

        traceback.print_exc()

        return create_error_response(
            message="Error interno del servidor", error_code="internal_error", status_code=500
        )


@router.post("/resend-code", response_model=StandardResponse)
@rate_limit(3, 600)
async def resend_code(request: Request, data: ResendCodeRequest, db=Depends(get_db)):
    """Reenvío de código de verificación"""

    email = SecurityUtils.sanitize_email(data.email)

    try:
        # Obtener usuario usando CRUD ORM
        user = user_crud.get_user_by_email_orm(db, email)

        if not user:
            return create_error_response(
                message="Usuario no encontrado", error_code="user_not_found", status_code=404
            )

        send_verification_code(db, email, user["id"])

        return create_success_response(message="Código reenviado correctamente")

    except Exception as e:
        await SecurityLogger.log_suspicious_activity(
            request, "resend_code_error", {"error": str(e)}
        )
        return create_error_response(
            message="Error interno del servidor", error_code="internal_error", status_code=500
        )


@router.post("/reset", response_model=StandardResponse)
@rate_limit(5, 600)
async def reset_password(request: Request, data: ResetPasswordRequest, db=Depends(get_db)):
    """Reset de contraseña con código OTP"""

    auth_service = AuthService(db)

    try:
        auth_service.reset_password(
            email=data.email, code=data.code, new_password=data.new_password
        )

        await SecurityLogger.log_password_reset_attempt(
            request, data.email, True, None, stage="reset"  # type: ignore[arg-type]
        )

        return create_success_response(message="Contraseña actualizada exitosamente")

    except ValueError as e:
        return create_error_response(message=str(e), error_code="weak_password", status_code=400)

    except AuthenticationError as e:
        return create_error_response(message=str(e), error_code="reset_failed", status_code=400)


@router.post("/logout", response_model=StandardResponse)
async def logout(current_user=Depends(get_current_user), db=Depends(get_db)):
    """Cierre de sesión (solo actual dispositivo)"""
    try:
        # Obtener cookie firmada
        import hashlib

        from fastapi import Request

        from app.utils.cookies import verify_signed_cookie

        # Revocar la sesión actual usando CRUD ORM
        session_cookie = current_user.get("session_token")
        if session_cookie:
            hashed_token = hashlib.sha256(session_cookie.encode()).hexdigest()
            session_crud.revoke_session_orm(db, hashed_token, reason="user_logout")

        response = create_success_response("Sesión cerrada exitosamente")
        response.delete_cookie(
            "session",
            httponly=SESSION_COOKIE_CONFIG["httponly"],
            secure=SESSION_COOKIE_CONFIG["secure"],
            samesite=SESSION_COOKIE_CONFIG["samesite"],
        )
        return response

    except Exception as e:
        print(f"Error en logout: {e}")
        return create_error_response(
            message="Error al cerrar sesión", error_code="logout_failed", status_code=500
        )


@router.post("/logout-all", response_model=StandardResponse)
async def logout_all(current_user=Depends(get_current_user), db=Depends(get_db)):
    """Cierre de sesión en todos los dispositivos"""

    try:
        # Revocar todas las sesiones usando CRUD ORM
        session_crud.revoke_all_user_sessions_orm(
            db, user_id=str(current_user["id"]), reason="user_logout_all"
        )

        response = create_success_response("Sesiones cerradas en todos los dispositivos")
        response.delete_cookie(
            "session",
            httponly=SESSION_COOKIE_CONFIG["httponly"],
            secure=SESSION_COOKIE_CONFIG["secure"],
            samesite=SESSION_COOKIE_CONFIG["samesite"],
        )
        return response

    except Exception as e:
        print(f"Error en logout_all: {e}")
        return create_error_response(
            message="Error al cerrar sesiones", error_code="logout_error", status_code=500
        )


@router.get("/me", response_model=StandardResponse)
async def get_me(current_user=Depends(get_current_user)):
    """Obtener usuario actual"""
    import os

    # Asegurarse de que todos los datetimes están serializados
    serialized_user = dict(current_user)
    datetime_fields = [
        "created_at",
        "updated_at",
        "last_login_at",
        "locked_until",
        "last_activity",
        "expires_at",
    ]

    for field in datetime_fields:
        if field in serialized_user and serialized_user[field]:
            if isinstance(serialized_user[field], datetime):
                serialized_user[field] = serialized_user[field].isoformat()

    # Inject is_admin based on ADMIN_USER_IDS env var (no DB migration needed)
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    admin_ids = [uid.strip() for uid in admin_ids_str.split(",") if uid.strip()]
    serialized_user["is_admin"] = str(serialized_user.get("id", "")) in admin_ids

    return create_success_response(
        message="Usuario obtenido exitosamente", data={"user": serialized_user}
    )


@router.get("/check")
async def check_auth(current_user=Depends(get_current_user_optional)):
    """Verificar autenticación"""

    return {"authenticated": current_user is not None}
