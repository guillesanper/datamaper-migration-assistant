"""
Middleware de headers de seguridad para DataMap
Añade headers de seguridad importantes a todas las respuestas
"""

from typing import Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.security import security_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware que añade headers de seguridad a todas las respuestas
    """

    def __init__(self, app, add_hsts: bool = True):
        super().__init__(app)
        self.add_hsts = add_hsts

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Procesa la request y añade headers de seguridad a la response

        Args:
            request: Request entrante
            call_next: Siguiente middleware/handler

        Returns:
            Response: Response con headers de seguridad añadidos
        """
        # Procesar la request
        response = await call_next(request)

        # Obtener headers de seguridad de la configuración
        security_headers = security_settings.get_security_headers()

        # Añadir headers de seguridad
        for header_name, header_value in security_headers.items():
            if header_value:  # Solo añadir si el valor no está vacío
                response.headers[header_name] = header_value

        # HSTS solo en HTTPS (en producción)
        if self.add_hsts and request.url.scheme == "https":
            if security_headers.get("Strict-Transport-Security"):
                response.headers["Strict-Transport-Security"] = security_headers[
                    "Strict-Transport-Security"
                ]

        # Headers adicionales específicos por tipo de contenido
        content_type = response.headers.get("content-type", "")

        # Para respuestas HTML
        if "text/html" in content_type:
            # Prevenir MIME type sniffing
            response.headers["X-Content-Type-Options"] = "nosniff"

            # Prevenir clickjacking
            if "X-Frame-Options" not in response.headers:
                response.headers["X-Frame-Options"] = "DENY"

        # Para respuestas JSON/API
        elif "application/json" in content_type:
            # Prevenir MIME type sniffing
            response.headers["X-Content-Type-Options"] = "nosniff"

            # Cache control para APIs
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        # Headers de privacidad
        response.headers["Referrer-Policy"] = security_headers.get(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )

        # Permissions Policy (reemplaza Feature-Policy)
        permissions_policy = self._get_permissions_policy()
        if permissions_policy:
            response.headers["Permissions-Policy"] = permissions_policy

        return response  # type: ignore[no-any-return]

    def _get_permissions_policy(self) -> str:
        """
        Genera la Permissions Policy para controlar características del navegador

        Returns:
            str: Valor de la Permissions Policy
        """
        # Política restrictiva por defecto - solo características ampliamente soportadas
        policies = [
            "geolocation=()",  # Bloquear geolocalización
            "microphone=()",  # Bloquear micrófono
            "camera=()",  # Bloquear cámara
            "payment=()",  # Bloquear API de pagos
            "usb=()",  # Bloquear USB
            "magnetometer=()",  # Bloquear magnetómetro
            "gyroscope=()",  # Bloquear giroscopio
            "accelerometer=()",  # Bloquear acelerómetro
            "autoplay=()",  # Bloquear autoplay
            "encrypted-media=()",  # Bloquear media encriptado
            "fullscreen=(self)",  # Permitir fullscreen solo en mismo origen
            "picture-in-picture=()",  # Bloquear picture-in-picture
        ]

        return ", ".join(policies)


