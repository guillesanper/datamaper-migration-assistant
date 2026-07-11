"""
Middleware de protección CSRF para DataMap
Maneja la generación, validación y almacenamiento de tokens CSRF
"""

import asyncio
import functools
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response

from app.config.security import security_settings
from app.crud import csrf_crud
from app.database.session import get_db_session
from app.utils.error_codes import ErrorCode, make_error
from app.utils.security import SecurityUtils

# Alias para backward compatibility con tests que patchean get_db
get_db = get_db_session


class CSRFProtection:
    """Clase para manejo de protección CSRF"""

    @staticmethod
    async def generate_csrf_token(request: Request) -> str:
        """
        Genera un nuevo token CSRF y lo almacena en la base de datos

        Args:
            request: Request de FastAPI

        Returns:
            str: Token CSRF generado
        """
        client_ip = SecurityUtils.get_client_ip(request)
        hashed_ip = SecurityUtils.hash_ip_address(client_ip)

        # Obtener session_id de las cookies si existe
        session_id = None
        session_cookie = request.cookies.get("session")
        if session_cookie:
            # Extraer el ID de sesión (asumiendo que está firmado)
            try:
                # Aquí deberías usar tu función de verificación de cookies
                # Por ahora usamos el valor directo
                session_id = session_cookie[:32]  # Truncar para usar como ID
            except Exception:
                pass

        # Calcular expiración en minutos desde la configuración (segundos -> minutos)
        expires_in_minutes = security_settings.CSRF_TOKEN_EXPIRY // 60

        # Generar token usando SecurityUtils (esto permite que los tests lo mockeen)
        token = SecurityUtils.generate_csrf_token()

        try:
            # Obtener sesión de SQLAlchemy (usando get_db para compatibilidad con tests)
            db = next(get_db())
            try:
                # Almacenar token en DB usando CRUD ORM
                token_data = csrf_crud.generate_token_orm(
                    db,
                    session_id=session_id or "",  # CRUD espera str, pasar "" si None
                    ip_address=hashed_ip,
                    expires_in_minutes=expires_in_minutes,
                    token=token,  # Pasar el token ya generado
                )

                return token

            finally:
                db.close()

        except Exception as e:
            print(f"Error almacenando token CSRF en DB: {e}")
            # Fail-open: devolver el token aunque no se haya guardado en DB
            # Esto evita bloquear la aplicación si la DB falla
            return token

    @staticmethod
    async def validate_csrf_token(request: Request, token: str) -> bool:
        """
        Valida un token CSRF

        Args:
            request: Request de FastAPI
            token: Token a validar

        Returns:
            bool: True si el token es válido
        """
        if not token:
            return False

        client_ip = SecurityUtils.get_client_ip(request)
        hashed_ip = SecurityUtils.hash_ip_address(client_ip)

        # Obtener session_id de las cookies si existe
        session_id = None
        session_cookie = request.cookies.get("session")
        if session_cookie:
            try:
                session_id = session_cookie[:32]
            except Exception:
                pass

        try:
            # Obtener sesión de SQLAlchemy (usando get_db para compatibilidad con tests)
            db = next(get_db())
            try:
                # Validar token usando CRUD ORM
                # El CRUD valida: existencia, no expirado, no usado, y marca como usado
                # Opcionalmente valida session_id e ip_address
                is_valid = csrf_crud.validate_token_orm(
                    db,
                    token=token,
                    session_id=session_id,  # Validación opcional de sesión
                    ip_address=hashed_ip,  # Validación opcional de IP
                )

                return is_valid

            finally:
                db.close()

        except Exception as e:
            print(f"Error validando token CSRF: {e}")
            # Fail-closed para validación: si DB falla, rechazar token
            # Esto es más seguro que fail-open en validación
            return False

    @staticmethod
    async def cleanup_expired_tokens(hours_old: int = 24):
        """
        Limpia tokens CSRF expirados y usados antiguos

        Args:
            hours_old: Horas de antigüedad para considerar tokens eliminables (default 24)
        """
        try:
            # Obtener sesión de SQLAlchemy (usando get_db para compatibilidad con tests)
            db = next(get_db())
            try:
                # Limpiar tokens usando CRUD ORM
                deleted_count = csrf_crud.cleanup_orm(db, hours_old=hours_old)

                if deleted_count > 0:
                    print(f"Limpiados {deleted_count} tokens CSRF antiguos (>{hours_old} horas)")

            finally:
                db.close()

        except Exception as e:
            print(f"Error limpiando tokens CSRF: {e}")


