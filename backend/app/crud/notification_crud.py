"""
Operaciones CRUD para la tabla de notifications.
Maneja creación, consulta, marcado de lectura y eliminación de notificaciones.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ============================================================================
# FUNCIONES ORM (SQLAlchemy)
# ============================================================================


def create_notification_orm(
    db: Session,
    recipient_id: str,
    notification_kind: str,
    title: str,
    body: str,
    project_id: Optional[str] = None,
    invitation_id: Optional[str] = None,
    link_url: Optional[str] = None,
    data: Optional[dict] = None,
    actions: Optional[List[dict]] = None,
    expires_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Crea una nueva notificación (ORM version).

    Args:
        db: SQLAlchemy Session
        recipient_id: UUID del usuario destinatario
        notification_kind: Tipo de notificación (system, invitation, mention, comment, version, invite)
        title: Título de la notificación (max 160 chars)
        body: Cuerpo del mensaje
        project_id: UUID del proyecto relacionado (opcional)
        invitation_id: UUID de la invitación (opcional, para tipo 'invitation')
        link_url: URL opcional para navegar al contenido (max 500 chars)
        data: Metadata adicional en formato dict
        actions: Lista de acciones disponibles en formato dict
        expires_at: Timestamp de expiración opcional

    Returns:
        Dict con los datos de la notificación creada

    Raises:
        HTTPException: Si hay error al crear la notificación
    """
    from app.models.orm.notification import Notification
    from app.utils.orm_helpers import model_to_dict

    try:
        # Crear nueva notificación
        new_notification = Notification(
            id=uuid.uuid4(),
            recipient_id=recipient_id,
            notification_kind=notification_kind,
            title=title,
            body=body,
            project_id=project_id,
            invitation_id=invitation_id,
            link_url=link_url,
            data=data,
            actions=actions,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        )

        db.add(new_notification)
        db.commit()
        db.refresh(new_notification)

        result = model_to_dict(new_notification)
        logger.debug(
            f"Notificación creada: {new_notification.id} para usuario {str(recipient_id)[:8]}..."
        )

        return result  # type: ignore[return-value]

    except Exception as e:
        db.rollback()
        logger.error(f"Error al crear notificación: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al crear notificación: {str(e)}")


def get_user_notifications_orm(
    db: Session, user_id: str, limit: int = 50, offset: int = 0, unread_only: bool = False
) -> List[Dict[str, Any]]:
    """
    Obtiene las notificaciones de un usuario (ORM version).

    Ordena las notificaciones:
    - Primero las no leídas, luego las leídas
    - Dentro de cada grupo, las más recientes primero

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario
        limit: Número máximo de notificaciones a retornar (default: 50)
        offset: Número de notificaciones a saltar (default: 0)
        unread_only: Si True, solo retorna notificaciones no leídas

    Returns:
        Lista de dicts con los datos de las notificaciones

    Raises:
        Exception: Si hay error al obtener las notificaciones
    """
    from app.models.orm.notification import Notification
    from app.utils.orm_helpers import model_to_dict

    try:
        query = db.query(Notification).filter(Notification.recipient_id == user_id)

        # Filtrar solo no leídas si se solicita
        if unread_only:
            query = query.filter(Notification.read_at.is_(None))

        # Ordenar: primero no leídas (read_at IS NULL), luego por fecha desc
        # En SQLAlchemy, para ordenar por expresión booleana usamos case()
        from sqlalchemy import case

        query = query.order_by(
            case((Notification.read_at.is_(None), 1), else_=0).desc(),
            Notification.created_at.desc(),
        )

        # Aplicar paginación
        query = query.limit(limit).offset(offset)

        notifications = query.all()

        result = [model_to_dict(notif) for notif in notifications]
        logger.debug(f"Obtenidas {len(result)} notificaciones para usuario {str(user_id)[:8]}...")

        return result  # type: ignore[return-value]

    except Exception as e:
        logger.error(f"Error al obtener notificaciones del usuario: {str(e)}")
        raise


def get_notification_by_id_orm(
    db: Session, notification_id: str, user_id: str
) -> Optional[Dict[str, Any]]:
    """
    Obtiene una notificación específica por ID (ORM version).

    Valida que la notificación pertenezca al usuario especificado.

    Args:
        db: SQLAlchemy Session
        notification_id: UUID de la notificación
        user_id: UUID del usuario (para validar pertenencia)

    Returns:
        Dict con los datos de la notificación, o None si no existe/no pertenece al usuario

    Raises:
        Exception: Si hay error al obtener la notificación
    """
    from app.models.orm.notification import Notification
    from app.utils.orm_helpers import model_to_dict

    try:
        notification = (
            db.query(Notification)
            .filter(and_(Notification.id == notification_id, Notification.recipient_id == user_id))
            .first()
        )

        if not notification:
            logger.warning(
                f"Notificación no encontrada: {notification_id} para usuario {str(user_id)[:8]}..."
            )
            return None

        result = model_to_dict(notification)
        return result

    except Exception as e:
        logger.error(f"Error al obtener notificación: {str(e)}")
        raise


