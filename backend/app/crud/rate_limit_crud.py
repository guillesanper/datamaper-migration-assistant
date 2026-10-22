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


def _bump_counter(
    db,
    identifier: str,
    endpoint: str,
    now: datetime,
    window_minutes: int,
    max_count: int,
    block_until: datetime,
    block_on_reach: bool,
):
    """
    Suma uno al contador con un único UPDATE atómico (UPDATE ... RETURNING).

    En la misma sentencia: reinicia la ventana si venció (contador a 1 y window_start = now),
    suma si no y fija el bloqueo si el contador lo exige. Un bloqueo vigente deja la fila
    fuera del WHERE: un identificador bloqueado no suma. Postgres retiene la fila hasta el
    commit y reevalúa el WHERE con su última versión, así que las peticiones simultáneas no
    pierden incrementos ni reinician la ventana a la vez (como verify_otp_orm).

    Args:
        db: SQLAlchemy Session
        identifier: Identificador único (IP hasheada, cuenta)
        endpoint: Endpoint solicitado
        now: Instante de la petición
        window_minutes: Duración de la ventana en minutos
        max_count: Máximo de peticiones (o de fallos) de la ventana
        block_until: Fin del bloqueo si este request lo fija
        block_on_reach: True bloquea al llegar al máximo (`>=`, record_failure_orm, también
            con la ventana reiniciada); False al superarlo (`>`, check_limit_orm: un reinicio
            nunca bloquea)

    Returns:
        (request_count, window_start, blocked_until) de la fila tras el UPDATE, o None si no
        hay fila o está bloqueada.
    """
    from sqlalchemy import and_, case, not_, or_, update

    from app.models.orm import SecurityRateLimit

    expired = SecurityRateLimit.window_start < now - timedelta(minutes=window_minutes)
    new_count = case((expired, 1), else_=SecurityRateLimit.request_count + 1)
    if block_on_reach:
        over_max = new_count >= max_count
    else:
        over_max = and_(not_(expired), new_count > max_count)

    return db.execute(
        update(SecurityRateLimit)
        .where(
            SecurityRateLimit.identifier == identifier,
            SecurityRateLimit.endpoint == endpoint,
            or_(SecurityRateLimit.blocked_until.is_(None), SecurityRateLimit.blocked_until <= now),
        )
        .values(
            request_count=new_count,
            attempt_count=case((expired, 1), else_=SecurityRateLimit.attempt_count + 1),
            window_start=case((expired, now), else_=SecurityRateLimit.window_start),
            last_attempt=now,
            updated_at=now,
            blocked_until=case((over_max, block_until), else_=SecurityRateLimit.blocked_until),
        )
        .returning(
            SecurityRateLimit.request_count,
            SecurityRateLimit.window_start,
            SecurityRateLimit.blocked_until,
        )
        .execution_options(synchronize_session=False)
    ).first()


