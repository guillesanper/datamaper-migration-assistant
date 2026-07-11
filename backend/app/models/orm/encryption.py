"""
Modelo ORM para Project Encryption

Este módulo contiene el modelo para configuración de cifrado por proyecto.

Características:
- Cifrado AES-256-GCM con Argon2id para key derivation
- Master key hash one-way (solo para verificación)
- Salts separados para verificación y derivación de claves
- Un registro por proyecto (1:1 relationship)

Seguridad:
- master_key_hash es irreversible (Argon2id)
- Los salts se usan para derivar claves de cifrado
- La passphrase nunca se almacena
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class ProjectEncryption(Base):
    """
    Configuración de cifrado para un proyecto.

    Gestiona las claves de cifrado AES-256-GCM con KDF Argon2id.

    Campos:
    - master_key_hash: Hash one-way de la master key (Argon2id) - solo verificación
    - salt_verification: Salt para verificar la passphrase del usuario
    - salt_key_derivation: Salt para derivar la clave de cifrado AES-256
    - encryption_enabled: Flag para activar/desactivar cifrado

    La lógica de cifrado/descifrado se maneja en la capa de servicio,
    NO en el ORM.

    Relación 1:1 con Project (project_id es PK y FK).
    """

    __tablename__ = "project_encryption"

    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )

    # Master key hash (Argon2id one-way) - NUNCA se puede revertir
    master_key_hash = Column(Text, nullable=False)

    # Salts (128 bits cada uno, almacenados en base64)
    salt_verification = Column(Text, nullable=False)
    salt_key_derivation = Column(Text, nullable=False)

    # Estado del cifrado
    encryption_enabled = Column(Boolean, default=True, nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationship (1:1 con Project)
    project = relationship("Project", back_populates="encryption_config")

    def __repr__(self):
        return f"<ProjectEncryption(project_id={self.project_id}, encryption_enabled={self.encryption_enabled})>"
