"""
Middleware de Rate Limiting para DataMap
Implementa control de límites de requests por IP y endpoint usando base de datos
"""

import asyncio
import functools
import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.config.security import security_settings
from app.database.session import get_db_session
from app.utils.error_codes import ErrorCode, make_error
from app.utils.security import SecurityUtils

get_db = get_db_session  # Alias para backward compatibility con tests
from app.crud import rate_limit_crud


def _account_identifier(account: str) -> str:
    """Identificador del contador por cuenta: hash con sal del email normalizado (sin PII)"""
    normalized = SecurityUtils.sanitize_email(account)
    salt = security_settings.IP_HASH_SALT.encode("utf-8")
    return "acct:" + hashlib.sha256(salt + normalized.encode("utf-8")).hexdigest()[:32]


def _counter_target(
    request: Request,
    endpoint: Optional[str],
    rule: Optional[Dict[str, Any]],
    account: Optional[str] = None,
) -> Tuple[str, str, int, int, int]:
    """
    Clave y regla del contador al que pertenece el request

    Es la única fuente de la clave: comprobar, contar y anotar fallos tienen que apuntar a la
    misma fila.

    Returns:
        (identificador, endpoint, máximo, ventana en minutos, bloqueo en minutos)
    """
    if endpoint is None:
        endpoint = request.url.path

    client_ip = SecurityUtils.get_client_ip(request)
    hashed_ip = SecurityUtils.hash_ip_address(client_ip)
    identifier = _account_identifier(account) if account is not None else hashed_ip

    # Obtener configuración para este endpoint
    config = security_settings.get_rate_limit_config(endpoint, rule)
    max_attempts = config["max_attempts"]
    window_seconds = config["window_seconds"]
    block_duration = config.get("block_duration", window_seconds)

    # Convertir segundos a minutos para el CRUD
    return identifier, endpoint, max_attempts, window_seconds // 60, block_duration // 60


def _in_session(operation: Callable[..., Any], **kwargs: Any) -> Dict[str, Any]:
    """
    Ejecuta una operación del CRUD con su propia sesión de BD

    Es síncrona y está pensada para run_in_threadpool: la sesión se abre, se usa y se cierra en
    el mismo hilo (una sesión por hilo, nunca la de la corrutina), y el event loop no espera a
    la BD. `get_db_session` se resuelve al llamar: los tests lo parchean en este módulo.
    """
    db = next(get_db_session())
    try:
        return dict(operation(db, **kwargs))
    finally:
        db.close()


