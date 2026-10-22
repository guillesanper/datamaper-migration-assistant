"""
Modelo ORM para Primary Key Constraints

Este módulo contiene el modelo para gestionar Primary Keys compuestas.

Características:
- Soporte para PKs simples y compuestas (múltiples columnas)
- column_ids: Array de UUIDs de columnas que componen la PK
- Constraint: array_length(column_ids, 1) >= 1
- Constraint UNIQUE(table_id) - solo una PK por tabla
- Índice GIN para búsquedas eficientes en el array

Migración 001:
Esta tabla reemplaza el campo is_primary de la tabla columns como fuente de verdad.
"""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class PrimaryKeyConstraint(Base):
    """
    Definición de Primary Key para una tabla.

    Soporta PKs simples (1 columna) y compuestas (múltiples columnas).

    Campos:
    - table_id: Tabla a la que pertenece la PK (FK a tables)
    - column_ids: Array de UUIDs de columnas que componen la PK
    - constraint_name: Nombre opcional del constraint (ej: "pk_users_id_tenant")

    Constraints:
    - UNIQUE(table_id): Solo una PK por tabla
    - CHECK: column_ids debe tener al menos 1 elemento

    Uso:
        # PK simple
        pk = PrimaryKeyConstraint(
            table_id=table.id,
            column_ids=[column_id.id],
            constraint_name="pk_users_id"
        )

        # PK compuesta
        pk = PrimaryKeyConstraint(
            table_id=table.id,
            column_ids=[col1.id, col2.id, col3.id],
            constraint_name="pk_orders_user_id_order_id"
        )
    """

    __tablename__ = "primary_key_constraints"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )

    # Relación con tabla
    table_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tables.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Array de column IDs que componen la PK
    column_ids: Any = Column(ARRAY(UUID(as_uuid=True)), nullable=False)

    # Nombre opcional del constraint
    constraint_name = Column(String(255))

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    table = relationship("Table", back_populates="primary_key_constraint")

    # Constraints e índices
    __table_args__ = (
        # Check constraint: al menos 1 columna en la PK
        CheckConstraint("array_length(column_ids, 1) >= 1", name="pk_at_least_one_column"),
        # Índice GIN para búsquedas eficientes en el array
        Index("idx_pk_constraints_column_ids", "column_ids", postgresql_using="gin"),
    )

    def __repr__(self):
        num_columns = len(self.column_ids) if self.column_ids else 0
        return f"<PrimaryKeyConstraint(id={self.id}, table_id={self.table_id}, num_columns={num_columns}, name='{self.constraint_name}')>"
