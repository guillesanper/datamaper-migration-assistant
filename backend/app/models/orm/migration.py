"""
Modelos ORM para Migration System

Este módulo contiene los modelos para el sistema de generación y ejecución de migraciones:
- MigrationScript: Scripts SQL generados para migraciones
- MigrationExecution: Tracking de ejecuciones de scripts
- MigrationAuditLog: Log de auditoría para cambios de esquema

Características:
- Versionado de scripts con SHA-256 hash
- Tracking de progreso de ejecución
- Análisis de dependencias (topological order)
- Backup y rollback support
- Dry run capability
"""

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class MigrationScript(Base):
    """
    Script SQL generado para migración de datos.

    Almacena scripts con opciones de generación y análisis de dependencias.

    Características:
    - script_hash: SHA-256 del contenido para deduplicación
    - dependency_order: Orden de ejecución de tablas (topological sort)
    - Opciones: batch_size, include_constraints, include_validation
    - Dialecto SQL (postgresql, mysql, etc.)
    """

    __tablename__ = "migration_scripts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relación con proyecto
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Script SQL
    script_content = Column(Text, nullable=False)
    script_hash = Column(String(64), nullable=False, index=True)  # SHA-256 hash

    # Opciones de generación
    batch_size = Column(Integer, default=10000, nullable=False)
    include_constraints = Column(Boolean, default=True, nullable=False)
    include_validation = Column(Boolean, default=True, nullable=False)
    dialect = Column(String(50), default="postgresql", nullable=False)

    # Análisis de dependencias
    dependency_order: Any = Column(ARRAY(Text))  # Array de nombres de tablas en orden de ejecución

    # Usuario que generó el script
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="migration_scripts")
    creator = relationship("User", back_populates="created_migration_scripts")
    executions = relationship(
        "MigrationExecution",
        back_populates="script",
        foreign_keys="MigrationExecution.script_hash",
        primaryjoin="MigrationScript.script_hash == foreign(MigrationExecution.script_hash)",
    )

    def __repr__(self):
        return f"<MigrationScript(id={self.id}, hash='{self.script_hash[:8]}...', dialect='{self.dialect}')>"


class MigrationExecution(Base):
    """
    Tracking de ejecución de scripts de migración.

    Almacena estado, progreso y resultados de ejecuciones.

    Estados:
    - pending: No iniciada
    - running: En ejecución
    - success: Completada exitosamente
    - failed: Falló con errores
    - rolled_back: Se hizo rollback
    - dry_run_complete: Dry run completado (no se ejecutó realmente)
    """

    __tablename__ = "migration_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relación con proyecto
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Hash del script ejecutado
    script_hash = Column(String(64), index=True)  # SHA-256 hash

    # Estado de ejecución
    status = Column(String(20), nullable=False, default="pending", index=True)

    # Progreso
    rows_migrated = Column(Integer, default=0, server_default=text("0"), nullable=False)

    # Timestamps
    started_at = Column(DateTime(timezone=True), index=True)
    completed_at = Column(DateTime(timezone=True))

    # Backup
    backup_id = Column(String(255))

    # Log de ejecución (JSON array de pasos)
    execution_log = Column(
        JSONB
    )  # [{"step": 1, "table": "users", "rows": 100, "duration": 1.5, "status": "success"}, ...]

    # Manejo de errores
    error_message = Column(Text)

    # Usuario que ejecutó la migración
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    project = relationship("Project", back_populates="migration_executions")
    creator = relationship("User", back_populates="created_migration_executions")
    script = relationship(
        "MigrationScript",
        back_populates="executions",
        foreign_keys=[script_hash],
        primaryjoin="foreign(MigrationExecution.script_hash) == MigrationScript.script_hash",
        viewonly=True,
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'success', 'failed', 'rolled_back', 'dry_run_complete')",
            name="chk_migration_execution_status",
        ),
        Index("idx_migration_executions_project_status", "project_id", "status"),
        Index("idx_migration_executions_started", "started_at"),
    )

    def __repr__(self):
        return (
            f"<MigrationExecution(id={self.id}, status='{self.status}', rows={self.rows_migrated})>"
        )


class MigrationAuditLog(Base):
    """
    Log de auditoría para cambios de esquema y migraciones.

    Registra todas las acciones importantes:
    - TYPE_CHANGE: Cambio de tipo de dato
    - PK_ADDED: Primary key agregada
    - FK_CREATED: Foreign key creada
    - TABLE_BACKUP: Backup de tabla creado
    - MIGRATION_EXECUTED: Migración ejecutada

    Almacena valores anteriores y nuevos, resultados de validación.
    """

    __tablename__ = "migration_audit_log"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # Número de migración
    migration_number = Column(String(20), nullable=False, index=True)

    # Acción realizada
    action = Column(String(50), nullable=False)

    # Entidades afectadas
    table_id = Column(UUID(as_uuid=True), ForeignKey("tables.id", ondelete="SET NULL"))
    column_id = Column(UUID(as_uuid=True))

    # Relación con proyecto (opcional, puede ser NULL para logs de sistema)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"))

    # Valores anterior y nuevo
    old_value = Column(JSONB)
    new_value = Column(JSONB)

    # Resultado de validación
    validation_result = Column(JSONB)

    # Referencia a backup
    backup_reference = Column(String(255))

    # Usuario que realizó la acción
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Timestamp
    timestamp = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    # Metadata adicional
    ip_address = Column(String(50))
    user_agent = Column(Text)

    # Relationships
    project = relationship("Project", back_populates="migration_audit_logs")

    # Índices
    __table_args__ = (
        Index("idx_audit_migration_action", "migration_number", "action"),
        Index("idx_audit_table_id", "table_id", postgresql_where=(table_id.isnot(None))),
        Index("idx_audit_user_id", "user_id", postgresql_where=(user_id.isnot(None))),
    )

    def __repr__(self):
        return f"<MigrationAuditLog(id={self.id}, migration='{self.migration_number}', action='{self.action}')>"
