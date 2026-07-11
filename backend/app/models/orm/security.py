"""
Modelos ORM para Security y Rate Limiting

Este módulo contiene los modelos para el sistema de seguridad:
- SecurityLog: Registro de eventos de seguridad
- SecurityRateLimit: Control de rate limiting por IP y endpoint

Características:
- Logs de eventos con severidad (info, warning, error, critical)
- Rate limiting por identificador (IP, email, user_id) y endpoint
- Índices optimizados para búsquedas por tipo, IP, usuario, severidad
- Soporte para bloqueos temporales
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class SecurityLog(Base):
    """
    Registro de eventos de seguridad del sistema.

    Almacena eventos como login_success, login_failed, rate_limit_exceeded,
    account_locked, password_changed, etc.

    La IP se almacena hasheada para protección de privacidad.
    """

    __tablename__ = "security_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Información del evento
    event_type = Column(String(100), nullable=False, index=True)
    ip_address = Column(String(64))  # IP hasheada
    username = Column(String(100), index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    endpoint = Column(String(255), index=True)

    # Detalles y severidad
    details = Column(JSONB)  # Detalles adicionales en JSON
    severity = Column(
        String(20), default="info", nullable=False, index=True
    )  # info, warning, error, critical

    # Timestamp
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    # Relationship
    user = relationship("User", back_populates="security_logs")

    # Índices adicionales
    __table_args__ = (
        # Índice GIN para búsquedas en JSONB
        Index("idx_security_logs_details", "details", postgresql_using="gin"),
    )

    def __repr__(self):
        return f"<SecurityLog(id={self.id}, event_type='{self.event_type}', severity='{self.severity}')>"


class SecurityRateLimit(Base):
    """
    Control de rate limiting por identificador y endpoint.

    Gestiona límites de peticiones para prevenir abuso:
    - Por IP
    - Por email (durante registro/login)
    - Por user_id (para usuarios autenticados)

    Soporta bloqueos temporales con blocked_until.
    """

    __tablename__ = "security_rate_limits"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Identificación
    identifier = Column(String(255), nullable=False, index=True)  # IP, email, user_id
    ip_address = Column(String(255), nullable=False, index=True)  # Hash de la IP
    endpoint = Column(String(255), nullable=False, index=True)

    # Contadores
    request_count = Column(Integer, default=1, nullable=False)
    attempt_count = Column(Integer, default=1, nullable=False)

    # Ventanas de tiempo
    window_start = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    last_attempt = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Bloqueo temporal
    blocked_until = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    # Constraints e índices
    __table_args__ = (
        # Constraint único para evitar duplicados
        Index("unique_ip_endpoint", "ip_address", "endpoint", unique=True),
        Index(
            "unique_identifier_endpoint_window",
            "identifier",
            "endpoint",
            "window_start",
            unique=True,
        ),
        # Índice parcial para búsquedas de registros bloqueados
        Index(
            "idx_security_rate_limits_blocked",
            "blocked_until",
            postgresql_where=(blocked_until.isnot(None)),
        ),
    )

    def __repr__(self):
        return f"<SecurityRateLimit(id={self.id}, identifier='{self.identifier}', endpoint='{self.endpoint}')>"
