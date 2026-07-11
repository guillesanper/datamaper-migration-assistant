"""
Table Statistics Models

Estadísticas de tablas (obtenidas de metadata, NO de datos).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TableStatistics(BaseModel):
    """
    Estadísticas de una tabla (solo metadata, NO lee datos).

    IMPORTANTE: Los valores son aproximados, obtenidos de:
    - PostgreSQL: pg_stat_user_tables, pg_class
    - MySQL: information_schema.tables
    - SQL Server: sys.dm_db_partition_stats
    - Oracle: user_tables, all_tables

    Atributos:
        table_name: Nombre de la tabla
        schema: Schema de la tabla
        row_count: Número aproximado de filas (NO ejecuta COUNT(*))
        size_bytes: Tamaño en bytes (aproximado)
        size_mb: Tamaño en MB (calculado desde size_bytes)
        index_size_bytes: Tamaño de índices en bytes (opcional)
        last_vacuum: Última vez que se ejecutó VACUUM (PostgreSQL)
        last_analyze: Última vez que se actualizaron estadísticas
        last_modified: Última modificación de la tabla
    """

    table_name: str
    schema: Optional[str] = None  # type: ignore[assignment]

    # Estadísticas de tamaño
    row_count: Optional[int] = Field(
        default=None, ge=0, description="Aproximado, NO ejecuta COUNT(*)"
    )
    size_bytes: Optional[int] = Field(default=None, ge=0)
    index_size_bytes: Optional[int] = Field(default=None, ge=0)

    # Fechas de mantenimiento
    last_vacuum: Optional[datetime] = None
    last_analyze: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    @property
    def total_size_bytes(self) -> Optional[int]:
        """Alias for size_bytes - used by tests"""
        return self.size_bytes

    @property
    def data_size_bytes(self) -> Optional[int]:
        """Alias for index_size_bytes - used by tests"""
        return self.index_size_bytes

    @property
    def size_mb(self) -> Optional[float]:
        """Tamaño en MB (calculado desde size_bytes)"""
        if self.size_bytes is not None:
            return round(self.size_bytes / (1024 * 1024), 2)
        return None

    @property
    def index_size_mb(self) -> Optional[float]:
        """Tamaño de índices en MB"""
        if self.index_size_bytes is not None:
            return round(self.index_size_bytes / (1024 * 1024), 2)
        return None

    @property
    def total_size_mb(self) -> Optional[float]:
        """Tamaño total (tabla + índices) en MB"""
        if self.size_bytes is not None:
            total = self.size_bytes + (self.index_size_bytes or 0)
            return round(total / (1024 * 1024), 2)
        return None

    def to_dict(self) -> dict:
        """Convierte a dict incluyendo propiedades calculadas"""
        data = self.model_dump(exclude_none=True)
        data["size_mb"] = self.size_mb
        data["index_size_mb"] = self.index_size_mb
        data["total_size_mb"] = self.total_size_mb
        return data
