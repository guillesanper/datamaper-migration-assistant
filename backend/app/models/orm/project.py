"""
Modelos ORM para Projects y Project Members

Este módulo contiene los modelos para proyectos y sus miembros:
- Project: Proyectos de migración de datos
- ProjectMember: Miembros del proyecto con roles (owner, editor, viewer)

Características:
- Proyectos con bases de datos origen y destino
- Sistema de roles con ENUM de PostgreSQL
- Relationship con owner y members
- Cascading deletes para mantener integridad
"""

import enum
import uuid
from typing import Any

from sqlalchemy import DECIMAL, Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class MemberRole(str, enum.Enum):
    """
    Roles de miembros en un proyecto.

    - owner: Propietario del proyecto (control total)
    - editor: Puede editar mappings, tablas, columnas
    - viewer: Solo lectura
    """

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class Project(Base):
    """
    Proyecto de migración de datos.

    Un proyecto contiene:
    - Tablas de origen y destino
    - Columnas de esas tablas
    - Mappings entre columnas
    - Miembros con diferentes roles

    El owner es el creador del proyecto y tiene control total.
    """

    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Información básica
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    origin_db = Column(String(255))
    destination_db = Column(String(255))

    # Owner del proyecto
    owner_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Estado del proyecto
    is_deleted = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="active")
    progress = Column(Integer, default=0)
    budget: Any = Column(DECIMAL(10, 2), default=0.0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_accessed_at = Column(DateTime(timezone=True), nullable=True, default=None, index=True)

    # Relationships
    owner = relationship("User", back_populates="owned_projects", foreign_keys=[owner_id])
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    tables = relationship("Table", back_populates="project", cascade="all, delete-orphan")
    mappings = relationship("Mapping", back_populates="project", cascade="all, delete-orphan")
    subscriptions = relationship(
        "Subscription", back_populates="project", cascade="all, delete-orphan"
    )
    encryption_config = relationship(
        "ProjectEncryption", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )
    entity_versions = relationship(
        "EntityVersion", back_populates="project", cascade="all, delete-orphan"
    )
    comments = relationship("Comment", back_populates="project", cascade="all, delete-orphan")
    entity_locks = relationship(
        "EntityLock", back_populates="project", cascade="all, delete-orphan"
    )
    activities = relationship(
        "ProjectActivity", back_populates="project", cascade="all, delete-orphan"
    )
    notifications = relationship(
        "Notification", back_populates="project", cascade="all, delete-orphan"
    )
    migration_scripts = relationship(
        "MigrationScript", back_populates="project", cascade="all, delete-orphan"
    )
    migration_executions = relationship(
        "MigrationExecution", back_populates="project", cascade="all, delete-orphan"
    )
    migration_audit_logs = relationship("MigrationAuditLog", back_populates="project")

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"


class ProjectMember(Base):
    """
    Miembro de un proyecto con rol específico.

    Los roles determinan los permisos:
    - owner: Control total (solo puede haber uno)
    - editor: Puede editar mappings, tablas, columnas
    - viewer: Solo lectura

    Constraint UNIQUE(project_id, user_id) asegura que un usuario
    solo puede tener un rol por proyecto.
    """

    __tablename__ = "project_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relaciones
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Rol del miembro
    role: Any = Column(
        SQLEnum(
            MemberRole,
            name="member_role",
            create_type=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )

    # Usuario que añadió a este miembro (para auditoría)
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    project = relationship("Project", back_populates="members")
    user = relationship("User", back_populates="project_memberships", foreign_keys=[user_id])
    added_by_user = relationship("User", back_populates="added_members", foreign_keys=[added_by])

    # Constraints e índices
    __table_args__ = (
        Index("uq_project_members_project_user", "project_id", "user_id", unique=True),
        Index("idx_project_members_role", "project_id", "role"),
    )

    def __repr__(self):
        return f"<ProjectMember(id={self.id}, project_id={self.project_id}, user_id={self.user_id}, role='{self.role.value}')>"
