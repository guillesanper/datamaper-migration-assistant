"""
Operaciones CRUD para la tabla de email_otps.
Maneja creación, verificación y eliminación de códigos OTP de email.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCIONES ORM (SQLAlchemy)
# ============================================================================


def create_otp_orm(
    db: Session, user_id: str, otp_code: str, expires_in_minutes: int = 10
) -> Dict[str, Any]:
    """
    Crea o actualiza un OTP para un usuario (ORM version).

    La tabla email_otps usa user_id como PK, por lo que solo puede haber
    un OTP activo por usuario. Si ya existe, se actualiza.

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario
        otp_code: Código OTP en texto plano (será cifrado antes de guardar)
        expires_in_minutes: Minutos hasta la expiración (default 10)

    Returns:
        Dict con los datos del OTP creado (user_id, otp_code, expires_at)
        NOTA: otp_code retornado es el hash, NO el código original

    Raises:
        Exception: Si hay error al crear/actualizar el OTP
    """
    from app.models.orm import EmailOTP
    from app.utils.orm_helpers import model_to_dict

    try:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=expires_in_minutes)

        # Cifrar OTP con bcrypt
        otp_hash = bcrypt.hashpw(otp_code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Buscar OTP existente (user_id es PK)
        existing = db.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()

        if existing:
            # Actualizar OTP existente (ON CONFLICT DO UPDATE equivalente)
            existing.otp_code = otp_hash  # type: ignore[assignment]
            existing.expires_at = expires_at  # type: ignore[assignment]
            db.commit()
            db.refresh(existing)
            result = model_to_dict(existing)
            logger.debug(f"OTP actualizado para user_id {str(user_id)[:8]}...")
        else:
            # Crear nuevo OTP
            new_otp = EmailOTP(user_id=user_id, otp_code=otp_hash, expires_at=expires_at)
            db.add(new_otp)
            db.commit()
            db.refresh(new_otp)
            result = model_to_dict(new_otp)
            logger.debug(f"OTP creado para user_id {str(user_id)[:8]}...")

        assert result is not None, "model_to_dict returned None for a non-None model"
        return result

    except Exception as e:
        db.rollback()
        logger.error(f"Error al crear/actualizar OTP: {str(e)}")
        raise


def verify_otp_orm(db: Session, user_id: str, otp_code: str) -> bool:
    """
    Verifica un código OTP y lo elimina si es válido (ORM version).

    Verifica que:
    - El OTP existe para el usuario
    - No ha expirado
    - El código coincide (usando bcrypt.checkpw para constant-time comparison)

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario
        otp_code: Código OTP en texto plano a verificar

    Returns:
        True si el OTP es válido (y se elimina), False en caso contrario

    Note:
        Si el OTP es válido, se elimina automáticamente de la BD.
        Si el OTP está expirado, también se elimina automáticamente.
    """
    from app.models.orm import EmailOTP

    try:
        now = datetime.now(timezone.utc)

        # Buscar OTP
        otp = db.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()

        if not otp:
            logger.warning(f"OTP no encontrado para user_id: {str(user_id)[:8]}...")
            return False

        # Verificar expiración
        if otp.expires_at < now:
            logger.warning(
                f"OTP expirado para user_id: {str(user_id)[:8]}... (expires_at: {otp.expires_at})"
            )
            # Eliminar OTP expirado
            db.delete(otp)
            db.commit()
            return False

        # Verificar código (constant-time comparison con bcrypt)
        if bcrypt.checkpw(otp_code.encode("utf-8"), otp.otp_code.encode("utf-8")):
            # OTP válido - eliminar
            db.delete(otp)
            db.commit()
            logger.info(f"OTP verificado exitosamente para user_id: {str(user_id)[:8]}...")
            return True
        else:
            logger.warning(f"OTP incorrecto para user_id: {str(user_id)[:8]}...")
            return False

    except Exception as e:
        db.rollback()
        logger.error(f"Error al verificar OTP: {str(e)}")
        return False


def delete_otp_orm(db: Session, user_id: str) -> bool:
    """
    Elimina el OTP de un usuario (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario

    Returns:
        True si se eliminó el OTP, False si no existía

    Raises:
        Exception: Si hay error al eliminar el OTP
    """
    from app.models.orm import EmailOTP

    try:
        # Buscar OTP
        otp = db.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()

        if not otp:
            logger.debug(f"No hay OTP para eliminar (user_id: {str(user_id)[:8]}...)")
            return False

        # Eliminar OTP
        db.delete(otp)
        db.commit()
        logger.debug(f"OTP eliminado para user_id: {str(user_id)[:8]}...")

        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error al eliminar OTP: {str(e)}")
        raise
