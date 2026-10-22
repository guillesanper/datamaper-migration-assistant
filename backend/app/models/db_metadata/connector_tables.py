"""
Connector Tables Response Models

Modelos Pydantic para representar tablas de BD externas con hashes pre-computados.
Estos modelos se usan cuando el usuario conecta via connector (sin guardar estructura).
Los hashes SHA-256 identifican tablas/columnas en los mappings almacenados.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ConnectorColumnResponse(BaseModel):
    """Columna de una BD externa con hash pre-computado para mappings."""

    name: str
    column_hash: str  # SHA-256(name) — identificador para mappings, invisible al usuario
    data_type: str  # Tipo generico normalizado
    native_type: str  # Tipo nativo del dialecto (ej: "VARCHAR2", "NVARCHAR")
    is_nullable: bool
    is_primary_key: bool
    is_auto_increment: bool
    default_value: Optional[str] = None
    max_length: Optional[int] = None
    ordinal_position: int = 1


class ConnectorTableResponse(BaseModel):
    """Tabla de una BD externa con hash pre-computado para mappings."""

    name: str  # Nombre real — lo que ve el usuario
    table_hash: str  # SHA-256(name) — identificador para mappings, invisible al usuario
    schema: str  # type: ignore[assignment]
    table_type: str  # 'BASE TABLE', 'VIEW', etc.
    columns: List[ConnectorColumnResponse]


class ConnectorTablesResponse(BaseModel):
    """Respuesta completa del endpoint connector-tables."""

    session_id: str
    tables: List[ConnectorTableResponse]
    # Schemas que no se pudieron leer (permisos, errores de la BD): sus tablas no aparecen
    failed_schemas: List[str] = Field(default_factory=list)
