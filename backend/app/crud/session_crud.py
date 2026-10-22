"""
Operaciones CRUD para la tabla de sesiones de usuario.
Maneja creación, validación, actualización y revocación de sesiones.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import SESSION_LIFETIME_HOURS

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCIONES ORM (SQLAlchemy)
# ============================================================================


def create_session_orm(
    db,
    user_id: str,
    session_token: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    device_fingerprint: Optional[str] = None,
    expires_in_hours: int = SESSION_LIFETIME_HOURS,
    refresh_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crea una nueva sesión de usuario después de login (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario (UUID string)
        session_token: Token único de sesión (ya hasheado)
        ip_address: Dirección IP del cliente
        user_agent: User agent del navegador
        device_fingerprint: Fingerprint del dispositivo
        expires_in_hours: Horas hasta expiración (default SESSION_LIFETIME_HOURS, 24)
        refresh_token: Token de refresh opcional

    Returns:
        Dict con los datos de la sesión creada

    Raises:
        IntegrityError: Si el session_token ya existe
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.orm import UserSession

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = now + timedelta(hours=expires_in_hours)

        new_session = UserSession(
            id=uuid.uuid4(),
            user_id=user_id,
            session_token=session_token,
            refresh_token=refresh_token,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint,
            created_at=now,
            last_activity=now,
            expires_at=expires_at,
            is_revoked=False,
        )

        db.add(new_session)
        db.commit()
        db.refresh(new_session)

        logger.info(f"Sesión creada para usuario {user_id}")

        return {
            "id": str(new_session.id),
            "user_id": str(new_session.user_id),
            "session_token": new_session.session_token,
            "refresh_token": new_session.refresh_token,
            "ip_address": new_session.ip_address,
            "user_agent": new_session.user_agent,
            "device_fingerprint": new_session.device_fingerprint,
            "created_at": new_session.created_at,
            "last_activity": new_session.last_activity,
            "expires_at": new_session.expires_at,
            "is_revoked": new_session.is_revoked,
        }

    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error de integridad al crear sesión: {str(e)}")
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error al crear sesión: {str(e)}")
        raise


def get_session_by_token_orm(db, session_token: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene una sesión activa por su token (ORM version).
    Valida que no esté revocada ni expirada.

    Args:
        db: SQLAlchemy Session
        session_token: Token de sesión (hasheado)

    Returns:
        Dict con los datos de la sesión o None si no existe/está inválida
    """
    from app.models.orm import UserSession

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        session = (
            db.query(UserSession)
            .filter(
                UserSession.session_token == session_token,
                UserSession.is_revoked == False,
                UserSession.expires_at > now,
            )
            .first()
        )

        if not session:
            return None

        return {
            "id": str(session.id),
            "user_id": str(session.user_id),
            "session_token": session.session_token,
            "refresh_token": session.refresh_token,
            "ip_address": session.ip_address,
            "user_agent": session.user_agent,
            "device_fingerprint": session.device_fingerprint,
            "created_at": session.created_at,
            "last_activity": session.last_activity,
            "expires_at": session.expires_at,
            "is_revoked": session.is_revoked,
        }

    except Exception as e:
        logger.error(f"Error al obtener sesión por token: {str(e)}")
        return None


def update_session_activity_orm(db, session_token: str) -> bool:
    """
    Actualiza el timestamp de última actividad de una sesión (ORM version).

    Args:
        db: SQLAlchemy Session
        session_token: Token de sesión (hasheado)

    Returns:
        True si se actualizó exitosamente, False en caso contrario
    """
    from app.models.orm import UserSession

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        result = (
            db.query(UserSession)
            .filter(
                UserSession.session_token == session_token,
                UserSession.is_revoked == False,
                UserSession.expires_at > now,
            )
            .update({"last_activity": now}, synchronize_session=False)
        )

        db.commit()

        return bool(result > 0)

    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar actividad de sesión: {str(e)}")
        return False


def revoke_session_orm(db, session_token: str, reason: Optional[str] = None) -> bool:
    """
    Revoca una sesión (logout / cierre manual) (ORM version).

    Args:
        db: SQLAlchemy Session
        session_token: Token de sesión a revocar
        reason: Razón de revocación opcional (ej: "logout", "security", "expired")

    Returns:
        True si se revocó exitosamente, False en caso contrario
    """
    from app.models.orm import UserSession

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        result = (
            db.query(UserSession)
            .filter(UserSession.session_token == session_token, UserSession.is_revoked == False)
            .update(
                {"is_revoked": True, "revoked_at": now, "revoked_reason": reason},
                synchronize_session=False,
            )
        )

        db.commit()

        if result > 0:
            logger.info(f"Sesión revocada: {reason or 'no reason'}")
            return True
        else:
            logger.warning(f"Sesión no encontrada para revocar")
            return False

    except Exception as e:
        db.rollback()
        logger.error(f"Error al revocar sesión: {str(e)}")
        return False


