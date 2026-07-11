"""
Middleware de logging de requests HTTP.

Captura método, endpoint, status code y tiempo de respuesta de cada request
y lo inserta de forma asíncrona (fire-and-forget) en api_request_logs.

Rutas excluidas: /health, /metrics, /api/admin/, /static/
"""

import asyncio
import time
from typing import Optional

from fastapi import Request

from app.database.session import get_db_session

_SKIP_PREFIXES = ("/health", "/metrics", "/api/admin/", "/static/")


async def _insert_log(
    method: str,
    endpoint: str,
    status_code: int,
    response_time_ms: int,
    user_id: Optional[str],
    error_message: Optional[str],
) -> None:
    """Tarea background que inserta el log en BD sin bloquear la respuesta."""
    try:
        from app.crud import request_log_crud

        db = next(get_db_session())
        try:
            request_log_crud.log_request_orm(
                db,
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                response_time_ms=response_time_ms,
                user_id=user_id,
                error_message=error_message,
            )
        finally:
            db.close()
    except Exception as e:
        print(f"[request_logging] Error al insertar log: {e}")


async def request_logging_middleware(request: Request, call_next):
    """
    Middleware HTTP que registra cada request en api_request_logs.

    Usa fire-and-forget (asyncio.create_task) para no añadir latencia.
    Nunca bloquea ni propaga errores propios.
    """
    path = request.url.path

    # Saltar rutas excluidas
    if any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return await call_next(request)

    start = time.perf_counter()
    status_code = 500
    error_message: Optional[str] = None
    response = None

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        error_message = str(exc)
        raise
    finally:
        response_time_ms = int((time.perf_counter() - start) * 1000)

        # Extraer user_id si el auth dependency ya lo pobló en request.state
        current_user = getattr(request.state, "current_user", None)
        user_id: Optional[str] = None
        if isinstance(current_user, dict):
            uid = current_user.get("id")
            user_id = str(uid) if uid else None

        try:
            asyncio.create_task(
                _insert_log(
                    method=request.method,
                    endpoint=path,
                    status_code=status_code,
                    response_time_ms=response_time_ms,
                    user_id=user_id,
                    error_message=error_message,
                )
            )
        except Exception as e:
            print(f"[request_logging] Error al crear tarea de log: {e}")
