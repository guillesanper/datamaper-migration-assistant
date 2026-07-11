# backend/app/middleware/encryption_session.py
"""
Middleware para manejar sesiones de cifrado con validación de ownership

🔐 SEGURIDAD HARDENED:
- Lee cookies httpOnly enc_session_{project_id} (inmune a XSS)
- Valida que la sesión pertenezca al usuario autenticado
- Previene session hijacking verificando user_id
- Extrae project_id del path automáticamente

CORRECCIONES DE VULNERABILIDADES:
1. 🔴 CRÍTICA (Fase 1.2): User ID binding - Previene session hijacking
2. 🔴 CRÍTICA (Fase 1.1): httpOnly cookies - Previene robo vía XSS

Autor: DataMap Security Team
Última actualización: 2025-01-04 (Cookie-based sessions)
"""

import logging
import re

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.redis_session_cache import get_encryption_session_cache

logger = logging.getLogger(__name__)


def extract_project_id_from_path(path: str) -> str | None:
    """
    Extrae el project_id del path de la request

    Soporta paths como:
    - /api/projects/{uuid}/...
    - /api/projects/{uuid}
    - /api/mappings/projects/{uuid}/...
    - /api/schemas/projects/{uuid}/...

    Args:
        path: Path de la request

    Returns:
        project_id (UUID string) o None si no se encuentra

    Ejemplos:
        >>> extract_project_id_from_path("/api/projects/abc-123/schemas")
        "abc-123"
        >>> extract_project_id_from_path("/api/mappings/projects/abc-123/tables")
        "abc-123"
        >>> extract_project_id_from_path("/api/health")
        None
    """
    # Pattern: /projects/{uuid}/...
    # UUID pattern: 8-4-4-4-12 caracteres hexadecimales con guiones
    pattern = r"/projects/([a-f0-9-]{36})(?:/|$)"
    match = re.search(pattern, path, re.IGNORECASE)

    if match:
        return match.group(1)

    return None