def revoke_user_session_by_id_orm(
    db, user_id: str, session_id: str, reason: Optional[str] = None
) -> bool:
    """
    Revoca una sesión específica de un usuario por ID (ORM version).
    Útil para que usuarios revoquen sesiones desde "dispositivos activos".

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario propietario
        session_id: ID de la sesión a revocar
        reason: Razón de revocación opcional

    Returns:
        True si se revocó exitosamente, False en caso contrario
    """
    from app.models.orm import UserSession

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        result = (
            db.query(UserSession)
            .filter(
                UserSession.id == session_id,
                UserSession.user_id == user_id,
                UserSession.is_revoked == False,
            )
            .update(
                {"is_revoked": True, "revoked_at": now, "revoked_reason": reason or "user_revoked"},
                synchronize_session=False,
            )
        )

        db.commit()

        if result > 0:
            logger.info(f"Sesión {session_id} revocada por usuario {user_id}")
            return True
        else:
            logger.warning(f"Sesión no encontrada o ya revocada")
            return False

    except Exception as e:
        db.rollback()
        logger.error(f"Error al revocar sesión por ID: {str(e)}")
        return False


def get_user_sessions_orm(db, user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
    """
    Obtiene todas las sesiones de un usuario (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario
        active_only: Si True, solo sesiones activas (no revocadas ni expiradas)

    Returns:
        Lista de diccionarios con datos de sesiones
    """
    from app.models.orm import UserSession
    from app.utils.orm_helpers import models_to_dict_list

    try:
        query = db.query(UserSession).filter(UserSession.user_id == user_id)

        if active_only:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            query = query.filter(UserSession.is_revoked == False, UserSession.expires_at > now)

        sessions = query.order_by(UserSession.last_activity.desc()).all()

        return models_to_dict_list(sessions)

    except Exception as e:
        logger.error(f"Error al obtener sesiones de usuario {user_id}: {str(e)}")
        return []


def cleanup_expired_sessions_orm(db, days_old: int = 30) -> int:
    """
    Elimina sesiones expiradas antiguas de la base de datos (ORM version).

    Args:
        db: SQLAlchemy Session
        days_old: Días de antigüedad para considerar una sesión eliminable
                  (solo elimina sesiones expiradas hace más de X días)

    Returns:
        Número de sesiones eliminadas
    """
    from app.models.orm import UserSession

    try:
        # Validar que days_old sea un entero para prevenir problemas
        days_old = int(days_old)

        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_old)

        # Eliminar sesiones que:
        # 1. Están expiradas (expires_at < now)
        # 2. La fecha de expiración es antigua (expires_at < cutoff_date)
        # O que están revocadas hace mucho tiempo
        result = (
            db.query(UserSession)
            .filter(
                (UserSession.expires_at < cutoff_date)
                | ((UserSession.is_revoked == True) & (UserSession.revoked_at < cutoff_date))
            )
            .delete(synchronize_session=False)
        )

        db.commit()

        if result > 0:
            logger.info(f"Limpiadas {result} sesiones expiradas")

        return int(result)

    except Exception as e:
        db.rollback()
        logger.error(f"Error al limpiar sesiones expiradas: {str(e)}")
        return 0


def revoke_all_user_sessions_orm(
    db, user_id: str, except_token: Optional[str] = None, reason: str = "user_request"
) -> int:
    """
    Revoca todas las sesiones de un usuario (ORM version).
    Útil para "cerrar sesión en todos los dispositivos" o cambio de password.

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario
        except_token: Token de sesión a excluir de la revocación (opcional)
        reason: Razón de revocación

    Returns:
        Número de sesiones revocadas
    """
    from app.models.orm import UserSession

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        query = db.query(UserSession).filter(
            UserSession.user_id == user_id, UserSession.is_revoked == False
        )

        # Excluir una sesión específica si se proporciona
        if except_token:
            query = query.filter(UserSession.session_token != except_token)

        result = query.update(
            {"is_revoked": True, "revoked_at": now, "revoked_reason": reason},
            synchronize_session=False,
        )

        db.commit()

        if result > 0:
            logger.info(f"Revocadas {result} sesiones para usuario {user_id}")

        return int(result)

    except Exception as e:
        db.rollback()
        logger.error(f"Error al revocar todas las sesiones: {str(e)}")
        return 0
