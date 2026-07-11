"""
Modelo ORM para Users

Este módulo contiene el modelo de usuarios del sistema.

Características:
- Autenticación con password hash
- Avatar de usuario (avatar_url)
- Campos de seguridad (is_verified, failed_login_attempts, locked_until)
- Autenticación de dos factores TOTP (totp_secret, totp_enabled)
- Soft delete con is_deleted
- Tracking de último login (last_login_at, last_login_ip)
- Relationships con proyectos, suscripciones, security logs, etc.
- Relación 1:1 con preferencias de usuario (UserPreferences)
- Relación 1:N con API keys (UserApiKey)
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class User(Base):
    """
    Modelo de usuario del sistema.

    Gestiona autenticación, autorización y seguridad de usuarios.

    Campos de seguridad:
    - is_verified: Usuario ha verificado su email
    - is_deleted: Soft delete (no se elimina físicamente)
    - failed_login_attempts: Contador para lockout automático
    - locked_until: Timestamp de bloqueo temporal tras múltiples intentos fallidos
    - last_login_at/last_login_ip: Tracking de actividad

    Campos de identidad:
    - avatar_url: URL del avatar del usuario (nullable)

    Campos 2FA / TOTP:
    - totp_secret: Secreto TOTP cifrado (nullable; presente sólo si el usuario enroló 2FA)
    - totp_enabled: Indica si 2FA está activo para la cuenta
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Credenciales
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(500), nullable=True)

    # 2FA / TOTP
    totp_secret = Column(String(64), nullable=True)
    totp_enabled = Column(Boolean, default=False, server_default="false", nullable=False)

    # Flags de seguridad
    is_verified = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    # Control de intentos de login
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True))

    # Tracking de actividad
    last_login_at = Column(DateTime(timezone=True))
    last_login_ip = Column(String(64))  # IP hasheada
    password_changed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    owned_projects = relationship(
        "Project", back_populates="owner", foreign_keys="Project.owner_id"
    )
    project_memberships = relationship(
        "ProjectMember",
        back_populates="user",
        foreign_keys="ProjectMember.user_id",
        cascade="all, delete-orphan",
    )
    subscriptions = relationship(
        "Subscription", back_populates="user", cascade="all, delete-orphan"
    )
    security_logs = relationship("SecurityLog", back_populates="user")
    notifications = relationship(
        "Notification", back_populates="recipient", cascade="all, delete-orphan"
    )
    entity_versions = relationship("EntityVersion", back_populates="user")
    comments = relationship("Comment", back_populates="user", foreign_keys="Comment.user_id")
    comment_reactions = relationship(
        "CommentReaction", back_populates="user", cascade="all, delete-orphan"
    )
    comment_reads = relationship("CommentRead", back_populates="user", cascade="all, delete-orphan")
    entity_locks = relationship("EntityLock", back_populates="user", cascade="all, delete-orphan")
    project_activities = relationship("ProjectActivity", back_populates="user")

    # Relaciones inversas para campos added_by, created_by, resolved_by
    added_members = relationship(
        "ProjectMember", back_populates="added_by_user", foreign_keys="ProjectMember.added_by"
    )
    created_tags = relationship("VersionTag", back_populates="creator")
    resolved_comments = relationship(
        "Comment", back_populates="resolver", foreign_keys="Comment.resolved_by"
    )
    created_migration_scripts = relationship("MigrationScript", back_populates="creator")
    created_migration_executions = relationship("MigrationExecution", back_populates="creator")

    # Ajustes de usuario
    preferences = relationship(
        "UserPreferences",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    api_keys = relationship(
        "UserApiKey",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Índices adicionales
    __table_args__ = (
        Index("idx_users_locked", "locked_until", postgresql_where=(locked_until.isnot(None))),
        Index("idx_users_active", "is_deleted", "is_verified"),
    )

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"
