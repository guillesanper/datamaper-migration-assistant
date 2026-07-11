"""
Table Metadata Models

Define la estructura de metadata de tablas.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .column import ColumnMetadata


class TableType(str, Enum):
    """Tipo de tabla"""

    BASE_TABLE = "BASE TABLE"  # Tabla regular
    TABLE = "BASE TABLE"  # Alias for BASE_TABLE
    VIEW = "VIEW"  # Vista
    MATERIALIZED_VIEW = "MATERIALIZED VIEW"  # Vista materializada
    TEMPORARY = "TEMPORARY"  # Tabla temporal
    SYSTEM = "SYSTEM"  # Tabla del sistema


class TableMetadata(BaseModel):
    """
    Metadata completa de una tabla.

    Atributos:
        name: Nombre de la tabla
        schema: Schema/database donde está la tabla
        table_type: Tipo de tabla (BASE TABLE, VIEW, etc.)
        columns: Lista de columnas
        description: Comentario/descripción de la tabla
        catalog: Catálogo de la BD (opcional, usado en algunos dialectos)
    """

    name: str = Field(..., min_length=1, max_length=128)
    schema: Optional[str] = Field(None, description="Schema o database")  # type: ignore[assignment]
    table_type: TableType = TableType.BASE_TABLE
    columns: List[ColumnMetadata] = Field(default_factory=list)
    description: Optional[str] = None
    catalog: Optional[str] = None

    class Config:
        use_enum_values = True

    @property
    def table_name(self) -> str:
        """Alias for name - used by tests"""
        return self.name

    @property
    def schema_name(self) -> Optional[str]:
        """Alias for schema - used by tests"""
        return self.schema

    @property
    def primary_keys(self) -> List[ColumnMetadata]:
        """Returns list of primary key columns - used by tests"""
        return self.get_primary_key_columns()

    @property
    def indexes(self) -> List:
        """
        Returns list of indexes for this table.
        Indexes are loaded dynamically by get_database_metadata() and stored in _indexes.
        """
        return getattr(self, "_indexes", [])

    def get_column(self, column_name: str) -> Optional[ColumnMetadata]:
        """Obtiene una columna por nombre (case-insensitive)"""
        for col in self.columns:
            if col.name.lower() == column_name.lower():
                return col
        return None

    def get_primary_key_columns(self) -> List[ColumnMetadata]:
        """Retorna las columnas que son primary key"""
        return [col for col in self.columns if col.is_primary_key]

    def get_foreign_key_columns(self) -> List[ColumnMetadata]:
        """Retorna las columnas que son foreign key"""
        return [col for col in self.columns if col.is_foreign_key]

    def get_nullable_columns(self) -> List[ColumnMetadata]:
        """Retorna las columnas que permiten NULL"""
        return [col for col in self.columns if col.is_nullable]

    def get_required_columns(self) -> List[ColumnMetadata]:
        """Retorna las columnas que NO permiten NULL"""
        return [col for col in self.columns if not col.is_nullable]

    def get_full_name(self) -> str:
        """
        Retorna el nombre completo de la tabla (schema.table).

        Ejemplos:
        - public.users
        - dbo.Orders
        - users (si no hay schema)
        """
        if self.schema:
            return f"{self.schema}.{self.name}"
        return self.name

    def to_dict(self) -> dict:
        """Convierte a dict para serialización"""
        return self.model_dump(exclude_none=True)

    def column_count(self) -> int:
        """Número de columnas"""
        return len(self.columns)

    def has_primary_key(self) -> bool:
        """Verifica si tiene primary key"""
        return any(col.is_primary_key for col in self.columns)

    def has_foreign_keys(self) -> bool:
        """Verifica si tiene foreign keys"""
        return any(col.is_foreign_key for col in self.columns)
