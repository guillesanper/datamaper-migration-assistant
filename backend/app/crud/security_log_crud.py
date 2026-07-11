"""
Operaciones CRUD para la tabla de security_logs.
Maneja registro, consulta y limpieza de eventos de seguridad.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCIONES ORM (SQLAlchemy)
# ============================================================================


def log_event_orm(
    db,
    event_type: str,
    ip_address: Optional[str] = None,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: str = "info",
) -> Dict[str, Any]:
    """
    Registra un evento de seguridad en el sistema (ORM version).

    Args:
        db: SQLAlchemy Session
        event_type: Tipo de evento (login_success, login_failed, rate_limit_exceeded, etc.)
        ip_address: Dirección IP (hasheada) del cliente
        username: Username asociado al evento
        user_id: ID del usuario (UUID string) si aplica
        endpoint: Endpoint/ruta donde ocurrió el evento
        details: Detalles adicionales del evento (JSONB)
        severity: Severidad del evento (info, warning, error, critical)

    Returns:
        Dict con los datos del log creado

    Raises:
        Exception: Si hay error al crear el log
    """
    from app.models.orm import SecurityLog
    from app.utils.orm_helpers import model_to_dict

    try:
        new_log = SecurityLog(
            event_type=event_type,
            ip_address=ip_address,
            username=username,
            user_id=user_id if user_id else None,
            endpoint=endpoint,
            details=details,
            severity=severity,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

        db.add(new_log)
        db.commit()
        db.refresh(new_log)

        logger.info(f"Evento de seguridad registrado: {event_type} ({severity})")

        result = model_to_dict(new_log)
        assert result is not None, "model_to_dict returned None for a non-None model"
        return result

    except Exception as e:
        db.rollback()
        logger.error(f"Error al registrar evento de seguridad: {str(e)}")
        raise


def get_logs_orm(
    db,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    endpoint: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Obtiene logs de seguridad con filtros opcionales (ORM version).

    Args:
        db: SQLAlchemy Session
        event_type: Filtrar por tipo de evento
        severity: Filtrar por severidad (info, warning, error, critical)
        user_id: Filtrar por ID de usuario
        username: Filtrar por username
        endpoint: Filtrar por endpoint
        start_date: Fecha de inicio del rango
        end_date: Fecha de fin del rango
        limit: Número máximo de resultados
        offset: Número de resultados a saltar (paginación)

    Returns:
        Lista de diccionarios con logs de seguridad
    """
    from app.models.orm import SecurityLog
    from app.utils.orm_helpers import models_to_dict_list

    try:
        query = db.query(SecurityLog)

        # Aplicar filtros opcionales
        if event_type:
            query = query.filter(SecurityLog.event_type == event_type)

        if severity:
            query = query.filter(SecurityLog.severity == severity)

        if user_id:
            query = query.filter(SecurityLog.user_id == user_id)

        if username:
            query = query.filter(SecurityLog.username == username)

        if endpoint:
            query = query.filter(SecurityLog.endpoint == endpoint)

        if start_date:
            query = query.filter(SecurityLog.created_at >= start_date)

        if end_date:
            query = query.filter(SecurityLog.created_at <= end_date)

        # Ordenar por más reciente primero y paginar
        logs = query.order_by(SecurityLog.created_at.desc()).limit(limit).offset(offset).all()

        return models_to_dict_list(logs)

    except Exception as e:
        logger.error(f"Error al obtener logs de seguridad: {str(e)}")
        return []


