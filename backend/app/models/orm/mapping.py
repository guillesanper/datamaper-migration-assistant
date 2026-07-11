"""
Modelo ORM para Mappings

Este módulo contiene el modelo para mappings entre columnas origen-destino.

Características principales:
- Modo híbrido: Import (esquema importado cifrado) vs Connector (conexión dinámica con hash)
- Soporte de encriptación AES-256-GCM para todos los campos sensibles
- Hashing SHA-256 para modo connector (one-way, irreversible)
- Referencias a sesiones Redis para modo connector
- Referencias a tablas importadas para modo import
- Transformation logic (puede ser cifrada)

Modos soportados:
1. IMPORT→IMPORT: Ambos lados usan esquemas importados (con cifrado reversible)
2. IMPORT→CONNECTOR: Origen importado, destino con connector (hash)
3. CONNECTOR→IMPORT: Origen con connector, destino importado
4. CONNECTOR→CONNECTOR: Ambos lados con connector (ambos hasheados)

La lógica de cifrado/descifrado y hashing se maneja en la capa de servicio.
"""

import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Mapping(Base):
    """
    Mapping entre columnas de origen y destino.

    Soporta modo híbrido (import/connector) con encriptación y hashing.

    Campos de origen:
    - origin_source_type: 'import' o 'connector'
    - origin_table / origin_table_encrypted+nonce (modo import)
    - origin_table_hash (modo connector, SHA-256)
    - origin_column / origin_column_encrypted+nonce (modo import)
    - origin_column_hash (modo connector, SHA-256)
    - origin_session_id: UUID de sesión Redis (modo connector)
    - origin_table_id: FK a tables (modo import)

    Campos de destino:
    - destination_source_type: 'import' o 'connector'
    - destination_table / destination_table_encrypted+nonce (modo import)
    - destination_table_hash (modo connector, SHA-256)
    - destination_column / destination_column_encrypted+nonce (modo import)
    - destination_column_hash (modo connector, SHA-256)
    - destination_session_id: UUID de sesión Redis (modo connector)
    - destination_table_id: FK a tables (modo import)

    Transformation logic:
    - transformation_logic / transformation_logic_encrypted+nonce

    Check constraints aseguran integridad según el modo.
    """

    __tablename__ = "mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relación con proyecto
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ========== ORIGEN ==========

    # Tipo de fuente de datos para el origen
    origin_source_type = Column(String(20), default="import", nullable=False, index=True)

    # Modo IMPORT: Nombre de tabla (plaintext o cifrado)
    origin_table = Column(String(255))
    origin_table_encrypted = Column(Text)
    origin_table_nonce = Column(Text)

    # Modo IMPORT: Nombre de columna (plaintext o cifrado)
    origin_column = Column(String(255))
    origin_column_encrypted = Column(Text)
    origin_column_nonce = Column(Text)

    # Modo CONNECTOR: Hashes SHA-256 (one-way, irreversible)
    origin_table_hash = Column(String(64))
    origin_column_hash = Column(String(64))

    # Modo CONNECTOR: Sesión Redis
    origin_session_id = Column(UUID(as_uuid=True))

    # Modo IMPORT: FK a tabla importada
    origin_table_id = Column(UUID(as_uuid=True), ForeignKey("tables.id", ondelete="CASCADE"))

    # ========== DESTINO ==========

    # Tipo de fuente de datos para el destino
    destination_source_type = Column(String(20), default="import", nullable=False, index=True)

    # Modo IMPORT: Nombre de tabla (plaintext o cifrado)
    destination_table = Column(String(255))
    destination_table_encrypted = Column(Text)
    destination_table_nonce = Column(Text)

    # Modo IMPORT: Nombre de columna (plaintext o cifrado)
    destination_column = Column(String(255))
    destination_column_encrypted = Column(Text)
    destination_column_nonce = Column(Text)

    # Modo CONNECTOR: Hashes SHA-256 (one-way, irreversible)
    destination_table_hash = Column(String(64))
    destination_column_hash = Column(String(64))

    # Modo CONNECTOR: Sesión Redis
    destination_session_id = Column(UUID(as_uuid=True))

    # Modo IMPORT: FK a tabla importada
    destination_table_id = Column(UUID(as_uuid=True), ForeignKey("tables.id", ondelete="CASCADE"))

    # ========== TRANSFORMATION LOGIC ==========

    # Lógica de transformación (puede ser sensible, soporta cifrado)
    transformation_logic = Column(Text)
    transformation_logic_encrypted = Column(Text)
    transformation_logic_nonce = Column(Text)

    # Flag de cifrado (para campos en modo import)
    is_encrypted = Column(Boolean, default=False, nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    project = relationship("Project", back_populates="mappings")
    origin_table_ref = relationship(
        "Table", back_populates="origin_mappings", foreign_keys=[origin_table_id]
    )
    destination_table_ref = relationship(
        "Table", back_populates="destination_mappings", foreign_keys=[destination_table_id]
    )

    # Constraints e índices
    __table_args__ = (
        # ===== Constraints de validación de source_type =====
        CheckConstraint(
            "origin_source_type IN ('import', 'connector')", name="chk_origin_source_type_values"
        ),
        CheckConstraint(
            "destination_source_type IN ('import', 'connector')",
            name="chk_destination_source_type_values",
        ),
        # ===== Constraints para modo CONNECTOR =====
        # Si origin es 'connector', debe tener session_id y table_hash
        CheckConstraint(
            """
            origin_source_type != 'connector' OR (
                origin_session_id IS NOT NULL AND
                origin_table_hash IS NOT NULL
            )
            """,
            name="chk_origin_connector_requirements",
        ),
        # Si destination es 'connector', debe tener session_id y table_hash
        CheckConstraint(
            """
            destination_source_type != 'connector' OR (
                destination_session_id IS NOT NULL AND
                destination_table_hash IS NOT NULL
            )
            """,
            name="chk_destination_connector_requirements",
        ),
        # ===== Constraints para modo IMPORT =====
        # Si origin es 'import', debe tener table_id O nombre (plaintext/encrypted)
        CheckConstraint(
            """
            origin_source_type != 'import' OR (
                origin_table_id IS NOT NULL OR
                origin_table IS NOT NULL OR
                origin_table_encrypted IS NOT NULL
            )
            """,
            name="chk_origin_import_requirements",
        ),
        # Si destination es 'import', debe tener table_id O nombre (plaintext/encrypted)
        CheckConstraint(
            """
            destination_source_type != 'import' OR (
                destination_table_id IS NOT NULL OR
                destination_table IS NOT NULL OR
                destination_table_encrypted IS NOT NULL
            )
            """,
            name="chk_destination_import_requirements",
        ),
        # ===== Constraints de encriptación (modo IMPORT) =====
        CheckConstraint(
            """
            (origin_table IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
            OR
            (origin_table_encrypted IS NOT NULL AND origin_table_nonce IS NOT NULL AND is_encrypted = TRUE)
            OR
            (origin_source_type = 'connector')
            """,
            name="check_mapping_origin_table_or_encrypted",
        ),
        CheckConstraint(
            """
            (origin_column IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
            OR
            (origin_column_encrypted IS NOT NULL AND origin_column_nonce IS NOT NULL AND is_encrypted = TRUE)
            OR
            (origin_source_type = 'connector')
            """,
            name="check_mapping_origin_column_or_encrypted",
        ),
        CheckConstraint(
            """
            (destination_table IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
            OR
            (destination_table_encrypted IS NOT NULL AND destination_table_nonce IS NOT NULL AND is_encrypted = TRUE)
            OR
            (destination_source_type = 'connector')
            """,
            name="check_mapping_dest_table_or_encrypted",
        ),
        CheckConstraint(
            """
            (destination_column IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))
            OR
            (destination_column_encrypted IS NOT NULL AND destination_column_nonce IS NOT NULL AND is_encrypted = TRUE)
            OR
            (destination_source_type = 'connector')
            """,
            name="check_mapping_dest_column_or_encrypted",
        ),
        # ===== Índices =====
        # Índices para filtrar por tipo de fuente
        Index(
            "idx_mappings_project_modes",
            "project_id",
            "origin_source_type",
            "destination_source_type",
        ),
        # Índices para sesiones Redis (solo donde sean NOT NULL)
        Index(
            "idx_mappings_origin_session_id",
            "origin_session_id",
            postgresql_where=(origin_session_id.isnot(None)),
        ),
        Index(
            "idx_mappings_destination_session_id",
            "destination_session_id",
            postgresql_where=(destination_session_id.isnot(None)),
        ),
        # Índices para FKs de tablas importadas
        Index(
            "idx_mappings_origin_table_id",
            "origin_table_id",
            postgresql_where=(origin_table_id.isnot(None)),
        ),
        Index(
            "idx_mappings_destination_table_id",
            "destination_table_id",
            postgresql_where=(destination_table_id.isnot(None)),
        ),
        # Índices compuestos para búsqueda por hashes (modo connector)
        Index(
            "idx_mappings_origin_hashes",
            "origin_table_hash",
            "origin_column_hash",
            postgresql_where=(origin_source_type == "connector"),
        ),
        Index(
            "idx_mappings_destination_hashes",
            "destination_table_hash",
            "destination_column_hash",
            postgresql_where=(destination_source_type == "connector"),
        ),
        # Índice para mappings encriptados
        Index("idx_mappings_encrypted", "is_encrypted", postgresql_where=(is_encrypted == True)),
        Index("idx_mappings_project_encrypted", "project_id", "is_encrypted"),
    )

    def __repr__(self):
        mode = f"{self.origin_source_type.upper()}→{self.destination_source_type.upper()}"
        return f"<Mapping(id={self.id}, mode={mode}, is_encrypted={self.is_encrypted})>"
