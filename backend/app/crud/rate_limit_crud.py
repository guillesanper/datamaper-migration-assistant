"""
Operaciones CRUD para la tabla de security_rate_limits.
Maneja rate limiting por IP, email, user_id y endpoint.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCIONES ORM (SQLAlchemy)
# ============================================================================


def check_limit_orm(
    db,
    identifier: str,
    ip_address: str,
    endpoint: str,
    max_requests: int = 100,
    window_minutes: int = 60,
    block_duration_minutes: int = 15,
) -> Dict[str, Any]:
    """
    Verifica si un identificador ha excedido el límite de requests (ORM version).
    Crea o actualiza el registro de rate limiting.

    Args:
        db: SQLAlchemy Session
        identifier: Identificador único (IP, email, user_id)
        ip_address: IP address (hasheada)
        endpoint: Endpoint solicitado
        max_requests: Número máximo de requests permitidos en la ventana
        window_minutes: Duración de la ventana de tiempo en minutos
        block_duration_minutes: Duración del bloqueo en minutos si se excede el límite

    Returns:
        Dict con:
            - is_allowed: bool - Si el request está permitido
            - is_blocked: bool - Si el identificador está bloqueado
            - remaining: int - Requests restantes en la ventana actual
            - reset_at: datetime - Cuándo se resetea el contador
            - blocked_until: datetime - Cuándo expira el bloqueo (si aplica)
            - request_count: int - Número actual de requests en la ventana

    Raises:
        Exception: Si hay error al verificar el límite
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.orm import SecurityRateLimit

    try:
        now = datetime.now(timezone.utc)

        # Buscar registro existente
        rate_limit = (
            db.query(SecurityRateLimit)
            .filter(
                SecurityRateLimit.identifier == identifier, SecurityRateLimit.endpoint == endpoint
            )
            .first()
        )

        # Si no existe, crear uno nuevo
        if not rate_limit:
            rate_limit = SecurityRateLimit(
                identifier=identifier,
                ip_address=ip_address,
                endpoint=endpoint,
                request_count=1,
                attempt_count=1,
                window_start=now,
                last_attempt=now,
                created_at=now,
                updated_at=now,
            )
            db.add(rate_limit)
            db.commit()
            db.refresh(rate_limit)

            return {
                "is_allowed": True,
                "is_blocked": False,
                "remaining": max_requests - 1,
                "reset_at": now + timedelta(minutes=window_minutes),
                "blocked_until": None,
                "request_count": 1,
            }

        # Verificar si está bloqueado
        if rate_limit.blocked_until and rate_limit.blocked_until > now:
            logger.warning(
                f"Identificador bloqueado: {identifier} hasta {rate_limit.blocked_until}"
            )
            return {
                "is_allowed": False,
                "is_blocked": True,
                "remaining": 0,
                "reset_at": rate_limit.blocked_until,
                "blocked_until": rate_limit.blocked_until,
                "request_count": rate_limit.request_count,
            }

        # Verificar si la ventana expiró
        window_end = rate_limit.window_start + timedelta(minutes=window_minutes)
        if now > window_end:
            # Resetear ventana
            rate_limit.window_start = now
            rate_limit.request_count = 1
            rate_limit.attempt_count = 1
            rate_limit.last_attempt = now
            rate_limit.updated_at = now
            db.commit()

            return {
                "is_allowed": True,
                "is_blocked": False,
                "remaining": max_requests - 1,
                "reset_at": now + timedelta(minutes=window_minutes),
                "blocked_until": None,
                "request_count": 1,
            }

        # Incrementar contador
        rate_limit.request_count += 1
        rate_limit.attempt_count += 1
        rate_limit.last_attempt = now
        rate_limit.updated_at = now

        # Verificar si se excedió el límite
        if rate_limit.request_count > max_requests:
            # Bloquear identificador
            rate_limit.blocked_until = now + timedelta(minutes=block_duration_minutes)
            db.commit()

            logger.warning(
                f"Límite excedido para {identifier} en {endpoint}. Bloqueado hasta {rate_limit.blocked_until}"
            )

            return {
                "is_allowed": False,
                "is_blocked": True,
                "remaining": 0,
                "reset_at": rate_limit.blocked_until,
                "blocked_until": rate_limit.blocked_until,
                "request_count": rate_limit.request_count,
            }

        db.commit()

        return {
            "is_allowed": True,
            "is_blocked": False,
            "remaining": max_requests - rate_limit.request_count,
            "reset_at": window_end,
            "blocked_until": None,
            "request_count": rate_limit.request_count,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error al verificar rate limit: {str(e)}")
        raise


def peek_limit_orm(db, identifier: str, endpoint: str) -> Dict[str, Any]:
    """
    Consulta sin contar si un identificador está bloqueado (ORM version).

    Es de solo lectura: no crea el registro ni toca el contador. Un identificador sin
    registro, o cuyo bloqueo ya venció, no está bloqueado. Mismo criterio de bloqueo que
    check_limit_orm (blocked_until > ahora, con independencia de la ventana).

    Args:
        db: SQLAlchemy Session
        identifier: Identificador único (IP hasheada, cuenta)
        endpoint: Endpoint solicitado

    Returns:
        Dict con is_allowed, is_blocked, blocked_until y request_count (0 sin registro)

    Raises:
        Exception: Si hay error al consultar el límite
    """
    from app.models.orm import SecurityRateLimit

    try:
        now = datetime.now(timezone.utc)

        rate_limit = (
            db.query(SecurityRateLimit)
            .filter(
                SecurityRateLimit.identifier == identifier, SecurityRateLimit.endpoint == endpoint
            )
            .first()
        )

        if rate_limit is None:
            return {
                "is_allowed": True,
                "is_blocked": False,
                "blocked_until": None,
                "request_count": 0,
            }

        is_blocked = bool(rate_limit.blocked_until and rate_limit.blocked_until > now)

        return {
            "is_allowed": not is_blocked,
            "is_blocked": is_blocked,
            "blocked_until": rate_limit.blocked_until if is_blocked else None,
            "request_count": rate_limit.request_count,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error al consultar rate limit: {str(e)}")
        raise


def record_failure_orm(
    db,
    identifier: str,
    ip_address: str,
    endpoint: str,
    max_failures: int = 5,
    window_minutes: int = 15,
    block_duration_minutes: int = 15,
) -> Dict[str, Any]:
    """
    Anota un fallo y bloquea al llegar al máximo de fallos de la ventana (ORM version).

    A diferencia de check_limit_orm (que permite `max_requests` peticiones y bloquea con la
    siguiente: `>`), aquí el fallo número `max_failures` ya fija el bloqueo (`>=`). Es lo que
    hace falta cuando solo se cuentan los fallos: si no, tras `max_failures` fallos quedaría un
    intento más (el login correcto de después pasaría) antes del primer 429.

    Un identificador ya bloqueado no suma (como en check_limit_orm); con la ventana vencida el
    contador reinicia en 1.

    Args:
        db: SQLAlchemy Session
        identifier: Identificador único (IP hasheada)
        ip_address: IP address (hasheada)
        endpoint: Endpoint solicitado
        max_failures: Fallos que caben en la ventana; el que llega a este número bloquea
        window_minutes: Duración de la ventana en minutos
        block_duration_minutes: Duración del bloqueo en minutos

    Returns:
        Dict con is_allowed, is_blocked, remaining, reset_at, blocked_until y request_count
        (mismas claves que check_limit_orm; is_blocked ya es True en el fallo que bloquea)

    Raises:
        Exception: Si hay error al anotar el fallo
    """
    from app.models.orm import SecurityRateLimit

    try:
        now = datetime.now(timezone.utc)

        rate_limit = (
            db.query(SecurityRateLimit)
            .filter(
                SecurityRateLimit.identifier == identifier, SecurityRateLimit.endpoint == endpoint
            )
            .first()
        )

        if rate_limit is None:
            rate_limit = SecurityRateLimit(
                identifier=identifier,
                ip_address=ip_address,
                endpoint=endpoint,
                request_count=1,
                attempt_count=1,
                window_start=now,
                last_attempt=now,
                created_at=now,
                updated_at=now,
            )
            db.add(rate_limit)
        elif rate_limit.blocked_until and rate_limit.blocked_until > now:
            # Otra petición lo bloqueó entre la comprobación y este fallo: no suma
            return {
                "is_allowed": False,
                "is_blocked": True,
                "remaining": 0,
                "reset_at": rate_limit.blocked_until,
                "blocked_until": rate_limit.blocked_until,
                "request_count": rate_limit.request_count,
            }
        elif now > rate_limit.window_start + timedelta(minutes=window_minutes):
            # Ventana vencida: el fallo abre una nueva
            rate_limit.window_start = now
            rate_limit.request_count = 1
            rate_limit.attempt_count = 1
        else:
            rate_limit.request_count += 1
            rate_limit.attempt_count += 1

        rate_limit.last_attempt = now
        rate_limit.updated_at = now

        is_blocked = rate_limit.request_count >= max_failures
        if is_blocked:
            rate_limit.blocked_until = now + timedelta(minutes=block_duration_minutes)

        db.commit()

        if is_blocked:
            logger.warning(
                f"Límite de fallos alcanzado para {identifier} en {endpoint}. "
                f"Bloqueado hasta {rate_limit.blocked_until}"
            )

        return {
            "is_allowed": not is_blocked,
            "is_blocked": is_blocked,
            "remaining": max(0, max_failures - rate_limit.request_count),
            "reset_at": (
                rate_limit.blocked_until
                if is_blocked
                else rate_limit.window_start + timedelta(minutes=window_minutes)
            ),
            "blocked_until": rate_limit.blocked_until if is_blocked else None,
            "request_count": rate_limit.request_count,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error al anotar fallo de rate limit: {str(e)}")
        raise


def update_orm(db, identifier: str, endpoint: str, increment: int = 1) -> bool:
    """
    Actualiza el contador de requests para un identificador/endpoint (ORM version).

    Args:
        db: SQLAlchemy Session
        identifier: Identificador único (IP, email, user_id)
        endpoint: Endpoint solicitado
        increment: Cantidad a incrementar (default 1)

    Returns:
        True si se actualizó exitosamente, False en caso contrario
    """
    from app.models.orm import SecurityRateLimit

    try:
        now = datetime.now(timezone.utc)

        result = (
            db.query(SecurityRateLimit)
            .filter(
                SecurityRateLimit.identifier == identifier, SecurityRateLimit.endpoint == endpoint
            )
            .update(
                {
                    "request_count": SecurityRateLimit.request_count + increment,
                    "attempt_count": SecurityRateLimit.attempt_count + increment,
                    "last_attempt": now,
                    "updated_at": now,
                },
                synchronize_session=False,
            )
        )

        db.commit()

        if result > 0:
            logger.debug(f"Rate limit actualizado para {identifier} en {endpoint}")
            return True
        else:
            logger.warning(f"No se encontró rate limit para actualizar: {identifier} en {endpoint}")
            return False

    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar rate limit: {str(e)}")
        return False


def get_info_orm(db, identifier: str, endpoint: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene información de rate limiting para un identificador/endpoint (ORM version).

    Args:
        db: SQLAlchemy Session
        identifier: Identificador único (IP, email, user_id)
        endpoint: Endpoint solicitado

    Returns:
        Dict con información del rate limit o None si no existe
    """
    from app.models.orm import SecurityRateLimit
    from app.utils.orm_helpers import model_to_dict

    try:
        rate_limit = (
            db.query(SecurityRateLimit)
            .filter(
                SecurityRateLimit.identifier == identifier, SecurityRateLimit.endpoint == endpoint
            )
            .first()
        )

        if not rate_limit:
            return None

        return model_to_dict(rate_limit)

    except Exception as e:
        logger.error(f"Error al obtener info de rate limit: {str(e)}")
        return None


def reset_orm(db, identifier: str, endpoint: str) -> bool:
    """
    Resetea el contador de rate limit para un identificador/endpoint (ORM version).
    Útil para desbloquear manualmente o resetear contadores.

    Args:
        db: SQLAlchemy Session
        identifier: Identificador único (IP, email, user_id)
        endpoint: Endpoint solicitado

    Returns:
        True si se reseteó exitosamente, False en caso contrario
    """
    from app.models.orm import SecurityRateLimit

    try:
        now = datetime.now(timezone.utc)

        result = (
            db.query(SecurityRateLimit)
            .filter(
                SecurityRateLimit.identifier == identifier, SecurityRateLimit.endpoint == endpoint
            )
            .update(
                {
                    "request_count": 0,
                    "attempt_count": 0,
                    "window_start": now,
                    "last_attempt": now,
                    "blocked_until": None,
                    "updated_at": now,
                },
                synchronize_session=False,
            )
        )

        db.commit()

        if result > 0:
            logger.info(f"Rate limit reseteado para {identifier} en {endpoint}")
            return True
        else:
            logger.warning(f"No se encontró rate limit para resetear: {identifier} en {endpoint}")
            return False

    except Exception as e:
        db.rollback()
        logger.error(f"Error al resetear rate limit: {str(e)}")
        return False


def cleanup_orm(db, days_old: int = 30) -> int:
    """
    Limpia registros antiguos de rate limiting (ORM version).
    Elimina registros que:
    - Tienen más de X días de antigüedad
    - No están bloqueados actualmente
    - No han tenido actividad reciente

    Args:
        db: SQLAlchemy Session
        days_old: Días de antigüedad para considerar un registro eliminable

    Returns:
        Número de registros eliminados

    Raises:
        Exception: Si hay error al eliminar registros
    """
    from app.models.orm import SecurityRateLimit

    try:
        # Validar que days_old sea un entero para prevenir problemas
        days_old = int(days_old)

        now = datetime.now(timezone.utc)
        cutoff_date = now - timedelta(days=days_old)

        # Eliminar registros que:
        # 1. No han sido actualizados recientemente (updated_at < cutoff_date)
        # 2. No están bloqueados actualmente (blocked_until is NULL o blocked_until < now)
        result = (
            db.query(SecurityRateLimit)
            .filter(
                SecurityRateLimit.updated_at < cutoff_date,
                (SecurityRateLimit.blocked_until.is_(None))
                | (SecurityRateLimit.blocked_until < now),
            )
            .delete(synchronize_session=False)
        )

        db.commit()

        if result > 0:
            logger.info(f"Limpiados {result} registros de rate limit antiguos (>{days_old} días)")

        return int(result)

    except Exception as e:
        db.rollback()
        logger.error(f"Error al limpiar registros de rate limit: {str(e)}")
        raise
