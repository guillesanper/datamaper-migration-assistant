"""
Operaciones CRUD para la tabla de csrf_tokens.
Maneja generación, validación y limpieza de tokens CSRF.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCIONES ORM (SQLAlchemy)
# ============================================================================


def generate_token_orm(
    db, session_id: str, ip_address: str, expires_in_minutes: int = 60, token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Genera un nuevo token CSRF único (ORM version).

    Args:
        db: SQLAlchemy Session
        session_id: ID de sesión asociado
        ip_address: IP address (hasheada) del cliente
        expires_in_minutes: Minutos hasta la expiración (default 60)
        token: Token opcional (para tests). Si no se proporciona, se genera uno nuevo

    Returns:
        Dict con los datos del token creado (id, token, session_id, ip_address,
        expires_at, used, used_at, created_at)

    Raises:
        Exception: Si hay error al crear el token
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.orm import CSRFToken
    from app.utils.orm_helpers import model_to_dict
    from app.utils.security import SecurityUtils

    try:
        # Generar token único y seguro usando SecurityUtils (o usar el proporcionado para tests)
        if token is None:
            token = SecurityUtils.generate_csrf_token()

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=expires_in_minutes)

        new_token = CSRFToken(
            token=token,
            session_id=session_id,
            ip_address=ip_address,
            expires_at=expires_at,
            used=False,
            created_at=now,
        )

        db.add(new_token)
        db.commit()
        db.refresh(new_token)

        logger.debug(f"Token CSRF generado para sesión {session_id[:8]}...")

        result = model_to_dict(new_token)
        assert result is not None
        return result

    except IntegrityError as e:
        db.rollback()
        logger.error(f"Error de integridad al generar token CSRF: {str(e)}")
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error al generar token CSRF: {str(e)}")
        raise


def validate_token_orm(
    db, token: str, session_id: Optional[str] = None, ip_address: Optional[str] = None
) -> bool:
    """
    Valida un token CSRF y lo marca como usado (ORM version).

    Verifica que:
    - El token existe
    - No ha expirado
    - No ha sido usado previamente
    - Opcionalmente valida session_id e ip_address

    Args:
        db: SQLAlchemy Session
        token: Token CSRF a validar
        session_id: ID de sesión opcional para validación adicional
        ip_address: IP address opcional para validación adicional

    Returns:
        True si el token es válido, False en caso contrario

    Note:
        Si el token es válido, se marca automáticamente como usado (used=True, used_at=now)
    """
    from app.models.orm import CSRFToken

    try:
        now = datetime.now(timezone.utc)

        # Buscar token
        query = db.query(CSRFToken).filter(CSRFToken.token == token)

        # Aplicar validaciones opcionales
        if session_id:
            query = query.filter(CSRFToken.session_id == session_id)

        if ip_address:
            query = query.filter(CSRFToken.ip_address == ip_address)

        csrf_token = query.first()

        # Validaciones
        if not csrf_token:
            logger.warning(f"Token CSRF no encontrado o no coincide con validaciones")
            return False

        if csrf_token.used:
            logger.warning(f"Token CSRF ya fue usado previamente")
            return False

        if csrf_token.expires_at < now:
            logger.warning(f"Token CSRF expirado (expires_at: {csrf_token.expires_at})")
            return False

        # Token válido - marcar como usado
        csrf_token.used = True
        csrf_token.used_at = now
        db.commit()

        logger.debug(f"Token CSRF validado y marcado como usado")

        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error al validar token CSRF: {str(e)}")
        return False


def cleanup_orm(db, hours_old: int = 24) -> int:
    """
    Limpia tokens CSRF antiguos (ORM version).
    Elimina tokens que:
    - Han expirado hace más de X horas, O
    - Han sido usados hace más de X horas

    Args:
        db: SQLAlchemy Session
        hours_old: Horas de antigüedad para considerar un token eliminable (default 24)

    Returns:
        Número de tokens eliminados

    Raises:
        Exception: Si hay error al eliminar tokens
    """
    from app.models.orm import CSRFToken

    try:
        # Validar que hours_old sea un entero para prevenir problemas
        hours_old = int(hours_old)

        now = datetime.now(timezone.utc)
        cutoff_date = now - timedelta(hours=hours_old)

        # Eliminar tokens que:
        # 1. Expiraron hace más de X horas (expires_at < cutoff_date), O
        # 2. Fueron usados hace más de X horas (used=True AND used_at < cutoff_date)
        result = (
            db.query(CSRFToken)
            .filter(
                (CSRFToken.expires_at < cutoff_date)
                | ((CSRFToken.used == True) & (CSRFToken.used_at < cutoff_date))
            )
            .delete(synchronize_session=False)
        )

        db.commit()

        if result > 0:
            logger.info(f"Limpiados {result} tokens CSRF antiguos (>{hours_old} horas)")

        return int(result)

    except Exception as e:
        db.rollback()
        logger.error(f"Error al limpiar tokens CSRF: {str(e)}")
        raise