class DatabaseRateLimiter:
    """Rate limiter que usa base de datos para persistencia"""

    @staticmethod
    async def count_request(
        request: Request,
        endpoint: Optional[str] = None,
        rule: Optional[Dict[str, Any]] = None,
        account: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cuenta el request contra su regla y devuelve el estado del contador

        Args:
            request: Request de FastAPI
            endpoint: Clave del contador (si no se proporciona, se usa request.url.path)
            rule: Regla explícita ({"max_attempts", "window_seconds"[, "block_duration"]}).
                Sin regla se usa la de por defecto; en desarrollo manda siempre la permisiva
            account: Cuenta (p. ej. el email) sobre la que contar en lugar de la IP, para que
                quien reparte las peticiones entre IPs no eluda el límite

        Returns:
            dict: resultado de check_limit_orm (is_allowed, blocked_until...). Si la BD falla
            se permite el request (fail-open)
        """
        identifier, endpoint, max_attempts, window_minutes, block_duration_minutes = (
            _counter_target(request, endpoint, rule, account)
        )

        try:
            # check_limit_orm hace TODO: verifica bloqueo, crea/actualiza registro,
            # incrementa contador, resetea ventana si expiró, bloquea si excede límite.
            # La E/S de BD corre en el threadpool: no bloquea el event loop
            return await run_in_threadpool(
                _in_session,
                rate_limit_crud.check_limit_orm,
                identifier=identifier,  # IP (hash) o cuenta
                # (ip_address, endpoint) es único: el contador de cuenta ocupa su propia fila
                ip_address=identifier,
                endpoint=endpoint,
                max_requests=max_attempts,
                window_minutes=window_minutes,
                block_duration_minutes=block_duration_minutes,
            )

        except Exception as e:
            print(f"Error en rate limiting: {e}")
            # Fail-open: permitir request si DB falla (evita bloquear tráfico legítimo)
            return {"is_allowed": True, "is_blocked": False, "blocked_until": None}

    @staticmethod
    async def check_rate_limit(
        request: Request,
        endpoint: Optional[str] = None,
        rule: Optional[Dict[str, Any]] = None,
        account: Optional[str] = None,
    ) -> bool:
        """
        Verifica si el request está dentro de los límites permitidos

        Args:
            request: Request de FastAPI
            endpoint: Endpoint específico (si no se proporciona, se usa request.url.path)
            rule: Regla explícita; tiene prioridad sobre la de por defecto
            account: Cuenta sobre la que contar en lugar de la IP

        Returns:
            bool: True si está dentro del límite, False si excede
        """
        result = await DatabaseRateLimiter.count_request(request, endpoint, rule, account)
        return bool(result["is_allowed"])

    @staticmethod
    async def peek_request(
        request: Request,
        endpoint: Optional[str] = None,
        rule: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Comprueba sin contar si la IP está bloqueada en el contador de la ruta

        Args:
            request: Request de FastAPI
            endpoint: Clave del contador (si no se proporciona, se usa request.url.path)
            rule: Regla explícita; en desarrollo manda siempre la permisiva

        Returns:
            dict: resultado de peek_limit_orm (is_allowed, blocked_until...). Si la BD falla
            se permite el request (fail-open)
        """
        identifier, endpoint, _max, _window, _block = _counter_target(request, endpoint, rule)

        try:
            return await run_in_threadpool(
                _in_session,
                rate_limit_crud.peek_limit_orm,
                identifier=identifier,
                endpoint=endpoint,
            )

        except Exception as e:
            print(f"Error en rate limiting: {e}")
            # Fail-open: igual que count_request
            return {"is_allowed": True, "is_blocked": False, "blocked_until": None}

    @staticmethod
    async def count_failure(
        request: Request,
        endpoint: Optional[str] = None,
        rule: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Anota un fallo de la IP en el contador de la ruta; al llegar al máximo, la bloquea

        Args:
            request: Request de FastAPI
            endpoint: Clave del contador (si no se proporciona, se usa request.url.path)
            rule: Regla explícita ({"max_attempts", "window_seconds"[, "block_duration"]}):
                el máximo es de fallos por ventana. En desarrollo manda siempre la permisiva

        Returns:
            dict: resultado de record_failure_orm. Si la BD falla el fallo no se anota (el
            request que ya falló no debe convertirse en un 500)
        """
        identifier, endpoint, max_failures, window_minutes, block_minutes = _counter_target(
            request, endpoint, rule
        )

        try:
            # record_failure_orm bloquea AL LLEGAR al máximo (check_limit_orm, con la
            # siguiente petición): con solo fallos, si no, quedaría un intento de más
            return await run_in_threadpool(
                _in_session,
                rate_limit_crud.record_failure_orm,
                identifier=identifier,
                ip_address=identifier,
                endpoint=endpoint,
                max_failures=max_failures,
                window_minutes=window_minutes,
                block_duration_minutes=block_minutes,
            )

        except Exception as e:
            print(f"Error en rate limiting: {e}")
            return {"is_allowed": True, "is_blocked": False, "blocked_until": None}

    @staticmethod
    async def get_rate_limit_info(
        request: Request, endpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Obtiene información sobre el estado del rate limiting para una IP/endpoint

        Args:
            request: Request de FastAPI
            endpoint: Endpoint específico

        Returns:
            dict: Información del rate limiting
        """
        if endpoint is None:
            endpoint = request.url.path

        client_ip = SecurityUtils.get_client_ip(request)
        hashed_ip = SecurityUtils.hash_ip_address(client_ip)

        config = security_settings.get_rate_limit_config(endpoint)

        try:
            # Obtener sesión de SQLAlchemy
            db = next(get_db_session())
            try:
                # Obtener info usando CRUD ORM
                info = rate_limit_crud.get_info_orm(db, identifier=hashed_ip, endpoint=endpoint)

                current_time = datetime.now(timezone.utc)

                if info:
                    is_blocked = info["blocked_until"] and info["blocked_until"] > current_time
                    remaining_attempts = max(0, config["max_attempts"] - info["request_count"])

                    return {
                        "is_blocked": is_blocked,
                        "attempt_count": info["request_count"],
                        "max_attempts": config["max_attempts"],
                        "remaining_attempts": remaining_attempts,
                        "blocked_until": info["blocked_until"],
                        "window_seconds": config["window_seconds"],
                        "last_attempt": info["last_attempt"],
                    }
                else:
                    return {
                        "is_blocked": False,
                        "attempt_count": 0,
                        "max_attempts": config["max_attempts"],
                        "remaining_attempts": config["max_attempts"],
                        "blocked_until": None,
                        "window_seconds": config["window_seconds"],
                        "last_attempt": None,
                    }

            finally:
                db.close()

        except Exception as e:
            print(f"Error obteniendo info de rate limiting: {e}")
            return {
                "is_blocked": False,
                "attempt_count": 0,
                "max_attempts": config["max_attempts"],
                "remaining_attempts": config["max_attempts"],
                "blocked_until": None,
                "window_seconds": config["window_seconds"],
                "last_attempt": None,
            }

    @staticmethod
    async def reset_rate_limit(ip_address: str, endpoint: str):
        """
        Resetea el rate limit para una IP y endpoint específicos

        Args:
            ip_address: IP a resetear
            endpoint: Endpoint específico (requerido)

        Note:
            El CRUD ORM actual solo soporta reseteo por endpoint específico.
            Para resetear todos los endpoints de una IP, llame a este método
            múltiples veces con cada endpoint.
        """
        hashed_ip = SecurityUtils.hash_ip_address(ip_address)

        try:
            # Obtener sesión de SQLAlchemy
            db = next(get_db_session())
            try:
                # Resetear usando CRUD ORM
                success = rate_limit_crud.reset_orm(db, identifier=hashed_ip, endpoint=endpoint)

                if success:
                    print(f"Rate limit reseteado para {ip_address} en {endpoint}")
                else:
                    print(f"No se encontró rate limit para resetear: {ip_address} en {endpoint}")

            finally:
                db.close()

        except Exception as e:
            print(f"Error reseteando rate limit: {e}")

    @staticmethod
    async def cleanup_old_records():
        """Limpia registros antiguos de rate limiting"""
        try:
            # Obtener configuración de retención
            retention_days = security_settings.RATE_LIMIT_RETENTION_DAYS

            # Obtener sesión de SQLAlchemy
            db = next(get_db_session())
            try:
                # Limpiar usando CRUD ORM
                deleted_count = rate_limit_crud.cleanup_orm(db, days_old=retention_days)

                if deleted_count > 0:
                    print(
                        f"Limpiados {deleted_count} registros antiguos de rate limiting (>{retention_days} días)"
                    )

            finally:
                db.close()

        except Exception as e:
            print(f"Error limpiando registros de rate limiting: {e}")


class Limiter:
    """Rate limiter simple en memoria para endpoints menos críticos"""

    def __init__(self):
        self._requests: Dict[str, list] = {}

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """
        Verifica si una clave está dentro del límite

        Args:
            key: Clave única (ej: IP + endpoint)
            max_requests: Máximo número de requests
            window_seconds: Ventana de tiempo en segundos

        Returns:
            bool: True si está permitido
        """
        current_time = datetime.now(timezone.utc)
        window_start = current_time - timedelta(seconds=window_seconds)

        # Limpiar requests antiguos
        if key in self._requests:
            self._requests[key] = [
                req_time for req_time in self._requests[key] if req_time > window_start
            ]
        else:
            self._requests[key] = []

        # Verificar límite
        if len(self._requests[key]) >= max_requests:
            return False

        # Añadir request actual
        self._requests[key].append(current_time)
        return True

    def reset(self, key: str):
        """Resetea el contador para una clave"""
        if key in self._requests:
            del self._requests[key]


# Instancia global del limiter simple
simple_limiter = Limiter()

# Instancia global del rate limiter de base de datos
db_rate_limiter = DatabaseRateLimiter()


def _retry_after_seconds(result: Dict[str, Any], fallback: int) -> int:
    """Segundos hasta que el contador deja de bloquear (mínimo 1)"""
    blocked_until = result.get("blocked_until")
    if blocked_until is None:
        return max(1, fallback)
    if blocked_until.tzinfo is None:
        blocked_until = blocked_until.replace(tzinfo=timezone.utc)
    remaining = (blocked_until - datetime.now(timezone.utc)).total_seconds()
    return max(1, math.ceil(remaining))


def _rate_limited(result: Dict[str, Any], window_seconds: int) -> HTTPException:
    """429 con Retry-After: respuesta única de todos los límites"""
    return HTTPException(
        status_code=429,
        detail=make_error(ErrorCode.RATE_LIMIT_EXCEEDED),
        headers={"Retry-After": str(_retry_after_seconds(result, window_seconds))},
    )


async def enforce_rate_limit(
    request: Request,
    max_requests: int,
    window_seconds: int,
    account: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> None:
    """
    Cuenta el request contra la regla y responde 429 con Retry-After si la supera

    Args:
        request: Request de FastAPI
        max_requests: Máximo número de requests en la ventana
        window_seconds: Ventana de tiempo en segundos
        account: Cuenta (p. ej. el email) sobre la que contar en lugar de la IP
        endpoint: Clave del contador (por defecto request.url.path)

    Raises:
        HTTPException: 429 si se supera el límite
    """
    rule = {"max_attempts": max_requests, "window_seconds": window_seconds}
    result = await db_rate_limiter.count_request(request, endpoint, rule, account)

    if not result["is_allowed"]:
        raise _rate_limited(result, window_seconds)


async def check_rate_limit_only(
    request: Request,
    max_requests: int,
    window_seconds: int,
    endpoint: Optional[str] = None,
) -> None:
    """
    Responde 429 con Retry-After si la IP ya está bloqueada, sin contar este request

    Es la mitad de entrada del límite que cuenta solo fallos (login): el request no gasta
    cupo; lo gasta record_failure cuando el intento falla.

    Args:
        request: Request de FastAPI
        max_requests: Máximo de fallos en la ventana
        window_seconds: Ventana de tiempo en segundos
        endpoint: Clave del contador (por defecto request.url.path)

    Raises:
        HTTPException: 429 si la IP está bloqueada
    """
    rule = {"max_attempts": max_requests, "window_seconds": window_seconds}
    result = await db_rate_limiter.peek_request(request, endpoint, rule)

    if not result["is_allowed"]:
        raise _rate_limited(result, window_seconds)


async def record_failure(
    request: Request,
    max_requests: int,
    window_seconds: int,
    endpoint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Anota un fallo de la IP; el que llega a `max_requests` la bloquea la ventana completa

    No responde 429: el intento que falla ya tiene su respuesta (401). El 429 llega en la
    siguiente petición, a través de check_rate_limit_only. Un acierto no llama a esta función:
    no suma ni reinicia el contador.

    Args:
        request: Request de FastAPI
        max_requests: Máximo de fallos en la ventana
        window_seconds: Ventana de tiempo en segundos
        endpoint: Clave del contador (por defecto request.url.path)

    Returns:
        dict: estado del contador tras anotar el fallo
    """
    rule = {"max_attempts": max_requests, "window_seconds": window_seconds}
    return await db_rate_limiter.count_failure(request, endpoint, rule)


# Decorador para rate limiting específico
def rate_limit(max_requests: int, window_seconds: int, use_database: bool = True):
    """
    Decorador para aplicar rate limiting a endpoints específicos

    Args:
        max_requests: Máximo número de requests
        window_seconds: Ventana de tiempo en segundos
        use_database: Si usar base de datos o memoria

    Returns:
        Decorador
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Buscar el request en los argumentos
            request = None

            # Buscar en args
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            # Si no se encuentra en args, buscar en kwargs
            if not request:
                for key, value in kwargs.items():
                    if isinstance(value, Request):
                        request = value
                        break

            # También buscar por nombre de parámetro
            if not request and "request" in kwargs:
                if isinstance(kwargs["request"], Request):
                    request = kwargs["request"]

            if not request:
                raise HTTPException(status_code=500, detail=make_error(ErrorCode.INTERNAL_ERROR))

            if use_database:
                # Usar rate limiter de base de datos, con los argumentos del decorador
                await enforce_rate_limit(request, max_requests, window_seconds)
            else:
                # Usar rate limiter simple
                client_ip = SecurityUtils.get_client_ip(request)
                key = f"{client_ip}:{request.url.path}"

                if not simple_limiter.is_allowed(key, max_requests, window_seconds):
                    raise HTTPException(
                        status_code=429,
                        detail=make_error(ErrorCode.RATE_LIMIT_EXCEEDED),
                        headers={"Retry-After": str(window_seconds)},
                    )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# Tarea de limpieza periódica
async def start_rate_limit_cleanup_task():
    """Inicia tarea de limpieza periódica de rate limiting"""
    while True:
        try:
            await db_rate_limiter.cleanup_old_records()
            # Limpiar cada 6 horas
            await asyncio.sleep(21600)
        except Exception as e:
            print(f"Error en tarea de limpieza de rate limiting: {e}")
            await asyncio.sleep(1800)  # Reintentar en 30 minutos
