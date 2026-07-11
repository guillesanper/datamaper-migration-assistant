"""
Modelo ORM para CSRF Tokens

Este módulo contiene el modelo para tokens CSRF.

Características:
- Tokens de un solo uso para prevenir ataques CSRF
- Asociados opcionalmente a sesiones
- Expiración automática
- Tracking de IP para seguridad adicional
- Flag de uso para prevenir reutilización
"""

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String
from sqlalchemy.sql import func

from app.database.base import Base


class CSRFToken(Base):
    """
    Token CSRF para protección contra ataques Cross-Site Request Forgery.

    Los tokens son de un solo uso y tienen expiración.
    Se asocian opcionalmente a sesiones de usuario.

    Campos:
    - token: Hash único del token CSRF
    - session_id: ID de sesión opcional
    - ip_address: IP del cliente (hasheada)
    - expires_at: Timestamp de expiración
    - used: Flag para marcar si ya fue usado
    - used_at: Timestamp de cuándo fue usado
    """

    __tablename__ = "csrf_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Token único
    token = Column(String(255), nullable=False, unique=True, index=True)

    # Sesión asociada (opcional)
    session_id = Column(String(255))

    # IP del cliente (hasheada)
    ip_address = Column(String(64), nullable=False)

    # Expiración
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Estado de uso
    used = Column(Boolean, default=False, nullable=False)
    used_at = Column(DateTime(timezone=True))

    # Timestamp de creación
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Índices
    __table_args__ = (
        # Índice para búsqueda de tokens activos (no usados y no expirados)
        Index("idx_csrf_tokens_active", "used", "expires_at"),
        Index("idx_csrf_tokens_session", "session_id", postgresql_where=(session_id.isnot(None))),
    )

    def __repr__(self):
        status = "used" if self.used else "active"
        return f"<CSRFToken(id={self.id}, token='{self.token[:8]}...', status='{status}')>"