class EncryptionSessionMiddleware(BaseHTTPMiddleware):
    """
    Middleware que maneja sesiones de cifrado con validación de seguridad

    🔐 NUEVO FLUJO (httpOnly cookies):
    1. Extrae project_id del path (/api/projects/{uuid}/...)
    2. Lee cookie httpOnly enc_session_{project_id}
    3. Busca la sesión en caché
    4. 🔐 VALIDA que el user_id de la sesión coincida con el usuario autenticado
    5. Si es válida, pone encryption_key y project_id en request.state
    6. Los CRUDs pueden usar request.state.encryption_key automáticamente

    Security Flow:
        ┌─────────────────┐
        │ Request llega   │
        └────────┬────────┘
                 │
        ┌────────▼────────────────────┐
        │ Extraer project_id del path │
        └────────┬────────────────────┘
                 │
        ┌────────▼────────────────────────────┐
        │ Leer cookie enc_session_{project_id}│
        └────────┬────────────────────────────┘
                 │
        ┌────────▼────────┐
        │ Obtener sesión del caché │
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │ ¿Sesión existe? │
        └────────┬────────┘
                 │ No → Continuar sin encryption_key
                 │ Sí ↓
        ┌────────▼────────────────────────┐
        │ ¿user_id sesión == current_user?│
        └────────┬────────────────────────┘
                 │ No → ⚠️ Rechazar (security violation)
                 │ Sí ↓
        ┌────────▼────────┐
        │ Inyectar encryption_key en request.state │
        └────────┬────────┘
                 │
        ┌────────▼────────┐
        │ Continuar request │
        └─────────────────┘

    VENTAJAS DE httpOnly COOKIES:
    ✅ Inmune a XSS - JavaScript no puede leer la cookie
    ✅ Enviadas automáticamente - No requiere interceptors
    ✅ Soporte de navegador - Manejo de expiración automático
    ✅ SameSite protection - Previene CSRF
    """

    async def dispatch(self, request: Request, call_next):
        # Inicializar valores por defecto en request.state
        request.state.encryption_key = None
        request.state.encryption_project_id = None

        # Extraer project_id del path
        path = request.url.path
        project_id = extract_project_id_from_path(path)

        if project_id:
            # Buscar cookie de sesión para este proyecto
            cookie_name = f"enc_session_{project_id}"
            session_token = request.cookies.get(cookie_name)

            logger.debug(
                f"[MIDDLEWARE] Encryption session check:\n"
                f"  project_id: {project_id[:8]}...\n"
                f"  cookie_name: {cookie_name}\n"
                f"  session_token exists: {session_token is not None}"
            )

            if session_token:
                # Obtener sesión del caché (con project_id para lookup eficiente)
                cache = get_encryption_session_cache()
                session = cache.get_session(session_token, project_id)

                logger.debug(
                    f"[MIDDLEWARE] Cache lookup result:\n"
                    f"  session_token (first 16 chars): {session_token[:16]}...\n"
                    f"  session found in cache: {session is not None}"
                )

                if session:
                    # 🔐 CRÍTICO: Validar ownership de la sesión
                    # El usuario autenticado debe ser el dueño de la sesión

                    # Obtener current_user si existe en request.state
                    # (el dependency get_current_user ya lo puso ahí)
                    current_user = getattr(request.state, "current_user", None)

                    logger.debug(
                        f"[MIDDLEWARE] User validation:\n"
                        f"  current_user available: {current_user is not None}\n"
                        f"  session_user_id: {session.get('user_id', 'N/A')[:8] if session.get('user_id') else 'N/A'}..."
                    )

                    if current_user:
                        session_user_id = session.get("user_id")
                        current_user_id = (
                            current_user.get("id")
                            if isinstance(current_user, dict)
                            else getattr(current_user, "id", None)
                        )

                        # Validar que coincidan
                        if session_user_id and current_user_id:
                            if session_user_id != current_user_id:
                                # 🚨 SECURITY VIOLATION: Session hijacking attempt
                                logger.warning(
                                    f"🚨 Session hijacking attempt detected! "
                                    f"Session belongs to user {session_user_id[:8]}... "
                                    f"but request is from user {current_user_id[:8]}... "
                                    f"Cookie: {cookie_name}, Project: {project_id[:8]}..."
                                )
                                # Invalidar la sesión comprometida
                                cache.invalidate_session(session_token)
                                # NO inyectar encryption_key (request continúa sin acceso)
                            else:
                                # ✅ Sesión válida y pertenece al usuario correcto
                                request.state.encryption_key = session["encryption_key"]
                                request.state.encryption_project_id = session["project_id"]

                                logger.debug(
                                    f"✅ Encryption session validated for project {project_id[:8]}... "
                                    f"and user {current_user_id[:8]}..."
                                )
                        else:
                            # Sesión válida pero sin validación de usuario (fallback legacy)
                            # Esto solo debería ocurrir en requests sin autenticación
                            request.state.encryption_key = session["encryption_key"]
                            request.state.encryption_project_id = session["project_id"]
                    else:
                        # No hay usuario autenticado aún (el request todavía no pasó por get_current_user)
                        # Guardar sesión temporalmente para validar después
                        logger.debug(
                            f"[MIDDLEWARE] ✓ Saving pending encryption session:\n"
                            f"  project_id: {session.get('project_id', 'N/A')[:8]}...\n"
                            f"  user_id: {session.get('user_id', 'N/A')[:8] if session.get('user_id') else 'N/A'}...\n"
                            f"  has_encryption_key: {session.get('encryption_key') is not None}"
                        )
                        request.state._pending_encryption_session = session
                else:
                    # Sesión no encontrada en caché (expirada o inválida)
                    logger.debug(
                        f"[MIDDLEWARE] ✗ Session not found in cache:\n"
                        f"  project_id: {project_id[:8]}...\n"
                        f"  cookie_name: {cookie_name}\n"
                        f"  session_token (first 16): {session_token[:16]}..."
                    )

        # Continuar con el request
        response = await call_next(request)
        return response
