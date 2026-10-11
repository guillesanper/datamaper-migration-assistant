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

# Hash bcrypt (12 rondas, como los OTP reales) de un valor que no es ningún código emitido:
# solo sirve para gastar el mismo tiempo cuando no hay OTP que comprobar
_DUMMY_OTP_HASH = b"$2b$12$9XTijnjNcZY/VgfXJrM15O73quxUg4jcAvmv7.7oexphe6M0cVZoG"


def simulate_otp_check() -> None:
    """
    Gasta el tiempo de una comprobación de OTP (un bcrypt) sin comprobar nada.

    Los caminos «sin cuenta» o «sin OTP» de verify-code, reset, resend-code y forgot la llaman
    para no responder antes que los caminos con OTP real. Es una mitigación de mejor esfuerzo
    contra la enumeración por tiempo, no una garantía.
    """
    bcrypt.checkpw(b"dummy-otp", _DUMMY_OTP_HASH)


# ============================================================================
# FUNCIONES ORM (SQLAlchemy)
# ============================================================================


def create_otp_orm(
    db: Session, user_id: str, otp_code: str, expires_in_minutes: int = 10
) -> Dict[str, Any]:
    """
    Crea o actualiza un OTP para un usuario (ORM version).

    La tabla email_otps usa user_id como PK, por lo que solo puede haber
    un OTP activo por usuario. Si ya existe, se actualiza y se reinician sus
    intentos fallidos (un reenvío da otra tanda).

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
            existing.failed_attempts = 0  # type: ignore[assignment]
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
    - No ha agotado sus intentos (OTP_MAX_ATTEMPTS comprobaciones erróneas lo invalidan)
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
        Cada comprobación reserva un intento con un UPDATE atómico antes de mirar el código:
        peticiones concurrentes no obtienen intentos de más. Al llegar a OTP_MAX_ATTEMPTS
        el OTP se elimina y ni el código correcto vuelve a valer (hay que pedir otro).
    """
    from sqlalchemy import update

    from app.config.security import security_settings
    from app.models.orm import EmailOTP

    try:
        now = datetime.now(timezone.utc)

        # Buscar OTP
        otp = db.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()

        if not otp:
            logger.warning(f"OTP no encontrado para user_id: {str(user_id)[:8]}...")
            simulate_otp_check()  # mismo tiempo que con un OTP: no delata «sin OTP»
            return False

        # Verificar expiración
        if otp.expires_at < now:
            logger.warning(
                f"OTP expirado para user_id: {str(user_id)[:8]}... (expires_at: {otp.expires_at})"
            )
            # Eliminar OTP expirado
            db.delete(otp)
            db.commit()
            simulate_otp_check()
            return False

        # Reservar el intento de forma atómica (failed_attempts = failed_attempts + 1)
        attempts = db.execute(
            update(EmailOTP)
            .where(EmailOTP.user_id == user_id)
            .values(failed_attempts=EmailOTP.failed_attempts + 1)
            .returning(EmailOTP.failed_attempts)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()

        if attempts is None:
            # Otra petición lo eliminó entre la lectura y el UPDATE
            return False

        max_attempts = security_settings.OTP_MAX_ATTEMPTS

        # Verificar código (constant-time comparison con bcrypt); si otra petición ya agotó
        # los intentos, ni se comprueba
        if attempts <= max_attempts and bcrypt.checkpw(
            otp_code.encode("utf-8"), otp.otp_code.encode("utf-8")
        ):
            # OTP válido - eliminar
            db.delete(otp)
            db.commit()
            logger.info(f"OTP verificado exitosamente para user_id: {str(user_id)[:8]}...")
            return True

        if attempts >= max_attempts:
            # Intentos agotados: el OTP se invalida
            db.delete(otp)
            logger.warning(
                f"OTP invalidado por intentos fallidos para user_id: {str(user_id)[:8]}..."
            )
        else:
            logger.warning(f"OTP incorrecto para user_id: {str(user_id)[:8]}...")
        db.commit()
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
