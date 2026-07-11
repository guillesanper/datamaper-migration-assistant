"""
Database Metadata Models

Modelos Pydantic para representar metadata de bases de datos de forma estructurada.
Estos modelos son independientes del dialecto SQL y facilitan:
- Introspección de schemas
- Comparación entre BDs
- Generación de scripts de migración
- Traducción entre dialectos
"""

from .column import ColumnMetadata, DataType
from .connector_tables import (
    ConnectorColumnResponse,
    ConnectorTableResponse,
    ConnectorTablesResponse,
)
from .constraint import (
    CheckConstraintMetadata,
    ConstraintType,
    ForeignKeyMetadata,
    PrimaryKeyMetadata,
    UniqueConstraintMetadata,
)
from .index import IndexMetadata, IndexType
from .schema import DatabaseMetadata, SchemaMetadata
from .statistics import TableStatistics
from .table import TableMetadata, TableType

__all__ = [
    # Column
    "ColumnMetadata",
    "DataType",
    # Table
    "TableMetadata",
    "TableType",
    # Constraints
    "PrimaryKeyMetadata",
    "ForeignKeyMetadata",
    "UniqueConstraintMetadata",
    "CheckConstraintMetadata",
    "ConstraintType",
    # Index
    "IndexMetadata",
    "IndexType",
    # Schema
    "SchemaMetadata",
    "DatabaseMetadata",
    # Statistics
    "TableStatistics",
    # Connector Tables
    "ConnectorColumnResponse",
    "ConnectorTableResponse",
    "ConnectorTablesResponse",
]
