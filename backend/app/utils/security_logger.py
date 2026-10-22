"""
Sistema de logging de seguridad para DataMap
Registra eventos de seguridad importantes en la base de datos
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.config.security import security_settings
from app.database.session import get_db_session
from app.utils.security import SecurityUtils


class SecurityLogger:
    """Logger de eventos de seguridad"""

    @staticmethod
    async def log_event(
        event_type: str,
        request: Request,
        username: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info",
        endpoint: Optional[str] = None,
    ):
        """
        Registra un evento de seguridad

        Args:
            event_type: Tipo de evento (login_success, login_failed, etc.)
            request: Request de FastAPI
            username: Username involucrado (opcional)
            user_id: ID del usuario (opcional)
            details: Detalles adicionales del evento
            severity: Severidad del evento (info, warning, error, critical)
            endpoint: Endpoint específico (opcional)
        """
        if not security_settings.LOG_FAILED_ATTEMPTS and event_type.endswith("_failed"):
            return

        if not security_settings.LOG_SUCCESSFUL_LOGINS and event_type.endswith("_success"):
            return

        client_ip = SecurityUtils.get_client_ip(request)
        hashed_ip = SecurityUtils.hash_ip_address(client_ip)
        user_agent_info = SecurityUtils.get_user_agent_info(request)

        if endpoint is None:
            endpoint = request.url.path

        # Preparar detalles del evento
        event_details = {
            "user_agent": user_agent_info,
            "referer": request.headers.get("Referer"),
            "method": request.method,
            "query_params": dict(request.query_params) if request.query_params else None,
        }

        if details:
            event_details.update(details)

        # Enmascarar datos sensibles en los detalles
        if "password" in event_details:
            event_details["password"] = SecurityUtils.mask_sensitive_data(
                str(event_details["password"])
            )

        try:
            from app.crud import security_log_crud

            db = next(get_db_session())

            security_log_crud.log_event_orm(
                db,
                event_type=event_type,
                ip_address=hashed_ip,
                username=username,
                user_id=user_id,
                endpoint=endpoint,
                details=event_details,
                severity=severity,
            )

            db.close()

        except Exception as e:
            print(f"Error registrando evento de seguridad: {e}")

    @staticmethod
    async def log_login_attempt(
        request: Request,
        username: str,
        success: bool,
        user_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ):
        """
        Registra un intento de login

        Args:
            request: Request de FastAPI
            username: Username utilizado
            success: Si el login fue exitoso
            user_id: ID del usuario (si fue exitoso)
            failure_reason: Razón del fallo (si falló)
        """
        event_type = "login_success" if success else "login_failed"
        severity = "info" if success else "warning"

        details = {
            "username_attempted": SecurityUtils.sanitize_input(username),
        }

        if not success and failure_reason:
            details["failure_reason"] = failure_reason

        await SecurityLogger.log_event(
            event_type=event_type,
            request=request,
            username=username,
            user_id=user_id,
            details=details,
            severity=severity,
            endpoint="/login",
        )

    @staticmethod
    async def log_registration_attempt(
        request: Request,
        username: str,
        email: str,
        success: bool,
        user_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ):
        """
        Registra un intento de registro

        Args:
            request: Request de FastAPI
            username: Username utilizado
            email: Email utilizado
            success: Si el registro fue exitoso
            user_id: ID del usuario creado (si fue exitoso)
            failure_reason: Razón del fallo (si falló)
        """
        event_type = "registration_success" if success else "registration_failed"
        severity = "info" if success else "warning"

        details = {
            "username_attempted": SecurityUtils.sanitize_input(username),
            "email_attempted": SecurityUtils.sanitize_email(email),
        }

        if not success and failure_reason:
            details["failure_reason"] = failure_reason

        await SecurityLogger.log_event(
            event_type=event_type,
            request=request,
            username=username,
            user_id=user_id,
            details=details,
            severity=severity,
            endpoint="/register",
        )

    @staticmethod
    async def log_password_reset_attempt(
        request: Request,
        email: str,
        success: bool,
        user_id: Optional[str] = None,
        stage: str = "request",  # request, verify, reset
        failure_reason: Optional[str] = None,
    ):
        """
        Registra un intento de reset de contraseña

        Args:
            request: Request de FastAPI
            email: Email utilizado
            success: Si la operación fue exitosa
            user_id: ID del usuario (si se encontró)
            stage: Etapa del proceso (request, verify, reset)
            failure_reason: Motivo real del fallo (solo al log: la respuesta es uniforme)
        """
        event_type = f"password_reset_{stage}_{'success' if success else 'failed'}"
        severity = "info" if success else "warning"

        details = {
            "email_attempted": SecurityUtils.sanitize_email(email),
            "stage": stage,
        }

        if not success and failure_reason:
            details["failure_reason"] = failure_reason

        await SecurityLogger.log_event(
            event_type=event_type,
            request=request,
            user_id=user_id,
            details=details,
            severity=severity,
            endpoint="/forgot" if stage == "request" else "/reset",
        )

    @staticmethod
    async def log_email_verification_attempt(
        request: Request,
        email: str,
        success: bool,
        user_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ):
        """
        Registra un intento de verificación de email

        Args:
            request: Request de FastAPI
            email: Email a verificar
            success: Si la verificación fue exitosa
            user_id: ID del usuario
            failure_reason: Razón del fallo (si falló)
        """
        event_type = "email_verification_success" if success else "email_verification_failed"
        severity = "info" if success else "warning"

        details = {
            "email_verified": SecurityUtils.sanitize_email(email),
        }

        if not success and failure_reason:
            details["failure_reason"] = failure_reason

        await SecurityLogger.log_event(
            event_type=event_type,
            request=request,
            user_id=user_id,
            details=details,
            severity=severity,
            endpoint="/verify-code",
        )

    @staticmethod
    async def log_rate_limit_exceeded(
        request: Request, endpoint: str, username: Optional[str] = None
    ):
        """
        Registra cuando se excede un rate limit

        Args:
            request: Request de FastAPI
            endpoint: Endpoint afectado
            username: Username si está disponible
        """
        await SecurityLogger.log_event(
            event_type="rate_limit_exceeded",
            request=request,
            username=username,
            details={"blocked_endpoint": endpoint},
            severity="warning",
            endpoint=endpoint,
        )

    @staticmethod
    async def log_csrf_violation(
        request: Request, username: Optional[str] = None, token_provided: bool = False
    ):
        """
        Registra una violación de CSRF

        Args:
            request: Request de FastAPI
            username: Username si está disponible
            token_provided: Si se proporcionó un token (aunque fuera inválido)
        """
        await SecurityLogger.log_event(
            event_type="csrf_violation",
            request=request,
            username=username,
            details={
                "token_provided": token_provided,
                "violation_type": "missing_token" if not token_provided else "invalid_token",
            },
            severity="error",
        )

    @staticmethod
    async def log_suspicious_activity(
        request: Request,
        activity_type: str,
        details: Dict[str, Any],
        username: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """
        Registra actividad sospechosa

        Args:
            request: Request de FastAPI
            activity_type: Tipo de actividad sospechosa
            details: Detalles de la actividad
            username: Username si está disponible
            user_id: ID del usuario si está disponible
        """
        await SecurityLogger.log_event(
            event_type=f"suspicious_activity_{activity_type}",
            request=request,
            username=username,
            user_id=user_id,
            details=details,
            severity="error",
        )

    @staticmethod
    async def log_account_lockout(
        request: Request, username: str, user_id: str, lockout_duration: int
    ):
        """
        Registra un bloqueo de cuenta

        Args:
            request: Request de FastAPI
            username: Username bloqueado
            user_id: ID del usuario bloqueado
            lockout_duration: Duración del bloqueo en segundos
        """
        await SecurityLogger.log_event(
            event_type="account_lockout",
            request=request,
            username=username,
            user_id=user_id,
            details={
                "lockout_duration_seconds": lockout_duration,
                "lockout_until": (datetime.utcnow().timestamp() + lockout_duration),
            },
            severity="warning",
        )

    @staticmethod
    async def log_session_rotated(
        request: Request,
        project_id: str,
        user_id: str,
        old_token_hash: str,
        new_token_hash: str,
        grace_period_seconds: int,
    ):
        """
        Registra una rotación de session token (FASE 2.2)

        Args:
            request: Request de FastAPI
            project_id: ID del proyecto
            user_id: ID del usuario
            old_token_hash: Hash del token viejo (primeros 8 chars de SHA-256)
            new_token_hash: Hash del token nuevo (primeros 8 chars de SHA-256)
            grace_period_seconds: Duración del grace period
        """
        await SecurityLogger.log_event(
            event_type="session_rotated",
            request=request,
            user_id=user_id,
            details={
                "project_id": project_id,
                "old_token_hash": old_token_hash,
                "new_token_hash": new_token_hash,
                "grace_period_seconds": grace_period_seconds,
                "rotation_timestamp": datetime.utcnow().isoformat(),
            },
            severity="info",
            endpoint=f"/projects/{project_id}/encryption/refresh-session",
        )

    @staticmethod
    async def get_security_events(
        event_type: Optional[str] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        severity: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> list:
        """
        Obtiene eventos de seguridad filtrados

        Args:
            event_type: Filtrar por tipo de evento
            username: Filtrar por username
            ip_address: Filtrar por IP (se hasheará automáticamente)
            severity: Filtrar por severidad
            start_date: Fecha de inicio
            end_date: Fecha de fin
            limit: Límite de resultados

        Returns:
            list: Lista de eventos de seguridad
        """
        try:
            from app.crud import security_log_crud

            db = next(get_db_session())

            # Hashear IP si se proporciona
            hashed_ip = SecurityUtils.hash_ip_address(ip_address) if ip_address else None

            # Usar CRUD para obtener logs con filtros
            events = security_log_crud.get_logs_orm(
                db,
                event_type=event_type,
                severity=severity,
                username=username,
                endpoint=None,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=0,
            )

            db.close()

            return events

        except Exception as e:
            print(f"Error obteniendo eventos de seguridad: {e}")
            return []

    @staticmethod
    async def get_security_stats(days: int = 7) -> Dict[str, Any]:
        """
        Obtiene estadísticas de seguridad

        Args:
            days: Número de días hacia atrás para las estadísticas

        Returns:
            dict: Estadísticas de seguridad
        """
        try:
            from app.crud import security_log_crud

            db = next(get_db_session())

            # Usar CRUD para obtener estadísticas agregadas
            stats = security_log_crud.get_logs_stats_orm(db, days=days)

            db.close()

            # Adaptar formato para mantener compatibilidad con código existente
            return {
                "period_days": stats.get("period_days", days),
                "events_by_type": stats.get("by_type", {}),
                "events_by_severity": stats.get("by_severity", {}),
                "top_ips": [
                    {"ip": item["ip_address"], "count": item["count"]}
                    for item in stats.get("top_ips", [])
                ],
                "events_by_day": stats.get("by_day", []),
                "total_events": stats.get("total_events", 0),
            }

        except Exception as e:
            print(f"Error obteniendo estadísticas de seguridad: {e}")
            return {}


# Funciones de conveniencia
async def log_login_success(request: Request, username: str, user_id: str):
    """Registra login exitoso"""
    await SecurityLogger.log_login_attempt(request, username, True, user_id)


async def log_login_failed(request: Request, username: str, reason: str = "invalid_credentials"):
    """Registra login fallido"""
    await SecurityLogger.log_login_attempt(request, username, False, failure_reason=reason)


async def log_registration_success(request: Request, username: str, email: str, user_id: str):
    """Registra registro exitoso"""
    await SecurityLogger.log_registration_attempt(request, username, email, True, user_id)


async def log_registration_failed(request: Request, username: str, email: str, reason: str):
    """Registra registro fallido"""
    await SecurityLogger.log_registration_attempt(
        request, username, email, False, failure_reason=reason
    )


async def log_security_event(
    event_type: str,
    request: Request,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: str = "info",
    endpoint: Optional[str] = None,
):
    """
    Función de conveniencia para registrar eventos de seguridad generales

    Args:
        event_type: Tipo de evento (encryption_setup, encryption_verify, etc.)
        request: Request de FastAPI
        username: Username involucrado (opcional)
        user_id: ID del usuario (opcional)
        details: Detalles adicionales del evento
        severity: Severidad del evento (info, warning, error, critical)
        endpoint: Endpoint específico (opcional)
    """
    await SecurityLogger.log_event(
        event_type=event_type,
        request=request,
        username=username,
        user_id=user_id,
        details=details,
        severity=severity,
        endpoint=endpoint,
    )


# ============================================================================
# WRAPPERS SÍNCRONOS PARA BACKWARD COMPATIBILITY CON TESTS
# ============================================================================


def log_event(
    db: Session,
    event_type: str,
    severity: str = "info",
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    ip_address: Optional[str] = None,
    endpoint: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Wrapper síncrono para log_event - usado por tests y código que no puede usar async

    Args:
        db: Sesión de base de datos
        event_type: Tipo de evento (login_success, login_failed, etc.)
        severity: Severidad del evento (info, warning, error, critical)
        user_id: ID del usuario (opcional)
        username: Username involucrado (opcional)
        ip_address: IP address del cliente (opcional)
        endpoint: Endpoint específico (opcional)
        user_agent: User agent del cliente (opcional)
        details: Detalles adicionales del evento

    Returns:
        Dict con los datos del log creado
    """
    from app.crud import security_log_crud

    return security_log_crud.log_event_orm(
        db=db,
        event_type=event_type,
        severity=severity,
        user_id=user_id,
        username=username,
        ip_address=ip_address,
        endpoint=endpoint,
        details=details,
    )


