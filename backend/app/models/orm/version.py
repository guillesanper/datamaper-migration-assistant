"""
Modelos ORM para Version Control

Este módulo contiene los modelos para el sistema de control de versiones:
- EntityVersion: Historial de versiones de entidades (mappings, tables, columns, etc.)
- VersionTag: Tags/etiquetas para marcar versiones importantes

Características:
- Versionado incremental por entidad
- Snapshots completos en JSONB
- Diffs con la versión anterior
- Soporte de encriptación para snapshots y diffs
- Hash SHA-256 para deduplicación
- Parent version tracking para árbol de versiones
- Tags para marcar releases, milestones, etc.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

from app.database.base import Base


class EntityVersion(Base):
    """
    Versión de una entidad del sistema.

    Almacena el historial completo de cambios para cualquier entidad
    (mapping, table, column, transformation, etc.).

    Características:
    - hash: SHA-256 del snapshot para deduplicación
    - version_number: Autoincremental por entidad
    - snapshot: Estado completo de la entidad en JSON
    - diff: Diferencias respecto a versión anterior
    - Soporte de encriptación para datos sensibles

    El hash permite detectar duplicados (ej: revertir a una versión anterior
    no crea un nuevo snapshot, solo referencia al existente).
    """

    __tablename__ = "entity_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Hash SHA-256 del snapshot para deduplicación
    hash = Column(String(64), nullable=False, unique=True, index=True)

    # Relación con proyecto y entidad
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type = Column(
        String(50), nullable=False
    )  # 'mapping', 'table', 'column', 'transformation'

    # Usuario que creó la versión
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )

    # Número de versión (autoincremental por entidad)
    version_number = Column(Integer, nullable=False)

    # Tipo de cambio
    change_type = Column(String(20), nullable=False)  # 'create', 'update', 'delete'

    # Commit message opcional
    message = Column(Text)

    # Snapshot (estado completo en JSON, plaintext)
    snapshot = Column(JSONB)

    # Snapshot cifrado (cuando is_encrypted=True)
    snapshot_encrypted = Column(Text)
    snapshot_nonce = Column(Text)

    # Diff (diferencias respecto a versión anterior, plaintext)
    diff = Column(JSONB)

    # Diff cifrado (cuando is_encrypted=True)
    diff_encrypted = Column(Text)
    diff_nonce = Column(Text)

    # Flag de cifrado
    is_encrypted = Column(
        Boolean, default=False, server_default=text("false"), nullable=False, index=True
    )

    # Parent version (para tracking de árbol)
    parent_version_id = Column(
        UUID(as_uuid=True), ForeignKey("entity_versions.id", ondelete="SET NULL")
    )

    # Timestamp
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    # Relationships
    project = relationship("Project", back_populates="entity_versions")
    user = relationship("User", back_populates="entity_versions")
    tags = relationship("VersionTag", back_populates="version", cascade="all, delete-orphan")
    parent_version = relationship("EntityVersion", remote_side=[id], backref="child_versions")

    # Constraints e índices
    __table_args__ = (
        # UNIQUE: version_number debe ser único por entidad
        Index("uq_entity_versions_entity_version", "entity_id", "version_number", unique=True),
        # Índices compuestos para búsquedas
        Index("idx_versions_entity", "entity_id", "created_at"),
        Index("idx_versions_project_type", "project_id", "entity_type"),
        Index("idx_versions_encrypted", "is_encrypted", postgresql_where=(is_encrypted == True)),
        Index("idx_versions_project_encrypted", "project_id", "is_encrypted"),
    )

    def __repr__(self):
        return f"<EntityVersion(id={self.id}, entity_id={self.entity_id}, version={self.version_number}, type='{self.entity_type}')>"


class VersionTag(Base):
    """
    Tag/etiqueta para marcar versiones importantes.

    Permite etiquetar versiones específicas con nombres descriptivos
    (ej: "v1.0", "Release 2023-Q1", "Before migration", etc.).

    Características:
    - Tag name único por proyecto
    - Color opcional (hex: #FF5733)
    - Descripción opcional
    - Referencia a la versión específica
    """

    __tablename__ = "version_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relación con versión y proyecto
    version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("entity_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Información del tag
    name = Column(String(100), nullable=False)
    description = Column(Text)
    color = Column(String(7))  # Hex color: #FF5733

    # Usuario que creó el tag
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )

    # Timestamp
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    version = relationship("EntityVersion", back_populates="tags")
    project = relationship("Project")
    creator = relationship("User", back_populates="created_tags")

    # Constraints e índices
    __table_args__ = (
        # UNIQUE: Tag name debe ser único por proyecto
        Index("uq_version_tags_project_name", "project_id", "name", unique=True),
    )

    def __repr__(self):
        return f"<VersionTag(id={self.id}, name='{self.name}', version_id={self.version_id})>"
