"""
Modelo ORM para Tables

Este módulo contiene el modelo para tablas de metadata.

Características:
- Soporte para tablas de origen y destino (type: 'origin' o 'destination')
- Soporte de encriptación con AES-256-GCM:
  - name (plaintext, nullable cuando está encriptado)
  - name_encrypted + name_nonce (cifrado)
  - is_encrypted (flag booleano)
- Constraint UNIQUE(project_id, name, type)
- Check constraints para garantizar que existe name O name_encrypted

La lógica de cifrado/descifrado se maneja en la capa de servicio.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Table(Base):
    """
    Tabla de metadata (origen o destino) en un proyecto.

    Representa una tabla física en la base de datos origen o destino.

    Campos:
    - name: Nombre en texto plano (nullable cuando is_encrypted=True)
    - name_encrypted: Nombre cifrado con AES-256-GCM (base64)
    - name_nonce: Nonce único usado para cifrar (96 bits, base64)
    - is_encrypted: Flag que indica si los datos están cifrados
    - type: 'origin' o 'destination'

    Check constraint asegura que existe name O (name_encrypted + name_nonce).
    """

    __tablename__ = "tables"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relación con proyecto
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Nombre (plaintext, nullable cuando está encriptado)
    name = Column(String(255))

    # Campos de encriptación
    name_encrypted = Column(Text)
    name_nonce = Column(Text)
    is_encrypted = Column(
        Boolean, default=False, server_default=text("false"), nullable=False, index=True
    )

    # Tipo de tabla
    type = Column(String(50), nullable=False)  # 'origin' o 'destination'

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    project = relationship("Project", back_populates="tables")
    columns = relationship("TableColumn", back_populates="table", cascade="all, delete-orphan")
    primary_key_constraint = relationship(
        "PrimaryKeyConstraint", back_populates="table", uselist=False, cascade="all, delete-orphan"
    )

    # Relaciones para modo import en mappings
    origin_mappings = relationship(
        "Mapping", back_populates="origin_table_ref", foreign_keys="Mapping.origin_table_id"
    )
    destination_mappings = relationship(
        "Mapping",
        back_populates="destination_table_ref",
        foreign_keys="Mapping.destination_table_id",
    )

    # Constraints e índices
    __table_args__ = (
        # Constraint UNIQUE: (project_id, name, type) - solo cuando no está encriptado
        Index(
            "uq_tables_project_name_type",
            "project_id",
            "name",
            "type",
            unique=True,
            postgresql_where=(is_encrypted == False),
        ),
        # Constraint CHECK: debe existir name O name_encrypted+nonce
        CheckConstraint(
            """
            (name IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
            OR
            (name_encrypted IS NOT NULL AND name_nonce IS NOT NULL AND is_encrypted = TRUE)
            """,
            name="check_table_name_or_encrypted",
        ),
        # Índice compuesto para búsquedas por proyecto y tipo
        Index("idx_tables_project_type", "project_id", "type"),
        # Índice parcial para búsquedas de tablas encriptadas
        Index("idx_tables_encrypted", "is_encrypted", postgresql_where=(is_encrypted == True)),
        Index("idx_tables_project_encrypted", "project_id", "is_encrypted"),
    )

    def __repr__(self):
        display_name = self.name if not self.is_encrypted else "[ENCRYPTED]"
        return f"<Table(id={self.id}, name='{display_name}', type='{self.type}', is_encrypted={self.is_encrypted})>"
