"""
Modelo ORM para Entity Locks

Este módulo contiene el modelo para bloqueos de edición.

Características:
- Previene conflictos de edición concurrente
- Locks con expiración automática
- Heartbeat para mantener locks activos
- Solo un lock por entidad a la vez
- Cleanup automático de locks expirados
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class EntityLock(Base):
    """
    Bloqueo de edición para prevenir conflictos concurrentes.

    Cuando un usuario comienza a editar una entidad (mapping, table, column),
    se crea un lock que previene que otros usuarios editen simultáneamente.

    Características:
    - expires_at: Timestamp de expiración del lock
    - last_heartbeat: Último ping del cliente (para mantener activo)
    - Solo un lock por entidad a la vez

    El cliente debe enviar heartbeats periódicos para mantener el lock activo.
    Los locks expirados deben limpiarse con cleanup_expired_locks().
    """

    __tablename__ = "entity_locks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Entidad bloqueada
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)  # 'mapping', 'table', 'column'

    # Relación con proyecto
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Usuario que posee el lock
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Timestamps
    acquired_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    last_heartbeat = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    project = relationship("Project", back_populates="entity_locks")
    user = relationship("User", back_populates="entity_locks")

    # Constraints e índices
    __table_args__ = (
        # UNIQUE: Solo un lock por entidad
        Index("uq_entity_locks_entity", "entity_id", "entity_type", unique=True),
        # Índices para búsquedas
        Index("idx_locks_expires", "expires_at"),
        Index("idx_locks_project_user", "project_id", "user_id"),
    )

    def __repr__(self):
        return f"<EntityLock(id={self.id}, entity_id={self.entity_id}, entity_type='{self.entity_type}', user_id={self.user_id})>"
