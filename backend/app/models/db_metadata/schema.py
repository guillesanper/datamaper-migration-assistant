"""
Schema and Database Metadata Models

Modelos que agrupan toda la metadata de schemas y databases.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .constraint import ForeignKeyMetadata, PrimaryKeyMetadata, UniqueConstraintMetadata
from .index import IndexMetadata
from .statistics import TableStatistics
from .table import TableMetadata


class SchemaMetadata(BaseModel):
    """
    Metadata de un schema completo.

    Atributos:
        name: Nombre del schema
        tables: Lista de tablas en el schema
        primary_keys: Lista de primary keys
        foreign_keys: Lista de foreign keys
        unique_constraints: Lista de unique constraints
        indexes: Lista de índices
        description: Descripción del schema
    """

    name: str = Field(..., description="Nombre del schema")
    tables: List[TableMetadata] = Field(default_factory=list)
    primary_keys: List[PrimaryKeyMetadata] = Field(default_factory=list)
    foreign_keys: List[ForeignKeyMetadata] = Field(default_factory=list)
    unique_constraints: List[UniqueConstraintMetadata] = Field(default_factory=list)
    indexes: List[IndexMetadata] = Field(default_factory=list)
    description: Optional[str] = None

    @property
    def schema_name(self) -> str:
        """Alias for name - used by tests"""
        return self.name

    def get_table(self, table_name: str) -> Optional[TableMetadata]:
        """Obtiene una tabla por nombre (case-insensitive)"""
        for table in self.tables:
            if table.name.lower() == table_name.lower():
                return table
        return None

    def get_table_count(self) -> int:
        """Número de tablas en el schema"""
        return len(self.tables)

    def get_column_count(self) -> int:
        """Número total de columnas en todas las tablas"""
        return sum(table.column_count() for table in self.tables)

    def get_foreign_keys_for_table(self, table_name: str) -> List[ForeignKeyMetadata]:
        """Obtiene todas las foreign keys de una tabla"""
        return [fk for fk in self.foreign_keys if fk.table_name.lower() == table_name.lower()]

    def get_indexes_for_table(self, table_name: str) -> List[IndexMetadata]:
        """Obtiene todos los índices de una tabla"""
        return [idx for idx in self.indexes if idx.table_name.lower() == table_name.lower()]

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)


class DatabaseMetadata(BaseModel):
    """
    Metadata de una base de datos completa.

    Atributos:
        name: Nombre de la base de datos
        dialect: Dialecto SQL (postgresql, mysql, sqlserver, oracle)
        version: Versión de la BD
        schemas: Lista de schemas
        statistics: Diccionario de estadísticas por tabla {table_name: TableStatistics}
        connection_info: Información de conexión (host, port, etc.) sin credenciales
    """

    name: str = Field(..., description="Nombre de la base de datos")
    dialect: str = Field(..., description="postgresql, mysql, sqlserver, oracle")
    version: Optional[str] = None
    schemas: List[SchemaMetadata] = Field(default_factory=list)
    statistics: Dict[str, TableStatistics] = Field(
        default_factory=dict, description="Stats por tabla"
    )
    connection_info: Optional[Dict[str, str]] = Field(
        default=None, description="Host, port, etc. SIN credenciales"
    )

    @property
    def database_name(self) -> str:
        """Alias for name - used by tests"""
        return self.name

    def get_schema(self, schema_name: str) -> Optional[SchemaMetadata]:
        """Obtiene un schema por nombre (case-insensitive)"""
        for schema in self.schemas:
            if schema.name.lower() == schema_name.lower():
                return schema
        return None

    def get_all_tables(self) -> List[TableMetadata]:
        """Retorna todas las tablas de todos los schemas"""
        tables = []
        for schema in self.schemas:
            tables.extend(schema.tables)
        return tables

    def get_total_table_count(self) -> int:
        """Número total de tablas en todos los schemas"""
        return sum(schema.get_table_count() for schema in self.schemas)

    def get_total_column_count(self) -> int:
        """Número total de columnas en todas las tablas"""
        return sum(schema.get_column_count() for schema in self.schemas)

    def get_table_statistics(
        self, table_name: str, schema_name: Optional[str] = None
    ) -> Optional[TableStatistics]:
        """Obtiene estadísticas de una tabla"""
        key = f"{schema_name}.{table_name}" if schema_name else table_name
        return self.statistics.get(key)

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)

    def to_summary(self) -> dict:
        """Retorna un resumen de la BD (sin detalles de columnas)"""
        return {
            "name": self.name,
            "dialect": self.dialect,
            "version": self.version,
            "schema_count": len(self.schemas),
            "total_tables": self.get_total_table_count(),
            "total_columns": self.get_total_column_count(),
            "schemas": [
                {
                    "name": schema.name,
                    "table_count": schema.get_table_count(),
                    "tables": [table.name for table in schema.tables],
                }
                for schema in self.schemas
            ],
        }
