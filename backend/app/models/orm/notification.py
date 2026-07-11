"""
Modelo ORM para Notifications

Este módulo contiene el modelo para el sistema de notificaciones.

Características:
- Notificaciones de diferentes tipos (system, invitation, mention, comment, version)
- Tracking de estado (leída/no leída)
- Expiración automática
- Acciones disponibles en JSONB
- Metadata adicional en JSONB
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Notification(Base):
    """
    Notificación para un usuario.

    Tipos de notificaciones:
    - system: Notificaciones del sistema (mantenimiento, updates, etc.)
    - invitation: Invitaciones a proyectos
    - mention: Menciones en comentarios
    - comment: Nuevos comentarios o replies
    - version: Nueva versión creada

    Características:
    - title: Título corto (max 160 chars)
    - body: Cuerpo del mensaje
    - link_url: URL opcional para navegar al contenido
    - data: Metadata adicional en JSON
    - actions: Acciones disponibles (aceptar, rechazar, etc.)
    - read_at: Timestamp de lectura (NULL = no leída)
    - expires_at: Timestamp de expiración opcional
    """

    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Destinatario
    recipient_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Tipo de notificación
    notification_kind = Column(
        String(50), nullable=False
    )  # 'system', 'invitation', 'mention', 'comment', 'version'

    # Relación con proyecto (opcional)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))

    # ID de invitación (opcional, para tipo 'invitation')
    invitation_id = Column(UUID(as_uuid=True))

    # Contenido
    title = Column(String(160), nullable=False)
    body = Column(Text, nullable=False)
    link_url = Column(String(500))

    # Metadata y acciones en JSON
    data = Column(JSONB)
    actions = Column(
        JSONB
    )  # [{"label": "Aceptar", "action": "accept"}, {"label": "Rechazar", "action": "reject"}]

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    read_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))

    # Relationships
    recipient = relationship("User", back_populates="notifications")
    project = relationship("Project", back_populates="notifications")

    # Índices
    __table_args__ = (
        # Índice para notificaciones no leídas
        Index(
            "idx_notifications_read",
            "recipient_id",
            "read_at",
            postgresql_where=(read_at.is_(None)),
        ),
        # Índice para notificaciones por proyecto
        Index("idx_notifications_project", "project_id", postgresql_where=(project_id.isnot(None))),
        # Índice para notificaciones por tipo
        Index("idx_notifications_kind", "notification_kind"),
    )

    def __repr__(self):
        status = "unread" if self.read_at is None else "read"
        return f"<Notification(id={self.id}, kind='{self.notification_kind}', title='{self.title}', status='{status}')>"
