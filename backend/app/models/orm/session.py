"""
Modelo ORM para User Sessions

Este módulo contiene el modelo para sesiones de usuario.

Características:
- Gestión de sesiones con tokens y refresh tokens
- Tracking de actividad y dispositivos
- Revocación de sesiones
- Expiración automática
- Información de dispositivo y ubicación
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class UserSession(Base):
    """
    Sesión de usuario activa.

    Gestiona sesiones con:
    - Session tokens (acceso) y refresh tokens
    - Tracking de actividad (last_activity)
    - Información de dispositivo (IP, user agent, fingerprint)
    - Revocación manual de sesiones
    - Expiración automática

    Constraint UNIQUE(session_token) para prevenir duplicados.
    """

    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Usuario propietario de la sesión
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Tokens
    session_token = Column(String(64), nullable=False, unique=True, index=True)
    refresh_token = Column(String(64))

    # Información de dispositivo/red
    ip_address = Column(String(45))  # Soporta IPv6
    user_agent = Column(Text)
    device_fingerprint = Column(String(255))

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_activity = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Revocación
    is_revoked = Column(Boolean, default=False, nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True))
    revoked_reason = Column(String(100))

    # Relationship
    user = relationship("User", backref="sessions")

    # Índices
    __table_args__ = (
        # Índice para sesiones activas (no revocadas y no expiradas)
        Index("idx_sessions_active", "user_id", "is_revoked", "expires_at"),
        # Índice para cleanup de sesiones expiradas
        Index("idx_sessions_expired", "expires_at", "is_revoked"),
        # Índice para búsqueda por token de refresh
        Index(
            "idx_sessions_refresh_token",
            "refresh_token",
            postgresql_where=(refresh_token.isnot(None)),
        ),
    )

    def __repr__(self):
        status = "revoked" if self.is_revoked else "active"
        return f"<UserSession(id={self.id}, user_id={self.user_id}, status='{status}')>"
