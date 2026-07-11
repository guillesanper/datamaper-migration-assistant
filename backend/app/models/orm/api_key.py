"""
Modelo ORM para UserApiKey

Este módulo contiene el modelo de API keys de usuario.

Características:
- Cada key tiene un prefijo visible (key_prefix) y un hash SHA-256 (key_hash)
- La clave real nunca se almacena — sólo su hash para verificación
- Soporte de expiración opcional (expires_at)
- Tracking de último uso (last_used_at)
- Soft-disable con is_active (sin borrar el registro)
- CASCADE delete: todas las keys se eliminan al borrar el usuario
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class UserApiKey(Base):
    """
    API Key perteneciente a un usuario.

    La clave real (con formato ``rlk_<random>``) se genera una única vez
    y se muestra al usuario en el momento de creación. A partir de entonces
    sólo se conserva:

    - key_prefix: primeros 8 caracteres tras el prefijo 'rlk_' (para
      identificar la key en listados sin exponer el secreto).
    - key_hash: SHA-256 de la clave completa (para verificación en cada
      request autenticado con API key).

    Campos de ciclo de vida:
    - is_active: Permite deshabilitar una key sin eliminarla
    - expires_at: Fecha de expiración opcional; NULL = sin expiración
    - last_used_at: Timestamp del último uso exitoso de la key
    """

    __tablename__ = "user_api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Propietario
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identificación
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(8), nullable=False)  # Primeros 8 chars tras 'rlk_'
    key_hash = Column(String(255), nullable=False, unique=True)  # SHA-256 de la key completa

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Estado
    is_active = Column(Boolean, default=True, server_default="true", nullable=False)

    # Relationships
    user = relationship("User", back_populates="api_keys")

    # Índices
    __table_args__ = (
        # Índice para listar keys activas de un usuario
        Index("idx_api_keys_user_active", "user_id", "is_active"),
        # Índice parcial para keys con expiración pendiente
        Index(
            "idx_api_keys_expires",
            "expires_at",
            postgresql_where=(expires_at.isnot(None)),
        ),
    )

    def __repr__(self) -> str:
        status = "active" if self.is_active else "inactive"
        return (
            f"<UserApiKey("
            f"id={self.id}, "
            f"user_id={self.user_id}, "
            f"name='{self.name}', "
            f"prefix='rlk_{self.key_prefix}', "
            f"status='{status}'"
            f")>"
        )