class CSPMiddleware(BaseHTTPMiddleware):
    """
    Middleware específico para Content Security Policy
    Permite configuración más granular de CSP
    """

    def __init__(self, app, csp_policy: Optional[str] = None):
        super().__init__(app)
        self.csp_policy = csp_policy or self._get_default_csp()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Añade Content Security Policy a las respuestas HTML

        Args:
            request: Request entrante
            call_next: Siguiente middleware/handler

        Returns:
            Response: Response con CSP añadido
        """
        response = await call_next(request)

        # Solo añadir CSP a respuestas HTML
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Content-Security-Policy"] = self.csp_policy

        return response  # type: ignore[no-any-return]

    def _get_default_csp(self) -> str:
        """
        Genera una Content Security Policy por defecto

        Returns:
            str: Política CSP por defecto
        """
        # CSP restrictiva pero funcional para la aplicación
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://js.stripe.com",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net",
            "img-src 'self' data: https:",
            "connect-src 'self' https://api.stripe.com https://cdn.jsdelivr.net",
            "frame-src https://js.stripe.com https://hooks.stripe.com",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "upgrade-insecure-requests",
        ]

        return "; ".join(csp_directives)


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware combinado de seguridad que incluye múltiples protecciones
    """

    def __init__(self, app, enable_csp: bool = True, enable_hsts: bool = True):
        super().__init__(app)
        self.enable_csp = enable_csp
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Aplica múltiples medidas de seguridad

        Args:
            request: Request entrante
            call_next: Siguiente middleware/handler

        Returns:
            Response: Response con todas las medidas de seguridad aplicadas
        """
        # Verificar si la IP está en lista negra (si se implementa)
        client_ip = self._get_client_ip(request)
        if await self._is_ip_blocked(client_ip):
            return JSONResponse(status_code=403, content={"error": "Access denied"})

        # Procesar request
        response = await call_next(request)

        # Aplicar headers de seguridad básicos
        security_headers = security_settings.get_security_headers()
        for header_name, header_value in security_headers.items():
            if header_value:
                response.headers[header_name] = header_value

        # Aplicar CSP si está habilitado
        if self.enable_csp:
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                csp_policy = security_settings.CONTENT_SECURITY_POLICY
                if csp_policy:
                    response.headers["Content-Security-Policy"] = csp_policy

        # Aplicar HSTS si está habilitado y es HTTPS
        if self.enable_hsts and request.url.scheme == "https":
            hsts_header = security_settings.STRICT_TRANSPORT_SECURITY
            if hsts_header:
                response.headers["Strict-Transport-Security"] = hsts_header

        # Headers adicionales de seguridad
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = security_settings.X_FRAME_OPTIONS
        response.headers["X-XSS-Protection"] = security_settings.X_XSS_PROTECTION
        response.headers["Referrer-Policy"] = security_settings.REFERRER_POLICY

        # Remover headers que revelan información del servidor
        if "Server" in response.headers:
            del response.headers["Server"]
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]

        return response  # type: ignore[no-any-return]

    def _get_client_ip(self, request: Request) -> str:
        """
        Obtiene la IP del cliente considerando proxies

        Args:
            request: Request de FastAPI

        Returns:
            str: IP del cliente
        """
        # Verificar headers de proxy en orden de prioridad
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Tomar la primera IP (cliente original)
            return str(forwarded_for.split(",")[0].strip())

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return str(real_ip)

        # Fallback a la IP de conexión directa
        return str(request.client.host) if request.client else "unknown"

    async def _is_ip_blocked(self, ip: str) -> bool:
        """
        Verifica si una IP está bloqueada

        Args:
            ip: IP a verificar

        Returns:
            bool: True si está bloqueada
        """
        # Implementar lógica de lista negra si es necesario
        # Por ahora, no bloqueamos ninguna IP
        return False


# Funciones de utilidad para configurar middlewares
def setup_security_middlewares(app, enable_csp: bool = True, enable_hsts: bool = True):
    """
    Configura todos los middlewares de seguridad en la aplicación

    Args:
        app: Instancia de FastAPI
        enable_csp: Habilitar Content Security Policy
        enable_hsts: Habilitar HTTP Strict Transport Security
    """
    # Middleware principal de seguridad
    app.add_middleware(SecurityMiddleware, enable_csp=enable_csp, enable_hsts=enable_hsts)

    # Middleware específico de headers de seguridad
    app.add_middleware(SecurityHeadersMiddleware, add_hsts=enable_hsts)


def get_security_headers_dict() -> dict:
    """
    Obtiene un diccionario con todos los headers de seguridad configurados

    Returns:
        dict: Headers de seguridad
    """
    return security_settings.get_security_headers()


# Decorador para endpoints que necesitan headers específicos
def add_security_headers(additional_headers: Optional[dict] = None):
    """
    Decorador para añadir headers de seguridad específicos a endpoints

    Args:
        additional_headers: Headers adicionales a añadir

    Returns:
        function: Decorador
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            response = await func(*args, **kwargs)

            # Si la respuesta no es un objeto Response, convertirla
            if not hasattr(response, "headers"):
                if isinstance(response, dict):
                    response = JSONResponse(content=response)
                else:
                    return response

            # Añadir headers adicionales
            if additional_headers:
                for header_name, header_value in additional_headers.items():
                    response.headers[header_name] = header_value

            return response

        return wrapper

    return decorator
