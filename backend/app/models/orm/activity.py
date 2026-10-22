"""
Modelo ORM para Project Activity

Este módulo contiene el modelo para el feed de actividad del proyecto.

Características:
- Feed de eventos del proyecto para auditoría y timeline
- Tipos de actividad: version_created, comment_added, member_added, etc.
- Metadata adicional en JSONB
- Referencia opcional a entidades
- Timestamps automáticos
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class ProjectActivity(Base):
    """
    Actividad del proyecto para auditoría y timeline.

    Registra eventos importantes:
    - version_created: Se creó una nueva versión
    - comment_added: Se agregó un comentario
    - member_added: Se agregó un miembro
    - mapping_created: Se creó un mapping
    - etc.

    La metadata puede contener información adicional específica del evento.
    """

    __tablename__ = "project_activity"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )

    # Relación con proyecto
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Usuario que realizó la acción (puede ser NULL para acciones del sistema)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Tipo de actividad
    activity_type = Column(String(50), nullable=False, index=True)

    # Entidad relacionada (opcional)
    entity_id = Column(UUID(as_uuid=True))
    entity_type = Column(String(50))

    # Descripción de la actividad
    description = Column(Text, nullable=False)

    # Metadata adicional del evento en JSON (nombre en Python: activity_metadata, nombre en BD: metadata)
    activity_metadata = Column("metadata", JSONB)

    # Timestamp
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    # Relationships
    project = relationship("Project", back_populates="activities")
    user = relationship("User", back_populates="project_activities")

    # Índices
    __table_args__ = (
        Index("idx_activity_project_created", "project_id", "created_at"),
        Index("idx_activity_user", "user_id", postgresql_where=(user_id.isnot(None))),
        Index(
            "idx_activity_entity",
            "entity_id",
            "entity_type",
            postgresql_where=(entity_id.isnot(None)),
        ),
        Index("idx_activity_type", "activity_type"),
    )

    def __repr__(self):
        return f"<ProjectActivity(id={self.id}, type='{self.activity_type}', description='{self.description[:50]}...')>"
