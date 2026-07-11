"""
Operaciones CRUD para la tabla api_request_logs.
Maneja inserción, consulta de estadísticas y limpieza de logs de requests HTTP.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def log_request_orm(
    db,
    method: str,
    endpoint: str,
    status_code: int,
    response_time_ms: int,
    user_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """
    Inserta un log de request en la BD.

    Diseñado para ser llamado desde fire-and-forget tasks — no relanza
    excepciones, solo las imprime para no impactar respuestas.

    Args:
        db: SQLAlchemy Session
        method: Método HTTP (GET, POST, etc.)
        endpoint: Path del endpoint
        status_code: Código de respuesta HTTP
        response_time_ms: Tiempo de respuesta en milisegundos
        user_id: UUID del usuario autenticado (opcional)
        error_message: Mensaje de error si el request falló (opcional)
    """
    from app.models.orm import ApiRequestLog

    try:
        log = ApiRequestLog(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            response_time_ms=response_time_ms,
            user_id=user_id if user_id else None,
            error_message=error_message,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(log)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error al insertar request log: {e}")


def get_endpoint_stats_orm(
    db,
    hours: int = 24,
) -> List[Dict[str, Any]]:
    """
    Devuelve estadísticas de rendimiento por endpoint para las últimas N horas.

    Incluye avg_ms, p95_ms (percentil 95), count y error_count.

    Args:
        db: SQLAlchemy Session
        hours: Ventana de tiempo en horas

    Returns:
        Lista de dicts: {endpoint, method, count, avg_ms, p95_ms, error_count}
    """
    from sqlalchemy import Integer, cast, func

    from app.models.orm import ApiRequestLog

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        rows = (
            db.query(
                ApiRequestLog.endpoint,
                ApiRequestLog.method,
                func.count(ApiRequestLog.id).label("count"),
                cast(func.avg(ApiRequestLog.response_time_ms), Integer).label("avg_ms"),
                cast(
                    func.percentile_cont(0.95).within_group(ApiRequestLog.response_time_ms),
                    Integer,
                ).label("p95_ms"),
                func.sum(cast(ApiRequestLog.status_code >= 400, Integer)).label("error_count"),
            )
            .filter(ApiRequestLog.created_at >= since)
            .group_by(ApiRequestLog.endpoint, ApiRequestLog.method)
            .order_by(func.avg(ApiRequestLog.response_time_ms).desc())
            .all()
        )

        return [
            {
                "endpoint": row.endpoint,
                "method": row.method,
                "count": row.count,
                "avg_ms": row.avg_ms or 0,
                "p95_ms": row.p95_ms or 0,
                "error_count": int(row.error_count or 0),
            }
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Error al obtener stats de endpoints: {e}")
        return []


def get_slow_endpoints_orm(
    db,
    threshold_ms: int = 1000,
    hours: int = 24,
) -> List[Dict[str, Any]]:
    """
    Devuelve endpoints cuyo tiempo promedio supera el umbral.

    Args:
        db: SQLAlchemy Session
        threshold_ms: Umbral en milisegundos
        hours: Ventana de tiempo en horas

    Returns:
        Lista de dicts: {endpoint, method, count, avg_ms}
    """
    from sqlalchemy import Integer, cast, func

    from app.models.orm import ApiRequestLog

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        rows = (
            db.query(
                ApiRequestLog.endpoint,
                ApiRequestLog.method,
                func.count(ApiRequestLog.id).label("count"),
                cast(func.avg(ApiRequestLog.response_time_ms), Integer).label("avg_ms"),
            )
            .filter(ApiRequestLog.created_at >= since)
            .group_by(ApiRequestLog.endpoint, ApiRequestLog.method)
            .having(func.avg(ApiRequestLog.response_time_ms) >= threshold_ms)
            .order_by(func.avg(ApiRequestLog.response_time_ms).desc())
            .all()
        )

        return [
            {
                "endpoint": row.endpoint,
                "method": row.method,
                "count": row.count,
                "avg_ms": row.avg_ms or 0,
            }
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Error al obtener endpoints lentos: {e}")
        return []


def get_error_stats_orm(
    db,
    hours: int = 24,
) -> List[Dict[str, Any]]:
    """
    Devuelve conteo de errores 4xx/5xx agrupados por endpoint y status_code.

    Args:
        db: SQLAlchemy Session
        hours: Ventana de tiempo en horas

    Returns:
        Lista de dicts: {endpoint, method, status_code, count}
    """
    from sqlalchemy import func

    from app.models.orm import ApiRequestLog

    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

        rows = (
            db.query(
                ApiRequestLog.endpoint,
                ApiRequestLog.method,
                ApiRequestLog.status_code,
                func.count(ApiRequestLog.id).label("count"),
            )
            .filter(
                ApiRequestLog.created_at >= since,
                ApiRequestLog.status_code >= 400,
            )
            .group_by(
                ApiRequestLog.endpoint,
                ApiRequestLog.method,
                ApiRequestLog.status_code,
            )
            .order_by(func.count(ApiRequestLog.id).desc())
            .all()
        )

        return [
            {
                "endpoint": row.endpoint,
                "method": row.method,
                "status_code": row.status_code,
                "count": row.count,
            }
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Error al obtener stats de errores: {e}")
        return []


def cleanup_old_logs_orm(db, days: int = 30) -> int:
    """
    Elimina registros de api_request_logs más antiguos que N días.

    Args:
        db: SQLAlchemy Session
        days: Días de retención

    Returns:
        Número de registros eliminados
    """
    from app.models.orm import ApiRequestLog

    try:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        result = (
            db.query(ApiRequestLog)
            .filter(ApiRequestLog.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        if result > 0:
            logger.info(f"Limpiados {result} api_request_logs (>{days} días)")
        return int(result)
    except Exception as e:
        db.rollback()
        logger.error(f"Error al limpiar api_request_logs: {e}")
        return 0
