"""
Encryption Router
Endpoints para gestión de cifrado de proyectos

Endpoints:
- POST /api/projects/{project_id}/encryption/setup - Configurar cifrado
- POST /api/projects/{project_id}/encryption/verify - Verificar passphrase
- POST /api/projects/{project_id}/encryption/rotate-key - Rotar master key
- GET /api/projects/{project_id}/encryption/stats - Estadísticas de cifrado
- POST /api/projects/{project_id}/encryption/enable - Habilitar cifrado
- POST /api/projects/{project_id}/encryption/disable - Deshabilitar cifrado

Autor: DataMap Security Team
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.database.session import get_db_session
from app.routers.dependencies import get_current_user
from app.services.encryption_service import EncryptionService
from app.utils.exception_sanitizer import internal_server_error
from app.utils.security_logger import log_security_event

router = APIRouter(prefix="/api/projects", tags=["encryption"])
logger = logging.getLogger(__name__)


# ==================== Schemas de Request ====================


class SetupEncryptionRequest(BaseModel):
    """Schema para configurar cifrado en un proyecto"""

    passphrase: str = Field(
        ...,
        min_length=12,
        description="Passphrase para cifrado (mínimo 12 caracteres, debe contener mayúsculas, minúsculas y números)",
    )


class VerifyPassphraseRequest(BaseModel):
    """Schema para verificar passphrase"""

    passphrase: str = Field(..., min_length=1)


class RotateKeyRequest(BaseModel):
    """Schema para rotar master key"""

    old_passphrase: str = Field(..., min_length=1, description="Passphrase actual")
    new_passphrase: str = Field(
        ..., min_length=12, description="Nueva passphrase (mínimo 12 caracteres)"
    )


class EnableEncryptionRequest(BaseModel):
    """Schema para habilitar cifrado"""

    passphrase: str = Field(..., min_length=1)


class DisableEncryptionRequest(BaseModel):
    """Schema para deshabilitar cifrado"""

    confirm_passphrase: str = Field(..., min_length=1)


# ==================== Response Schemas ====================


class EncryptionStatusResponse(BaseModel):
    """Response para status de cifrado"""

    project_id: str
    encryption_enabled: bool
    has_encryption_config: bool
    created_at: Optional[str] = None


class EncryptionStatsResponse(BaseModel):
    """Response para estadísticas de cifrado"""

    tables_total: int
    tables_encrypted: int
    columns_total: int
    columns_encrypted: int
    mappings_total: int
    mappings_encrypted: int
    versions_total: int
    versions_encrypted: int
    comments_total: int
    comments_encrypted: int
    encryption_percentage: float


# ==================== Endpoints ====================


@router.post("/{project_id}/encryption/setup")
async def setup_project_encryption(
    project_id: str,
    request_data: SetupEncryptionRequest,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Configura cifrado AES-256-GCM + Argon2id para un proyecto

    Este endpoint:
    - Crea la configuración de cifrado
    - Genera salts únicos
    - Deriva y almacena el hash de master key (one-way)
    - CIFRA AUTOMÁTICAMENTE todos los datos existentes (tablas, columnas)

    Requisitos:
    - Usuario debe ser owner o editor del proyecto
    - Passphrase debe cumplir requisitos de seguridad

    IMPORTANTE: Guarda la passphrase en un lugar seguro.
    Sin ella, los datos cifrados son IRRECUPERABLES.
    """
    try:
        result = EncryptionService.setup_project_encryption(
            db, project_id, request_data.passphrase, current_user["id"]
        )

        # Log security event
        await log_security_event(
            request=request,
            event_type="encryption_setup",
            user_id=current_user["id"],
            details={"project_id": project_id, "action": "setup_encryption"},
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error configurando cifrado") from e


@router.post("/{project_id}/encryption/verify")
async def verify_passphrase(
    project_id: str,
    request_data: VerifyPassphraseRequest,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Verifica passphrase y crea sesión de cifrado

    🔐 SEGURIDAD HARDENED:
    - Rate limiting: Máximo 5 intentos fallidos cada 10 minutos
    - Lockout: 15 minutos después de exceder límite
    - httpOnly cookies: Session token NUNCA accesible desde JavaScript (previene XSS)
    - User ID binding: Sesión vinculada al usuario autenticado (previene session hijacking)
    - SameSite=Strict: Previene CSRF

    Este endpoint:
    1. 🔐 Verifica rate limiting (previene fuerza bruta)
    2. Verifica la passphrase del proyecto
    3. Si es válida, deriva la encryption key
    4. Crea una sesión temporal (1-3 horas) vinculada al user_id
    5. 🔐 NUEVO: Establece cookie httpOnly con el session token
    6. Retorna solo confirmación de éxito (token no expuesto en JSON)

    Cookie establecida:
    - Nombre: enc_session_{project_id}
    - HttpOnly: True (no accesible desde JS)
    - Secure: True en producción
    - SameSite: Strict (máxima protección CSRF)
    - Max-Age: timeout_seconds

    Útil para:
    - Desbloquear proyecto en UI (modal)
    - Validar antes de operaciones críticas
    - Crear sesión de cifrado temporal

    Returns:
        {
            "valid": true/false,
            "expires_in_seconds": 3600 (solo si valid=true)
        }

    Raises:
        HTTPException 429: Demasiados intentos fallidos (rate limit exceeded)

    VULNERABILIDAD CORREGIDA: 🔴 CRÍTICA
    - Antes: Session token en localStorage (vulnerable a XSS)
    - Ahora: Session token en httpOnly cookie (inmune a XSS)
    - Referencia: Auditoría de Seguridad 2025-01-03, Fase 1.1
    """
    import logging

    from app.utils.rate_limiter import create_rate_limit_key, get_passphrase_rate_limiter
    from app.utils.redis_session_cache import get_encryption_session_cache

    logger = logging.getLogger(__name__)

    # 🔐 SEGURIDAD: Rate limiting para prevenir fuerza bruta
    rate_limiter = get_passphrase_rate_limiter()
    rate_limit_key = create_rate_limit_key(current_user["id"], project_id)

    # Verificar si está bloqueado
    locked, remaining_seconds = rate_limiter.is_locked(rate_limit_key)
    if locked:
        # Log del intento durante lockout
        await log_security_event(
            request=request,
            event_type="passphrase_verification_blocked",
            user_id=current_user["id"],
            details={
                "project_id": project_id,
                "reason": "rate_limit_exceeded",
                "retry_after_seconds": remaining_seconds,
            },
            severity="warning",
        )

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Too many failed attempts",
                "message": f"Demasiados intentos fallidos. Reintenta en {remaining_seconds} segundos.",
                "retry_after_seconds": remaining_seconds,
                "locked_until": (
                    datetime.now() + timedelta(seconds=remaining_seconds or 0)
                ).isoformat(),
            },
        )

    # Verificar passphrase
    is_valid = EncryptionService.verify_project_passphrase(db, project_id, request_data.passphrase)

    # 🔐 Registrar intento en rate limiter
    rate_limit_result = rate_limiter.record_attempt(rate_limit_key, success=is_valid)

    # Log attempt (sin incluir la passphrase por seguridad)
    await log_security_event(
        request=request,
        event_type="passphrase_verification",
        user_id=current_user["id"],
        details={
            "project_id": project_id,
            "valid": is_valid,
            "remaining_attempts": rate_limit_result.get("remaining_attempts", 0),
        },
        severity="warning" if not is_valid else "info",
    )

    # Si falló y ahora está bloqueado, informar al usuario
    if not is_valid and rate_limit_result.get("locked"):
        retry_after = rate_limit_result.get("retry_after", 900)

        await log_security_event(
            request=request,
            event_type="passphrase_verification_locked",
            user_id=current_user["id"],
            details={
                "project_id": project_id,
                "reason": "max_attempts_exceeded",
                "retry_after_seconds": retry_after,
            },
            severity="error",
        )

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Too many failed attempts",
                "message": f"Demasiados intentos fallidos. Tu cuenta ha sido bloqueada temporalmente. Reintenta en {retry_after} segundos.",
                "retry_after_seconds": retry_after,
                "max_attempts": rate_limiter.max_attempts,
            },
        )

    # Si la passphrase no es válida (pero aún hay intentos disponibles)
    if not is_valid:
        remaining = rate_limit_result.get("remaining_attempts", 0)
        return {
            "valid": False,
            "remaining_attempts": remaining,
            "message": f"Passphrase incorrecta. Te quedan {remaining} intentos antes de bloqueo temporal.",
        }

    # Passphrase válida - Derivar encryption key y crear sesión
    encryption_key = EncryptionService.get_encryption_key(db, project_id, request_data.passphrase)

    if not encryption_key:
        return {"valid": False}

    # Crear sesión en caché (con user_id binding para prevenir session hijacking)
    cache = get_encryption_session_cache()
    cookie_name = f"enc_session_{project_id}"
    old_session_token = request.cookies.get(cookie_name)

    if old_session_token:
        # Invalidar sesión antigua (si existe en caché)
        cache.invalidate_session(old_session_token)
        logger.info(
            f"[VERIFY_PASSPHRASE] 🔄 Invalidated old session:\n"
            f"  old_token (first 16): {old_session_token[:16]}...\n"
            f"  reason: creating_new_session"
        )

    timeout_seconds = int(
        os.getenv("ENCRYPTION_SESSION_TIMEOUT", "3600")
    )  # 1 hora (default hardened)

    # 🔍 DEBUG: Log de creación de sesión

    logger.info(
        f"[VERIFY_PASSPHRASE] Creating encryption session:\n"
        f"  project_id: {project_id[:8]}...\n"
        f"  user_id: {current_user['id'][:8]}...\n"
        f"  timeout_seconds: {timeout_seconds}\n"
        f"  timeout_env_var: {os.getenv('ENCRYPTION_SESSION_TIMEOUT', 'NOT_SET')}"
    )

    session_token = cache.create_session(
        project_id=project_id,
        encryption_key=encryption_key,
        user_id=current_user["id"],  # 🔐 CRÍTICO: Vincula sesión al usuario
        timeout_seconds=timeout_seconds,
    )

    logger.info(
        f"[VERIFY_PASSPHRASE] ✓ Session created successfully:\n"
        f"  session_token (first 16): {session_token[:16]}...\n"
        f"  cookie_name: enc_session_{project_id}"
    )

    # 🔐 SEGURIDAD: Establecer cookie httpOnly (NUNCA localStorage)
    response = JSONResponse(
        content={
            "valid": True,
            "expires_in_seconds": timeout_seconds,
            "message": "Sesión de cifrado creada exitosamente",
        }
    )

    # Cookie settings
    is_production = os.getenv("ENV", "development").lower() == "production"

    # Establecer cookie httpOnly con settings de seguridad
    # (set_cookie sobrescribe automáticamente si existe)
    response.set_cookie(
        key=cookie_name,
        value=session_token,
        max_age=timeout_seconds,
        httponly=True,
        secure=is_production,
        samesite="strict",  # Siempre strict para máxima seguridad CSRF
        path="/",
    )

    # Log successful session creation
    await log_security_event(
        request=request,
        event_type="encryption_session_created",
        user_id=current_user["id"],
        details={
            "project_id": project_id,
            "timeout_seconds": timeout_seconds,
            "cookie_name": cookie_name,
            "httponly": True,
            "secure": is_production,
        },
        severity="info",
    )

    return response


@router.get("/{project_id}/encryption/session-status")
async def get_session_status(
    project_id: str,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Verifica si existe una sesión de cifrado válida para el proyecto

    🔐 SEGURIDAD:
    - Lee la cookie httpOnly enc_session_{project_id}
    - Valida que la sesión exista en caché
    - Valida que la sesión pertenezca al usuario autenticado
    - NO expone el session token (solo confirma existencia)

    Este endpoint permite al frontend:
    - Verificar si hay sesión activa (para mostrar UI correcta)
    - Restaurar estado después de page refresh
    - Sincronizar estado entre tabs (con BroadcastChannel)

    Returns:
        {
            "has_session": true/false,
            "expires_in_seconds": 2700 (solo si has_session=true),
            "project_id": "uuid"
        }

    Notas:
    - La cookie httpOnly no es accesible desde JavaScript
    - Este endpoint provee una forma segura de verificar el estado
    - El session token NUNCA se retorna en la respuesta
    """
    from app.utils.redis_session_cache import get_encryption_session_cache

    # Leer cookie de sesión
    cookie_name = f"enc_session_{project_id}"
    session_token = request.cookies.get(cookie_name)

    if not session_token:
        return {"has_session": False, "project_id": project_id}

    # Verificar que la sesión existe en caché
    cache = get_encryption_session_cache()
    session = cache.get_session(session_token)

    if not session:
        # Cookie existe pero sesión expiró en caché
        return {"has_session": False, "project_id": project_id, "reason": "session_expired"}

    # 🔐 CRÍTICO: Validar ownership de la sesión
    session_user_id = session.get("user_id")
    current_user_id = current_user.get("id")

    if session_user_id != current_user_id:
        # 🚨 SECURITY VIOLATION: Session hijacking attempt
        # Invalidar la sesión comprometida
        cache.invalidate_session(session_token)

        await log_security_event(
            request=request,
            event_type="session_hijacking_attempt_detected",
            user_id=current_user_id,
            details={
                "project_id": project_id,
                "session_owner": session_user_id[:8] + "..." if session_user_id else "unknown",
                "attacker": current_user_id[:8] + "..." if current_user_id else "unknown",
            },
            severity="critical",
        )

        return {"has_session": False, "project_id": project_id, "reason": "security_violation"}

    # ✅ Sesión válida
    # Calcular tiempo restante
    expires_at = session.get("expires_at")
    if expires_at:
        from datetime import timezone

        now = datetime.now(timezone.utc)
        remaining = (expires_at - now).total_seconds()
        remaining = max(0, int(remaining))
    else:
        remaining = 0

    return {"has_session": True, "project_id": project_id, "expires_in_seconds": remaining}


@router.post("/{project_id}/encryption/refresh-session")
async def refresh_encryption_session(
    project_id: str,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Rotar session token para prevenir session fixation attacks (FASE 2.2)

    🔐 SEGURIDAD:
    - Genera nuevo token (CSPRNG)
    - Mantiene user_id binding (previene hijacking)
    - Grace period de 30s (configurable) para race conditions
    - httpOnly cookie con el nuevo token
    - Logging completo de auditoría

    Este endpoint:
    1. Lee el session token actual de la cookie httpOnly
    2. Valida que la sesión existe y pertenece al usuario
    3. Rota el token (genera nuevo token, marca viejo como "rotating")
    4. Establece nueva cookie httpOnly con el nuevo token
    5. Durante grace period (30s), ambos tokens son válidos
    6. Loggea el evento de rotación para auditoría

    Use cases:
    - Prevenir session fixation attacks
    - Rotación manual por el usuario
    - Rotación automática antes de expirar (opcional)
    - Rotación después de operaciones críticas (opcional)

    Returns:
        {
            "success": true,
            "project_id": "uuid",
            "expires_in_seconds": 3600,
            "message": "Session token rotated successfully"
        }

    Raises:
        HTTPException 404: No hay sesión activa para rotar
        HTTPException 403: Sesión no pertenece al usuario actual

    IMPLEMENTACIÓN: FASE 2.2 - Session Token Rotation
    Referencia: Auditoría de Seguridad 2025-01-04
    """
    import hashlib

    from app.config.security import security_settings
    from app.utils.redis_session_cache import get_encryption_session_cache
    from app.utils.security_logger import SecurityLogger

    # Leer cookie de sesión actual
    cookie_name = f"enc_session_{project_id}"
    old_token = request.cookies.get(cookie_name)

    if not old_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active encryption session found for this project",
        )

    # Verificar que la sesión existe en caché
    cache = get_encryption_session_cache()
    session = cache.get_session(old_token)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session expired or invalid"
        )

    # 🔐 CRÍTICO: Validar ownership de la sesión
    session_user_id = session.get("user_id")
    current_user_id = current_user.get("id")

    if session_user_id != current_user_id:
        # 🚨 SECURITY VIOLATION: Session hijacking attempt
        cache.invalidate_session(old_token)

        await log_security_event(
            request=request,
            event_type="session_hijacking_attempt_detected",
            user_id=current_user_id,
            details={
                "project_id": project_id,
                "action": "refresh_session_attempt",
                "session_owner": session_user_id[:8] + "..." if session_user_id else "unknown",
                "attacker": current_user_id[:8] + "..." if current_user_id else "unknown",
            },
            severity="critical",
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Session does not belong to current user"
        )

    # ✅ Rotar token con grace period
    grace_period = security_settings.SESSION_ROTATION_GRACE_PERIOD
    new_token = cache.rotate_token(old_token, grace_period_seconds=grace_period)

    if not new_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate session token",
        )

    # Calcular tiempo restante de expiración
    expires_at = session.get("expires_at")
    if expires_at:
        from datetime import timezone

        now = datetime.now(timezone.utc)
        remaining = (expires_at - now).total_seconds()
        remaining = max(0, int(remaining))
    else:
        remaining = int(os.getenv("ENCRYPTION_SESSION_TIMEOUT", "3600"))

    # 🔐 SEGURIDAD: Establecer nueva cookie httpOnly
    response = JSONResponse(
        content={
            "success": True,
            "project_id": project_id,
            "expires_in_seconds": remaining,
            "grace_period_seconds": grace_period,
            "message": "Session token rotated successfully",
        }
    )

    # Cookie settings (mismas que en /verify)
    is_production = os.getenv("ENV", "development").lower() == "production"

    response.set_cookie(
        key=cookie_name,
        value=new_token,
        max_age=remaining,  # Mantener expiración original
        httponly=True,  # 🔐 CRÍTICO: No accesible desde JavaScript
        secure=is_production,  # 🔐 Solo HTTPS en producción
        samesite="strict",  # 🔐 Previene CSRF
        path="/",  # Accesible en toda la app
    )

    # 🔐 Log token rotation para auditoría
    # Hash tokens para seguridad (nunca loggear tokens completos)
    old_token_hash = hashlib.sha256(old_token.encode()).hexdigest()[:8]
    new_token_hash = hashlib.sha256(new_token.encode()).hexdigest()[:8]

    await SecurityLogger.log_session_rotated(
        request=request,
        project_id=project_id,
        user_id=current_user_id,
        old_token_hash=old_token_hash,
        new_token_hash=new_token_hash,
        grace_period_seconds=grace_period,
    )

    return response


@router.post("/{project_id}/encryption/rotate-key")
async def rotate_master_key(
    project_id: str,
    request_data: RotateKeyRequest,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Rota la master key de un proyecto

    ⚠️ TEMPORALMENTE DESHABILITADO POR SEGURIDAD ⚠️

    Este endpoint está deshabilitado hasta completar la implementación completa
    de re-cifrado de datos. La versión actual SOLO actualiza la configuración
    pero NO re-cifra los datos existentes, lo que causaría pérdida de datos.

    La implementación completa debe:
    1. Verificar passphrase actual
    2. Descifrar TODOS los datos con clave antigua
    3. Crear nueva configuración de cifrado
    4. Re-cifrar TODOS los datos con nueva clave
    5. Manejar rollback en caso de error

    Feature flag: ENABLE_KEY_ROTATION (actualmente False)

    Use cases (cuando esté completo):
    - Rotación periódica de claves (buena práctica de seguridad)
    - Passphrase comprometida
    - Cambio de personal con acceso

    VULNERABILIDAD CRÍTICA PREVENIR:
    - Sin re-cifrado completo, los datos quedan inaccesibles después de rotación
    - Referencia: Auditoría de Seguridad 2025-01-03, Vulnerabilidad CRÍTICA #1
    """
    import os

    # Feature flag para habilitar cuando la implementación esté completa
    enable_key_rotation = os.getenv("ENABLE_KEY_ROTATION", "false").lower() == "true"

    if not enable_key_rotation:
        # Log del intento (para tracking de feature usage)
        await log_security_event(
            request=request,
            event_type="master_key_rotation_attempted",
            user_id=current_user["id"],
            details={
                "project_id": project_id,
                "status": "disabled",
                "reason": "incomplete_implementation",
            },
            severity="warning",
        )

        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "error": "Feature not implemented",
                "message": "La rotación de master key está temporalmente deshabilitada",
                "reason": "La implementación actual no re-cifra los datos existentes, lo que causaría pérdida de datos",
                "status": "in_development",
                "estimated_completion": "Próxima versión",
                "workaround": "Por favor contacte al administrador si necesita rotar su passphrase",
                "security_note": "Esta restricción existe para proteger la integridad de sus datos cifrados",
            },
        )

    # Código original (solo se ejecutará cuando el feature flag esté habilitado)
    try:
        result = EncryptionService.rotate_master_key(
            db,
            project_id,
            request_data.old_passphrase,
            request_data.new_passphrase,
            current_user["id"],
        )

        # Log security event
        await log_security_event(
            request=request,
            event_type="master_key_rotation",
            user_id=current_user["id"],
            details={"project_id": project_id, "action": "rotate_master_key", "status": "success"},
            severity="warning",  # Important security operation
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise internal_server_error(e, logger, "Error rotando master key") from e


@router.get("/{project_id}/encryption/stats", response_model=EncryptionStatsResponse)
async def get_encryption_stats(
    project_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """
    Obtiene estadísticas de cifrado para un proyecto

    Retorna:
    - Total de items por tipo (tables, columns, mappings, versions, comments)
    - Cuántos están cifrados
    - Porcentaje total de cifrado

    Útil para:
    - Dashboard de seguridad
    - Monitorear progreso de migración
    - Auditoría de cumplimiento
    """
    stats = EncryptionService.get_encryption_stats(db, project_id)
    return stats


@router.get("/{project_id}/encryption/status", response_model=EncryptionStatusResponse)
async def get_encryption_status(
    project_id: str, db=Depends(get_db_session), current_user=Depends(get_current_user)
):
    """
    Obtiene el estado actual del cifrado de un proyecto

    Returns:
        - has_encryption_config: Si el proyecto tiene cifrado configurado
        - encryption_enabled: Si el cifrado está actualmente habilitado
        - created_at: Cuándo se configuró el cifrado
    """
    from app.crud import master_key_crud

    config = master_key_crud.get_project_encryption_orm(db, project_id)

    if not config:
        return {
            "project_id": project_id,
            "encryption_enabled": False,
            "has_encryption_config": False,
            "created_at": None,
        }

    return {
        "project_id": project_id,
        "encryption_enabled": config["encryption_enabled"],
        "has_encryption_config": True,
        "created_at": str(config["created_at"]) if config["created_at"] else None,
    }


@router.post("/{project_id}/encryption/enable")
async def enable_encryption(
    project_id: str,
    request_data: EnableEncryptionRequest,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Re-habilita el cifrado para un proyecto y cifra datos existentes

    Requisitos:
    - Proyecto debe tener configuración de cifrado existente
    - Passphrase debe ser correcta
    - Usuario debe ser owner o editor

    Este endpoint:
    - Re-activa el cifrado en el proyecto
    - CIFRA AUTOMÁTICAMENTE todos los datos no cifrados (tablas, columnas)

    Use case:
    - Re-activar cifrado después de haberlo deshabilitado temporalmente
    - Activar cifrado en proyecto con datos ya creados
    """
    result = EncryptionService.enable_encryption(
        db, project_id, current_user["id"], request_data.passphrase
    )

    await log_security_event(
        request=request,
        event_type="encryption_enabled",
        user_id=current_user["id"],
        details={"project_id": project_id},
        severity="warning",
    )

    return result


@router.post("/{project_id}/encryption/disable")
async def disable_encryption(
    project_id: str,
    request_data: DisableEncryptionRequest,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Deshabilita el cifrado para un proyecto

    ADVERTENCIA:
    - Esto NO descifra los datos existentes
    - Solo deshabilita futuras operaciones cifradas
    - Los datos cifrados seguirán siendo inaccesibles sin la passphrase
    - Requiere confirmación con passphrase

    Use case:
    - Debugging temporal
    - Migración a otro sistema de cifrado
    - Proyecto en estado de solo lectura

    SOLO USAR EN CASOS EXCEPCIONALES
    """
    result = EncryptionService.disable_encryption(
        db, project_id, current_user["id"], request_data.confirm_passphrase
    )

    await log_security_event(
        request=request,
        event_type="encryption_disabled",
        user_id=current_user["id"],
        details={"project_id": project_id},
        severity="critical",  # This is a critical security change
    )

    return result


# ==================== Debug & Monitoring ====================


@router.get("/encryption/debug/cache-stats")
async def get_cache_stats(db=Depends(get_db_session), current_user=Depends(get_current_user)):
    """
    DEBUG: Obtener estadísticas del caché de sesiones de encriptación

    SOLO PARA DEBUG - NO EXPONER EN PRODUCCIÓN

    🔍 DIAGNOSTIC INFO:
    - Total de sesiones en caché
    - Sesiones activas vs expiradas
    - User ID del que está consultando
    """
    import logging

    from app.utils.redis_session_cache import get_encryption_session_cache

    logger = logging.getLogger(__name__)
    cache = get_encryption_session_cache()
    stats = cache.get_stats()

    # 🔍 ENHANCED LOGGING: Log detallado para diagnóstico
    logger.warning(
        f"[CACHE_DEBUG] Cache stats requested:\n"
        f"  user_id: {current_user['id'][:8]}...\n"
        f"  total_sessions: {stats['total_sessions']}\n"
        f"  active_sessions: {stats['active_sessions']}\n"
        f"  expired_sessions: {stats['expired_sessions']}"
    )

    return {
        "stats": stats,
        "user_id": current_user["id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{project_id}/encryption/debug/session-check")
async def debug_session_check(
    project_id: str,
    request: Request,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    DEBUG: Verificar estado de sesión de encriptación para un proyecto específico

    🔍 DIAGNOSTIC ENDPOINT:
    - Verifica si existe cookie enc_session_{project_id}
    - Busca la sesión en caché
    - Valida ownership de la sesión
    - Verifica si está expirada
    - Muestra información detallada para debugging

    SOLO PARA DEBUG - NO EXPONER EN PRODUCCIÓN
    """
    import logging
    from datetime import timezone

    from app.utils.redis_session_cache import get_encryption_session_cache

    logger = logging.getLogger(__name__)

    # Leer cookie de sesión
    cookie_name = f"enc_session_{project_id}"
    session_token = request.cookies.get(cookie_name)

    result = {
        "project_id": project_id,
        "user_id": current_user["id"],
        "cookie_name": cookie_name,
        "cookie_exists": session_token is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if not session_token:
        result["status"] = "NO_COOKIE"
        result["message"] = "No se encontró la cookie de sesión"
        logger.warning(
            f"[SESSION_DEBUG] No cookie found:\n"
            f"  project_id: {project_id[:8]}...\n"
            f"  cookie_name: {cookie_name}\n"
            f"  user_id: {current_user['id'][:8]}..."
        )
        return result

    # Mostrar primeros caracteres del token (para debugging)
    result["session_token_preview"] = session_token[:16] + "..."

    # Verificar en caché
    cache = get_encryption_session_cache()
    session = cache.get_session(session_token)

    if not session:
        result["status"] = "SESSION_NOT_IN_CACHE"
        result["message"] = (
            "La cookie existe pero la sesión no está en el caché (¿servidor reiniciado?)"
        )
        logger.warning(
            f"[SESSION_DEBUG] Cookie exists but session not in cache:\n"
            f"  project_id: {project_id[:8]}...\n"
            f"  session_token (first 16): {session_token[:16]}...\n"
            f"  user_id: {current_user['id'][:8]}...\n"
            f"  ⚠️ POSIBLE CAUSA: Servidor reiniciado (caché en memoria perdida)"
        )
        return result

    # Sesión encontrada - validar ownership
    session_user_id = session.get("user_id")
    if session_user_id != current_user["id"]:
        result["status"] = "OWNERSHIP_MISMATCH"
        result["message"] = "La sesión no pertenece al usuario actual (posible session hijacking)"
        result["session_user_id"] = str(session_user_id or "")[:8] + "..."
        logger.error(
            f"[SESSION_DEBUG] 🚨 Ownership mismatch detected:\n"
            f"  project_id: {project_id[:8]}...\n"
            f"  session_user_id: {str(session_user_id or '')[:8]}...\n"
            f"  current_user_id: {current_user['id'][:8]}..."
        )
        return result

    # Verificar expiración
    expires_at = session.get("expires_at")
    now = datetime.now(timezone.utc)
    is_expired = now > expires_at if expires_at else False
    remaining_seconds = (expires_at - now).total_seconds() if expires_at else 0

    result["status"] = "EXPIRED" if is_expired else "VALID"
    result["session_found"] = True
    result["session_user_id"] = session_user_id[:8] + "..."
    result["expires_at"] = expires_at.isoformat() if expires_at else None
    result["remaining_seconds"] = int(remaining_seconds) if not is_expired else 0
    result["is_expired"] = is_expired
    result["has_encryption_key"] = session.get("encryption_key") is not None
    result["encryption_key_length"] = len(session.get("encryption_key", b""))

    logger.warning(
        f"[SESSION_DEBUG] Session check completed:\n"
        f"  project_id: {project_id[:8]}...\n"
        f"  status: {result['status']}\n"
        f"  user_id: {current_user['id'][:8]}...\n"
        f"  expires_in: {result['remaining_seconds']}s\n"
        f"  has_encryption_key: {result['has_encryption_key']}"
    )

    return result


# ==================== Health Check ====================


@router.get("/encryption/health")
async def encryption_health_check():
    """
    Verifica que el sistema de cifrado esté funcionando correctamente

    Checks:
    - EncryptionManager puede inicializarse
    - Argon2 está disponible
    - Configuración de seguridad es válida

    Útil para:
    - Monitoring
    - CI/CD health checks
    - Troubleshooting
    """
    from app.config.security import security_settings
    from app.utils.encryption import ARGON2_AVAILABLE, EncryptionManager

    checks: Dict[str, Any] = {
        "argon2_available": ARGON2_AVAILABLE,
        "encryption_enabled_in_config": security_settings.ENCRYPTION_ENABLED,
        "argon2_memory_cost": security_settings.ARGON2_MEMORY_COST,
        "argon2_time_cost": security_settings.ARGON2_TIME_COST,
        "data_retention_days": security_settings.DATA_RETENTION_DAYS,
    }

    # Try to initialize manager
    try:
        manager = EncryptionManager()
        checks["encryption_manager"] = "ok"
    except Exception as e:
        checks["encryption_manager"] = f"error: {str(e)}"

    all_ok = checks["argon2_available"] and checks["encryption_manager"] == "ok"

    return {"status": "healthy" if all_ok else "unhealthy", "checks": checks}
