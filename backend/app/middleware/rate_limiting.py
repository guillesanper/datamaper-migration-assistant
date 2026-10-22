"""
Middleware de Rate Limiting para DataMap
Implementa control de límites de requests por IP y endpoint usando base de datos
"""

import asyncio
import functools
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.config.security import security_settings
from app.database.session import get_db_session
from app.utils.error_codes import ErrorCode, make_error
from app.utils.security import SecurityUtils

get_db = get_db_session  # Alias para backward compatibility con tests
from app.crud import rate_limit_crud


class DatabaseRateLimiter:
    """Rate limiter que usa base de datos para persistencia"""

    @staticmethod
    async def check_rate_limit(request: Request, endpoint: Optional[str] = None) -> bool:
        """
        Verifica si el request está dentro de los límites permitidos

        Args:
            request: Request de FastAPI
            endpoint: Endpoint específico (si no se proporciona, se usa request.url.path)

        Returns:
            bool: True si está dentro del límite, False si excede
        """
        if endpoint is None:
            endpoint = request.url.path

        client_ip = SecurityUtils.get_client_ip(request)
        hashed_ip = SecurityUtils.hash_ip_address(client_ip)

        # Obtener configuración para este endpoint
        config = security_settings.get_rate_limit_config(endpoint)
        max_attempts = config["max_attempts"]
        window_seconds = config["window_seconds"]
        block_duration = config.get("block_duration", window_seconds)

        # Convertir segundos a minutos para el CRUD
        window_minutes = window_seconds // 60
        block_duration_minutes = block_duration // 60

        try:
            # Obtener sesión de SQLAlchemy
            db = next(get_db_session())
            try:
                # Verificar límite usando CRUD ORM
                # check_limit_orm hace TODO: verifica bloqueo, crea/actualiza registro,
                # incrementa contador, resetea ventana si expiró, bloquea si excede límite
                result = rate_limit_crud.check_limit_orm(
                    db,
                    identifier=hashed_ip,  # Usar IP como identificador
                    ip_address=hashed_ip,
                    endpoint=endpoint,
                    max_requests=max_attempts,
                    window_minutes=window_minutes,
                    block_duration_minutes=block_duration_minutes,
                )

                # Retornar si está permitido
                return bool(result["is_allowed"])

            finally:
                db.close()

        except Exception as e:
            print(f"Error en rate limiting: {e}")
            # Fail-open: permitir request si DB falla (evita bloquear tráfico legítimo)
            return True

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
        # Los endpoints síncronos se ejecutan en el threadpool: proteger el dict compartido
        self._lock = threading.Lock()

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
        with self._lock:
            return self._is_allowed_locked(key, max_requests, window_seconds)

    def _is_allowed_locked(self, key: str, max_requests: int, window_seconds: int) -> bool:
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


async def rate_limit_middleware(request: Request, call_next):
    """
    Middleware de rate limiting

    Args:
        request: Request de FastAPI
        call_next: Siguiente middleware/handler

    Returns:
        Response: Respuesta procesada
    """
    endpoint = security_settings.normalize_rate_limit_path(request.url.path)
    limited = security_settings.is_rate_limited_endpoint(endpoint)

    # Verificar si el endpoint tiene configuración de rate limiting
    if limited and not await db_rate_limiter.check_rate_limit(request, endpoint):
        # Obtener información para el mensaje de error
        info = await db_rate_limiter.get_rate_limit_info(request, endpoint)

        # JSONResponse y no HTTPException: lanzada desde un middleware HTTP, Starlette
        # la convierte en un 500 en lugar del 429
        if info["blocked_until"]:
            remaining_time = int(
                (info["blocked_until"] - datetime.now(timezone.utc)).total_seconds()
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": make_error(ErrorCode.RATE_LIMIT_BLOCKED, seconds=remaining_time)
                },
                headers={"Retry-After": str(remaining_time)},
            )
        return JSONResponse(
            status_code=429,
            content={"detail": make_error(ErrorCode.RATE_LIMIT_EXCEEDED)},
            headers={"Retry-After": "900"},  # 15 minutos por defecto
        )

    # Procesar request
    response = await call_next(request)

    # Añadir headers informativos de rate limiting
    if limited:
        info = await db_rate_limiter.get_rate_limit_info(request, endpoint)
        response.headers["X-RateLimit-Limit"] = str(info["max_attempts"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining_attempts"])
        response.headers["X-RateLimit-Window"] = str(info["window_seconds"])

    return response


def _find_request(args, kwargs) -> Optional[Request]:
    """Busca el Request entre los argumentos posicionales y con nombre del endpoint."""
    for value in list(args) + list(kwargs.values()):
        if isinstance(value, Request):
            return value
    return None


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
            request = _find_request(args, kwargs)
            if not request:
                raise HTTPException(status_code=500, detail=make_error(ErrorCode.INTERNAL_ERROR))

            if use_database:
                # Los endpoints de RATE_LIMITS ya los limita el middleware: contarlos aquí
                # otra vez dividiría el límite efectivo entre dos
                if security_settings.is_rate_limited_endpoint(request.url.path):
                    return await func(*args, **kwargs)
                # Usar rate limiter de base de datos
                if not await db_rate_limiter.check_rate_limit(request):
                    raise HTTPException(status_code=429, detail=make_error(ErrorCode.RATE_LIMIT_EXCEEDED))
            else:
                # Usar rate limiter simple
                client_ip = SecurityUtils.get_client_ip(request)
                key = f"{client_ip}:{request.url.path}"

                if not simple_limiter.is_allowed(key, max_requests, window_seconds):
                    raise HTTPException(status_code=429, detail=make_error(ErrorCode.RATE_LIMIT_EXCEEDED))

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