def get_by_user_orm(
    db,
    user_id: str,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Obtiene logs de seguridad de un usuario específico (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario
        event_type: Filtrar por tipo de evento (opcional)
        severity: Filtrar por severidad (opcional)
        limit: Número máximo de resultados
        offset: Número de resultados a saltar (paginación)

    Returns:
        Lista de diccionarios con logs del usuario
    """
    from app.models.orm import SecurityLog
    from app.utils.orm_helpers import models_to_dict_list

    try:
        query = db.query(SecurityLog).filter(SecurityLog.user_id == user_id)

        # Aplicar filtros adicionales si se proporcionan
        if event_type:
            query = query.filter(SecurityLog.event_type == event_type)

        if severity:
            query = query.filter(SecurityLog.severity == severity)

        # Ordenar por más reciente primero y paginar
        logs = query.order_by(SecurityLog.created_at.desc()).limit(limit).offset(offset).all()

        return models_to_dict_list(logs)

    except Exception as e:
        logger.error(f"Error al obtener logs de usuario {user_id}: {str(e)}")
        return []


def cleanup_orm(db, days_old: int = 90, severity_keep: Optional[str] = "critical") -> int:
    """
    Limpia logs de seguridad antiguos (ORM version).
    Por defecto mantiene todos los logs críticos y elimina logs de más de 90 días.

    Args:
        db: SQLAlchemy Session
        days_old: Días de antigüedad para considerar un log eliminable
        severity_keep: Severidad de logs que nunca se eliminan (ej: 'critical')
                       Si es None, se eliminan todos los logs antiguos

    Returns:
        Número de logs eliminados

    Raises:
        Exception: Si hay error al eliminar logs
    """
    from app.models.orm import SecurityLog

    try:
        # Validar que days_old sea un entero para prevenir problemas
        days_old = int(days_old)

        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_old)

        # Construir query de eliminación
        query = db.query(SecurityLog).filter(SecurityLog.created_at < cutoff_date)

        # Si hay una severidad a mantener, excluirla
        if severity_keep:
            query = query.filter(SecurityLog.severity != severity_keep)

        # Ejecutar eliminación
        result = query.delete(synchronize_session=False)

        db.commit()

        if result > 0:
            logger.info(f"Limpiados {result} logs de seguridad antiguos (>{days_old} días)")

        return int(result)

    except Exception as e:
        db.rollback()
        logger.error(f"Error al limpiar logs de seguridad: {str(e)}")
        raise


def get_logs_stats_orm(db, days: int = 7) -> Dict[str, Any]:
    """
    Obtiene estadísticas agregadas de logs de seguridad (ORM version).

    Args:
        db: SQLAlchemy Session
        days: Número de días hacia atrás para las estadísticas (default: 7)

    Returns:
        Dict con estadísticas:
        {
            'by_type': {'login_success': 100, 'login_failed': 10, ...},
            'by_severity': {'info': 80, 'warning': 15, 'error': 4, 'critical': 1},
            'top_ips': [{'ip_address': '1.2.3.4', 'count': 50}, ...],
            'by_day': [{'date': '2025-01-01', 'count': 120}, ...]
        }
    """
    from sqlalchemy import desc, func

    from app.models.orm import SecurityLog

    try:
        # Calcular fecha de inicio del rango
        start_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        # Count por tipo de evento
        by_type_query = (
            db.query(SecurityLog.event_type, func.count().label("count"))
            .filter(SecurityLog.created_at >= start_date)
            .group_by(SecurityLog.event_type)
            .all()
        )

        by_type = {row.event_type: row.count for row in by_type_query}

        # Count por severidad
        by_severity_query = (
            db.query(SecurityLog.severity, func.count().label("count"))
            .filter(SecurityLog.created_at >= start_date)
            .group_by(SecurityLog.severity)
            .all()
        )

        by_severity = {row.severity: row.count for row in by_severity_query}

        # Top 10 IPs
        top_ips_query = (
            db.query(SecurityLog.ip_address, func.count().label("count"))
            .filter(SecurityLog.created_at >= start_date)
            .group_by(SecurityLog.ip_address)
            .order_by(desc(func.count()))
            .limit(10)
            .all()
        )

        top_ips = [{"ip_address": row.ip_address, "count": row.count} for row in top_ips_query]

        # Por día (últimos N días)
        by_day_query = (
            db.query(func.date(SecurityLog.created_at).label("date"), func.count().label("count"))
            .filter(SecurityLog.created_at >= start_date)
            .group_by("date")
            .order_by("date")
            .all()
        )

        by_day = [{"date": row.date.isoformat(), "count": row.count} for row in by_day_query]

        return {
            "period_days": days,
            "by_type": by_type,
            "by_severity": by_severity,
            "top_ips": top_ips,
            "by_day": by_day,
            "total_events": sum(by_type.values()) if by_type else 0,
        }

    except Exception as e:
        logger.error(f"Error al obtener estadísticas de logs: {str(e)}")
        return {
            "period_days": days,
            "by_type": {},
            "by_severity": {},
            "top_ips": [],
            "by_day": [],
            "total_events": 0,
        }