async def csrf_middleware(request: Request, call_next):
    """
    Middleware para protección CSRF

    Args:
        request: Request de FastAPI
        call_next: Siguiente middleware/handler

    Returns:
        Response: Respuesta procesada
    """
    # Verificar si el endpoint requiere protección CSRF
    path = request.url.path
    method = request.method

    print(f"🔒 CSRF Middleware - Path: {path}, Method: {method}")

    if not security_settings.is_csrf_protected_endpoint(path, method):
        # No requiere protección, continuar
        print(f"✅ CSRF - Endpoint {path} no requiere protección")
        response = await call_next(request)
        return response

    # Verificar token CSRF para métodos protegidos
    if method in security_settings.CSRF_PROTECTED_METHODS:
        print(f"🔒 CSRF - Método {method} requiere protección CSRF")
        csrf_token = None

        # Intentar obtener token del formulario
        content_type = request.headers.get("content-type", "")
        print(f"🔒 CSRF - Content-Type: {content_type}")

        if content_type.startswith("application/x-www-form-urlencoded"):
            try:
                form_data = await request.form()
                csrf_token = form_data.get("csrf_token")
                print(
                    f"🔒 CSRF - Token del formulario: {str(csrf_token)[:20] if csrf_token else 'None'}..."
                )
            except Exception as e:
                print(f"❌ CSRF - Error obteniendo formulario: {e}")
                pass

        # Intentar obtener token del header
        if not csrf_token:
            csrf_token = request.headers.get("X-CSRF-Token")
            print(f"🔒 CSRF - Token del header: {csrf_token[:20] if csrf_token else 'None'}...")

        # Validar token
        if not csrf_token:
            print("❌ CSRF - No se encontró token CSRF")
            raise HTTPException(status_code=403, detail=make_error(ErrorCode.CSRF_TOKEN_INVALID))

        token_valid = await CSRFProtection.validate_csrf_token(request, str(csrf_token))
        print(f"🔒 CSRF - Token válido: {token_valid}")

        if not token_valid:
            print("❌ CSRF - Token CSRF inválido")
            raise HTTPException(status_code=403, detail=make_error(ErrorCode.CSRF_TOKEN_INVALID))

    # Procesar request
    response = await call_next(request)

    return response


# Función auxiliar para templates
async def get_csrf_token_for_template(request: Request) -> str:
    """
    Función auxiliar para obtener token CSRF en templates

    Args:
        request: Request de FastAPI

    Returns:
        str: Token CSRF
    """
    return await CSRFProtection.generate_csrf_token(request)


# Decorador para endpoints que necesitan CSRF
def csrf_protect(func):
    """
    Decorador para proteger endpoints específicos con CSRF

    Args:
        func: Función del endpoint

    Returns:
        Función decorada
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Buscar el request en los argumentos y kwargs
        request = None

        # Buscar en args
        for arg in args:
            if isinstance(arg, Request):
                request = arg
                break

        # Buscar en kwargs si no se encontró en args
        if not request:
            for key, value in kwargs.items():
                if isinstance(value, Request):
                    request = value
                    break

        # Si aún no se encuentra, buscar por nombre de parámetro
        if not request and "request" in kwargs:
            request = kwargs["request"]

        if not request:
            # En lugar de fallar, simplemente ejecutar la función sin validación CSRF
            # Esto permite que el middleware principal maneje la protección CSRF
            return await func(*args, **kwargs)

        # El middleware principal ya maneja la protección CSRF,
        # así que simplemente ejecutamos la función
        return await func(*args, **kwargs)

    return wrapper


# Tarea de limpieza periódica
async def start_csrf_cleanup_task():
    """Inicia tarea de limpieza periódica de tokens CSRF"""
    while True:
        try:
            await CSRFProtection.cleanup_expired_tokens()
            # Limpiar cada hora
            await asyncio.sleep(3600)
        except Exception as e:
            print(f"Error en tarea de limpieza CSRF: {e}")
            await asyncio.sleep(300)  # Reintentar en 5 minutos