def mark_as_read_orm(db: Session, notification_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Marca una notificación como leída (ORM version).

    Solo marca como leída si:
    - La notificación existe
    - Pertenece al usuario especificado
    - No está ya marcada como leída

    Args:
        db: SQLAlchemy Session
        notification_id: UUID de la notificación
        user_id: UUID del usuario (para validar pertenencia)

    Returns:
        Dict con los datos actualizados (id, read_at), o None si no se pudo marcar

    Raises:
        HTTPException: Si hay error al marcar como leída
    """
    from app.models.orm.notification import Notification
    from app.utils.orm_helpers import model_to_dict

    try:
        notification = (
            db.query(Notification)
            .filter(
                and_(
                    Notification.id == notification_id,
                    Notification.recipient_id == user_id,
                    Notification.read_at.is_(None),  # Solo si no está leída
                )
            )
            .first()
        )

        if not notification:
            logger.warning(f"Notificación no encontrada o ya leída: {notification_id}")
            return None

        # Marcar como leída
        notification.read_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        db.commit()
        db.refresh(notification)

        result = {"id": str(notification.id), "read_at": notification.read_at}

        logger.debug(f"Notificación marcada como leída: {notification_id}")
        return result

    except Exception as e:
        db.rollback()
        logger.error(f"Error al marcar notificación como leída: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error al marcar notificación como leída: {str(e)}"
        )


def mark_all_as_read_orm(db: Session, user_id: str) -> int:
    """
    Marca todas las notificaciones no leídas de un usuario como leídas (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario

    Returns:
        Número de notificaciones marcadas como leídas

    Raises:
        HTTPException: Si hay error al marcar como leídas
    """
    from app.models.orm.notification import Notification

    try:
        # Actualizar todas las notificaciones no leídas del usuario
        updated_count = (
            db.query(Notification)
            .filter(and_(Notification.recipient_id == user_id, Notification.read_at.is_(None)))
            .update({"read_at": datetime.now(timezone.utc)}, synchronize_session="fetch")
        )

        db.commit()

        logger.debug(
            f"Marcadas {updated_count} notificaciones como leídas para usuario {str(user_id)[:8]}..."
        )
        return updated_count

    except Exception as e:
        db.rollback()
        logger.error(f"Error al marcar todas las notificaciones como leídas: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al marcar todas las notificaciones como leídas: {str(e)}",
        )


def delete_notification_orm(db: Session, notification_id: str, user_id: str) -> bool:
    """
    Elimina una notificación (ORM version).

    Solo elimina si la notificación existe y pertenece al usuario.

    Args:
        db: SQLAlchemy Session
        notification_id: UUID de la notificación
        user_id: UUID del usuario (para validar pertenencia)

    Returns:
        True si se eliminó la notificación, False si no existía/no pertenece al usuario

    Raises:
        HTTPException: Si hay error al eliminar
    """
    from app.models.orm.notification import Notification

    try:
        notification = (
            db.query(Notification)
            .filter(and_(Notification.id == notification_id, Notification.recipient_id == user_id))
            .first()
        )

        if not notification:
            logger.warning(f"Notificación no encontrada para eliminar: {notification_id}")
            return False

        db.delete(notification)
        db.commit()

        logger.debug(f"Notificación eliminada: {notification_id}")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error al eliminar notificación: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar notificación: {str(e)}")


def get_unread_count_orm(db: Session, user_id: str) -> int:
    """
    Obtiene el número de notificaciones no leídas de un usuario (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: UUID del usuario

    Returns:
        Número de notificaciones no leídas

    Raises:
        Exception: Si hay error al contar las notificaciones
    """
    from app.models.orm.notification import Notification

    try:
        count = (
            db.query(Notification)
            .filter(and_(Notification.recipient_id == user_id, Notification.read_at.is_(None)))
            .count()
        )

        logger.debug(f"Usuario {str(user_id)[:8]}... tiene {count} notificaciones no leídas")
        return count

    except Exception as e:
        logger.error(f"Error al obtener contador de notificaciones no leídas: {str(e)}")
        raise


def check_existing_invite_orm(db: Session, recipient_id: str, project_id: str) -> bool:
    """
    Verifica si ya existe una invitación pendiente para un usuario en un proyecto (ORM version).

    Args:
        db: SQLAlchemy Session
        recipient_id: UUID del usuario destinatario
        project_id: UUID del proyecto

    Returns:
        True si existe una invitación pendiente, False en caso contrario

    Raises:
        Exception: Si hay error al verificar
    """
    from app.models.orm.notification import Notification

    try:
        exists = (
            db.query(Notification)
            .filter(
                and_(
                    Notification.recipient_id == recipient_id,
                    Notification.project_id == project_id,
                    Notification.notification_kind == "invite",
                )
            )
            .first()
            is not None
        )

        return exists

    except Exception as e:
        logger.error(f"Error al verificar invitación existente: {str(e)}")
        raise