def get_logs(
    db: Session,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    endpoint: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    **kwargs,
) -> list:
    """
    Wrapper síncrono para obtener logs - usado por tests

    Args:
        db: Sesión de base de datos
        event_type: Filtrar por tipo de evento
        severity: Filtrar por severidad
        user_id: Filtrar por user_id
        username: Filtrar por username
        endpoint: Filtrar por endpoint
        start_date: Fecha de inicio
        end_date: Fecha de fin
        limit: Límite de resultados
        offset: Offset para paginación

    Returns:
        Lista de logs
    """
    from app.crud import security_log_crud

    return security_log_crud.get_logs_orm(
        db=db,
        event_type=event_type,
        severity=severity,
        user_id=user_id,
        username=username,
        endpoint=endpoint,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


def get_logs_by_user(db: Session, user_id: str, limit: int = 50, offset: int = 0) -> list:
    """
    Wrapper síncrono para obtener logs de un usuario específico

    Args:
        db: Sesión de base de datos
        user_id: ID del usuario
        limit: Límite de resultados
        offset: Offset para paginación

    Returns:
        Lista de logs del usuario
    """
    from app.crud import security_log_crud

    return security_log_crud.get_by_user_orm(db=db, user_id=user_id, limit=limit, offset=offset)


def cleanup_old_logs(db: Session, days_old: int = 90, preserve_critical: bool = True) -> int:
    """
    Wrapper síncrono para limpiar logs antiguos

    Args:
        db: Sesión de base de datos
        days_old: Número de días para considerar logs como antiguos
        preserve_critical: Si se deben preservar logs críticos

    Returns:
        Número de logs eliminados
    """
    from app.crud import security_log_crud

    return security_log_crud.cleanup_orm(
        db=db, days_old=days_old, severity_keep="critical" if preserve_critical else None
    )


def get_logs_stats(db: Session, days: int = 7) -> Dict[str, Any]:
    """
    Wrapper síncrono para obtener estadísticas de logs

    Args:
        db: Sesión de base de datos
        days: Número de días hacia atrás para las estadísticas

    Returns:
        Dict con estadísticas agregadas
    """
    from app.crud import security_log_crud

    return security_log_crud.get_logs_stats_orm(db=db, days=days)


# Alias para get_db_session - usado en patches de tests
def get_db():
    """
    Alias para get_db_session - usado en patches de tests
    DEPRECATED: Use get_db_session directamente
    """
    return get_db_session()
