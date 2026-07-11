"""
Index Metadata Models

Define estructuras para índices.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class IndexType(str, Enum):
    """Tipo de índice"""

    BTREE = "BTREE"  # B-Tree (default en la mayoría de BDs)
    HASH = "HASH"  # Hash index
    GIN = "GIN"  # Generalized Inverted Index (PostgreSQL)
    GIST = "GIST"  # Generalized Search Tree (PostgreSQL)
    BRIN = "BRIN"  # Block Range Index (PostgreSQL)
    SPATIAL = "SPATIAL"  # Spatial index
    FULLTEXT = "FULLTEXT"  # Full-text index
    CLUSTERED = "CLUSTERED"  # Clustered index (SQL Server)
    NONCLUSTERED = "NONCLUSTERED"  # Non-clustered index (SQL Server)
    BITMAP = "BITMAP"  # Bitmap index (Oracle)
    UNKNOWN = "UNKNOWN"


class IndexMetadata(BaseModel):
    """
    Metadata de un índice.

    Atributos:
        name: Nombre del índice
        columns: Lista de columnas indexadas (en orden)
        table_name: Nombre de la tabla
        schema: Schema de la tabla
        is_unique: Si es índice único
        is_primary: Si es el índice de la primary key
        index_type: Tipo de índice
        filter_condition: Condición WHERE para índices parciales (opcional)
        included_columns: Columnas incluidas (INCLUDE en SQL Server, no indexadas pero almacenadas)
    """

    name: str = Field(..., description="Nombre del índice")
    columns: List[str] = Field(..., min_length=1, description="Columnas indexadas")
    table_name: str
    schema: Optional[str] = None  # type: ignore[assignment]
    is_unique: bool = False
    is_primary: bool = False
    index_type: IndexType = IndexType.BTREE
    filter_condition: Optional[str] = Field(
        default=None, description="WHERE clause para índices parciales"
    )
    included_columns: Optional[List[str]] = Field(
        default=None, description="Columnas INCLUDE (SQL Server)"
    )

    class Config:
        use_enum_values = True

    @property
    def index_name(self) -> str:
        """Alias for name - used by tests"""
        return self.name

    @property
    def column_names(self) -> List[str]:
        """Alias for columns - used by tests"""
        return self.columns

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)

    def is_composite(self) -> bool:
        """Retorna True si el índice es compuesto (múltiples columnas)"""
        return len(self.columns) > 1

    def is_partial(self) -> bool:
        """Retorna True si es un índice parcial (con WHERE)"""
        return self.filter_condition is not None

    def has_included_columns(self) -> bool:
        """Retorna True si tiene columnas INCLUDE"""
        return self.included_columns is not None and len(self.included_columns) > 0