def _count_atomically(
    db,
    identifier: str,
    ip_address: str,
    endpoint: str,
    now: datetime,
    window_minutes: int,
    max_count: int,
    block_duration_minutes: int,
    block_on_reach: bool,
) -> Dict[str, Any]:
    """
    Cuenta un request (o un fallo) sin perder incrementos ni la carrera de la primera petición.

    Primero intenta el UPDATE atómico (_bump_counter). Si no actualiza ninguna fila, distingue
    «bloqueado» (se devuelve sin sumar) de «no existe» (INSERT ... ON CONFLICT DO NOTHING: si
    otra petición la creó a la vez, esta pierde el INSERT y vuelve al UPDATE). Confirma con
    commit en los caminos que escriben.

    Returns:
        Dict con request_count, window_start (None si ya estaba bloqueado), blocked_until,
        is_blocked y was_blocked (estaba bloqueado antes: no se sumó).

    Raises:
        RuntimeError: Si la fila no se puede actualizar ni crear (p. ej. otro identificador
        ocupa el mismo (ip_address, endpoint))
    """
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.orm import SecurityRateLimit

    block_until = now + timedelta(minutes=block_duration_minutes)

    # UPDATE -> (INSERT) -> UPDATE: la última vuelta cubre que otra petición cree la fila
    for _attempt in range(3):
        bumped = _bump_counter(
            db, identifier, endpoint, now, window_minutes, max_count, block_until, block_on_reach
        )
        if bumped is not None:
            request_count, window_start, blocked_until = bumped
            if block_on_reach:
                is_blocked = request_count >= max_count
            else:
                # la petición que reinicia la ventana (window_start == now) nunca bloquea
                is_blocked = request_count > max_count and window_start != now
            db.commit()
            return {
                "request_count": request_count,
                "window_start": window_start,
                "blocked_until": blocked_until if is_blocked else None,
                "is_blocked": is_blocked,
                "was_blocked": False,
            }

        state = db.execute(
            select(SecurityRateLimit.request_count, SecurityRateLimit.blocked_until).where(
                SecurityRateLimit.identifier == identifier, SecurityRateLimit.endpoint == endpoint
            )
        ).first()

        if state is None:
            # La primera petición de un identificador: con `>=` y máximo 1 ya bloquea
            first_blocks = block_on_reach and 1 >= max_count
            created = db.execute(
                pg_insert(SecurityRateLimit)
                .values(
                    identifier=identifier,
                    ip_address=ip_address,
                    endpoint=endpoint,
                    request_count=1,
                    attempt_count=1,
                    window_start=now,
                    last_attempt=now,
                    blocked_until=block_until if first_blocks else None,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing()
                .returning(SecurityRateLimit.id)
            ).scalar_one_or_none()
            if created is not None:
                db.commit()
                return {
                    "request_count": 1,
                    "window_start": now,
                    "blocked_until": block_until if first_blocks else None,
                    "is_blocked": first_blocks,
                    "was_blocked": False,
                }
            # Otra petición creó la fila a la vez: se cuenta por el UPDATE en la vuelta siguiente
        elif state.blocked_until is not None and state.blocked_until > now:
            return {
                "request_count": state.request_count,
                "window_start": None,
                "blocked_until": state.blocked_until,
                "is_blocked": True,
                "was_blocked": True,
            }
        # Fila sin bloqueo vigente que el UPDATE no vio (se creó o venció el bloqueo entre
        # medias): se vuelve a intentar por el UPDATE

    raise RuntimeError("No se pudo contar en el limitador: la fila no se puede crear ni actualizar")


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
    try:
        now = datetime.now(timezone.utc)

        counted = _count_atomically(
            db,
            identifier=identifier,
            ip_address=ip_address,
            endpoint=endpoint,
            now=now,
            window_minutes=window_minutes,
            max_count=max_requests,
            block_duration_minutes=block_duration_minutes,
            block_on_reach=False,
        )

        if counted["was_blocked"]:
            logger.warning(
                f"Identificador bloqueado: {identifier} hasta {counted['blocked_until']}"
            )
        elif counted["is_blocked"]:
            logger.warning(
                f"Límite excedido para {identifier} en {endpoint}. "
                f"Bloqueado hasta {counted['blocked_until']}"
            )

        if counted["is_blocked"]:
            return {
                "is_allowed": False,
                "is_blocked": True,
                "remaining": 0,
                "reset_at": counted["blocked_until"],
                "blocked_until": counted["blocked_until"],
                "request_count": counted["request_count"],
            }

        return {
            "is_allowed": True,
            "is_blocked": False,
            "remaining": max_requests - counted["request_count"],
            "reset_at": counted["window_start"] + timedelta(minutes=window_minutes),
            "blocked_until": None,
            "request_count": counted["request_count"],
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
    try:
        now = datetime.now(timezone.utc)

        counted = _count_atomically(
            db,
            identifier=identifier,
            ip_address=ip_address,
            endpoint=endpoint,
            now=now,
            window_minutes=window_minutes,
            max_count=max_failures,
            block_duration_minutes=block_duration_minutes,
            block_on_reach=True,
        )

        if counted["is_blocked"] and not counted["was_blocked"]:
            logger.warning(
                f"Límite de fallos alcanzado para {identifier} en {endpoint}. "
                f"Bloqueado hasta {counted['blocked_until']}"
            )

        if counted["is_blocked"]:
            # Ya bloqueado por otra petición (no suma) o bloqueado por este fallo
            return {
                "is_allowed": False,
                "is_blocked": True,
                "remaining": 0,
                "reset_at": counted["blocked_until"],
                "blocked_until": counted["blocked_until"],
                "request_count": counted["request_count"],
            }

        return {
            "is_allowed": True,
            "is_blocked": False,
            "remaining": max(0, max_failures - counted["request_count"]),
            "reset_at": counted["window_start"] + timedelta(minutes=window_minutes),
            "blocked_until": None,
            "request_count": counted["request_count"],
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
