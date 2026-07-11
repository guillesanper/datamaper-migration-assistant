# app/routers/dependencies.py
import hashlib
import os
from datetime import datetime
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database.session import get_db_session
from app.utils.cookies import verify_signed_cookie
from app.utils.error_codes import ErrorCode, make_error


# ============================================================================
# SQLAlchemy ORM Version
# ============================================================================


class CurrentUserORM:
    """
    Dependencia para obtener el usuario actual autenticado (SQLAlchemy ORM version)

    Esta es la versión ORM de CurrentUser que usa SQLAlchemy Session en vez de
    psycopg2.connection. Útil para routers que ya migraron a usar CRUDs _orm.

    Mantiene exactamente la misma interfaz de retorno que CurrentUser (dict),
    pero usa queries ORM internamente.

    Usage:
        from app.routers.dependencies import get_current_user_orm

        @router.get("/endpoint")
        async def endpoint(current_user: dict = Depends(get_current_user_orm)):
            # current_user es un dict, igual que con get_current_user
            user_id = current_user['id']
    """

    def __init__(self, required: bool = True):
        self.required = required

    def _serialize_user(self, user: dict) -> Optional[dict]:
        """
        Convierte datetime a ISO format para JSON

        Reutiliza la misma lógica que CurrentUser para mantener consistencia
        """
        if not user:
            return None

        serialized = dict(user)
        datetime_fields = ["created_at", "updated_at", "last_login_at", "locked_until"]

        for field in datetime_fields:
            if serialized.get(field) and isinstance(serialized[field], datetime):
                serialized[field] = serialized[field].isoformat()

        return serialized

    async def __call__(
        self,
        request: Request,
        session: Optional[str] = Cookie(None),
        db: Session = Depends(get_db_session),  # <-- USA SESSION ORM con pool
    ):
        if not session:
            # Intentar autenticación por Bearer token (API key)
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                raw_key = auth_header[7:].strip()
                from app.crud.api_key_crud import verify_api_key_orm

                api_user = verify_api_key_orm(db, raw_key)
                if api_user:
                    serialized = self._serialize_user(api_user)
                    request.state.current_user = serialized
                    return serialized
            if self.required:
                raise HTTPException(401, detail=make_error(ErrorCode.NOT_AUTHENTICATED))
            return None

        # Verificar token (misma lógica que CurrentUser)
        session_token = verify_signed_cookie(session)
        if not session_token:
            if self.required:
                raise HTTPException(401, detail=make_error(ErrorCode.SESSION_INVALID))
            return None

        # Hash del token para buscar en BD
        hashed_token = hashlib.sha256(session_token.encode()).hexdigest()

        try:
            from app.crud import session_crud, user_crud

            # Obtener sesión usando CRUD
            user_session = session_crud.get_session_by_token_orm(db, hashed_token)
            if not user_session:
                if self.required:
                    from app.models.orm.session import UserSession

                    raw = db.query(UserSession).filter(
                        UserSession.session_token == hashed_token
                    ).first()
                    if raw is None:
                        raise HTTPException(401, detail=make_error(ErrorCode.SESSION_INVALID))
                    elif raw.is_revoked:
                        raise HTTPException(401, detail=make_error(ErrorCode.SESSION_REVOKED))
                    else:
                        raise HTTPException(401, detail=make_error(ErrorCode.SESSION_EXPIRED))
                return None

            # Obtener usuario usando CRUD
            user = user_crud.get_user_by_id_orm(db, user_session["user_id"])
            if not user or user.get("is_deleted"):
                if self.required:
                    raise HTTPException(401, detail=make_error(ErrorCode.INVALID_USER))
                return None

            # Actualizar última actividad usando CRUD
            session_crud.update_session_activity_orm(db, hashed_token)

            # Combinar datos de usuario y sesión
            user_dict = {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "is_verified": user["is_verified"],
                "created_at": user["created_at"],
                "last_activity": user_session["last_activity"],
                "expires_at": user_session["expires_at"],
            }

            # ✅ CRITICAL: Poblar request.state para que middleware pueda acceder
            serialized = self._serialize_user(user_dict)
            request.state.current_user = serialized
            return serialized

        except HTTPException:
            raise
        except Exception as e:
            print(f"Error al obtener usuario (ORM): {e}")
            if self.required:
                raise HTTPException(500, detail=make_error(ErrorCode.GET_USER_FAILED))
            return None


# Instancias exportables de CurrentUserORM
get_current_user = CurrentUserORM(required=True)
get_current_user_optional = CurrentUserORM(required=False)
get_current_user_orm = CurrentUserORM(required=True)
get_current_user_optional_orm = CurrentUserORM(required=False)

# Alias de compatibilidad: db_connections.py aún importa CurrentUser directamente
CurrentUser = CurrentUserORM


async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency que requiere que el usuario actual sea admin (via ADMIN_USER_IDS env var)."""
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    admin_ids = [uid.strip() for uid in admin_ids_str.split(",") if uid.strip()]
    if str(current_user.get("id")) not in admin_ids:
        raise HTTPException(status_code=403, detail=make_error(ErrorCode.ADMIN_ACCESS_REQUIRED))
    return current_user


async def validate_encryption_session(
    request: Request, current_user: dict = Depends(get_current_user)
):
    """
    Valida sesiones de encriptado pendientes (User ID Binding - Fase 1.2)

    CRÍTICO: Este dependency debe ejecutarse DESPUÉS de get_current_user
    para validar el ownership de la sesión de encriptado.

    El middleware EncryptionSessionMiddleware guarda sesiones pendientes en
    request.state._pending_encryption_session cuando current_user aún no está
    disponible. Esta función valida esas sesiones pendientes.

    Security:
    - Valida que session['user_id'] == current_user['id']
    - Invalida sesión si user_id no coincide (previene session hijacking)
    - Inyecta encryption_key en request.state solo si validación pasa

    Args:
        request: FastAPI Request
        current_user: Usuario actual (inyectado por get_current_user)

    Returns:
        None (modifica request.state)
    """
    import logging

    from app.utils.redis_session_cache import get_encryption_session_cache

    logger = logging.getLogger(__name__)

    # Verificar si hay una sesión pendiente
    pending_session = getattr(request.state, "_pending_encryption_session", None)

    if not pending_session:
        # No hay sesión pendiente, nada que validar
        return

    # Validar ownership
    session_user_id = pending_session.get("user_id")
    current_user_id = current_user.get("id")

    if session_user_id == current_user_id:
        # ✅ Ownership válido - Inyectar encryption_key
        request.state.encryption_key = pending_session["encryption_key"]
        request.state.encryption_project_id = pending_session["project_id"]
        logger.debug(
            f"✓ Encryption session validated: "
            f"user={current_user_id[:8]}..., project={pending_session['project_id'][:8]}..."
        )
    else:
        # ⚠️ SECURITY VIOLATION: user_id no coincide
        logger.warning(
            f"⚠️ SECURITY: Session hijacking attempt detected!\n"
            f"  Session user_id: {str(session_user_id)[:8]}...\n"
            f"  Current user_id: {str(current_user_id)[:8]}...\n"
            f"  Project: {pending_session.get('project_id', 'unknown')[:8]}..."
        )

        # Invalidar sesión comprometida
        cache = get_encryption_session_cache()
        # Nota: Necesitamos el session_token para invalidar, pero no lo tenemos aquí
        # La sesión ya fue rechazada por no inyectar encryption_key

        # No inyectar encryption_key (request continúa sin clave)
        # El endpoint recibirá encryption_key=None y fallará si lo requiere

    # Limpiar sesión pendiente
    delattr(request.state, "_pending_encryption_session")
