"""
Modelo ORM para UserPreferences

Este módulo contiene el modelo de preferencias de usuario.

Características:
- Relación 1:1 con User (user_id es la PK y FK a users.id)
- Idioma y zona horaria por usuario
- Configuración de exportación y tipo de BD por defecto
- Configuración granular de notificaciones (email e in-app) en JSONB
- CASCADE delete: se elimina al borrar el usuario
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class UserPreferences(Base):
    """
    Preferencias de configuración de un usuario.

    Relación 1:1 con User — ``user_id`` actúa como PRIMARY KEY y FK.
    Se elimina en cascada al borrar el usuario asociado.

    Campos de localización:
    - language: Código BCP-47 del idioma preferido (p.ej. 'es', 'en')
    - timezone: Identificador IANA de zona horaria (p.ej. 'UTC', 'Europe/Madrid')

    Campos de trabajo:
    - default_db_type: Tipo de BD usado por defecto en nuevos proyectos
    - default_export_format: Formato de exportación preferido ('xlsx', 'csv', 'json')

    Campos de notificaciones (JSONB):
    - email_notifications: Control granular de qué eventos generan email
    - in_app_notifications: Control granular de qué eventos aparecen in-app
    """

    __tablename__ = "user_preferences"

    # PK compuesta con la FK — garantiza exactamente una fila por usuario
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    # Localización
    language = Column(String(10), server_default="es", nullable=False)
    timezone = Column(String(64), server_default="UTC", nullable=False)

    # Preferencias de trabajo
    default_db_type = Column(String(50), nullable=True)
    default_export_format = Column(String(20), server_default="xlsx", nullable=False)

    # Configuración de notificaciones
    email_notifications = Column(JSONB, server_default="{}", nullable=False)
    in_app_notifications = Column(JSONB, server_default="{}", nullable=False)

    # Timestamp
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="preferences")

    def __repr__(self) -> str:
        return (
            f"<UserPreferences("
            f"user_id={self.user_id}, "
            f"language='{self.language}', "
            f"timezone='{self.timezone}'"
            f")>"
        )
