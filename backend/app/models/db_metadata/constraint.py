"""
Constraint Metadata Models

Define estructuras para primary keys, foreign keys, unique constraints, etc.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ConstraintType(str, Enum):
    """
    Tipos de constraints en bases de datos.
    """

    PRIMARY_KEY = "PRIMARY KEY"
    FOREIGN_KEY = "FOREIGN KEY"
    UNIQUE = "UNIQUE"
    CHECK = "CHECK"
    NOT_NULL = "NOT NULL"
    DEFAULT = "DEFAULT"


class PrimaryKeyMetadata(BaseModel):
    """
    Metadata de una primary key.

    Atributos:
        constraint_name: Nombre del constraint (ej: "pk_users_id")
        constraint_type: Tipo de constraint (PRIMARY_KEY)
        column_names: Lista de columnas que componen la PK
        table_name: Nombre de la tabla
        schema: Schema de la tabla
    """

    constraint_name: str = Field(..., description="Nombre del constraint")
    constraint_type: ConstraintType = Field(default=ConstraintType.PRIMARY_KEY)
    column_names: List[str] = Field(..., min_length=1, description="Columnas de la PK")
    table_name: str
    schema: Optional[str] = None  # type: ignore[assignment]

    # Alias para compatibilidad
    @property
    def name(self) -> str:
        return self.constraint_name

    @property
    def columns(self) -> List[str]:
        return self.column_names

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)

    def is_composite(self) -> bool:
        """Retorna True si la PK es compuesta (múltiples columnas)"""
        return len(self.columns) > 1


class ForeignKeyMetadata(BaseModel):
    """
    Metadata de una foreign key.

    Atributos:
        constraint_name: Nombre del constraint
        constraint_type: Tipo de constraint (FOREIGN_KEY)
        column_names: Columnas de la tabla source (esta tabla)
        referenced_table: Tabla referenciada
        referenced_schema: Schema de la tabla referenciada
        referenced_columns: Columnas referenciadas
        on_delete: Acción ON DELETE (CASCADE, SET NULL, RESTRICT, etc.)
        on_update: Acción ON UPDATE
        table_name: Nombre de la tabla source
        schema: Schema de la tabla source
    """

    constraint_name: str = Field(..., description="Nombre del constraint")
    constraint_type: ConstraintType = Field(default=ConstraintType.FOREIGN_KEY)
    column_names: List[str] = Field(..., min_length=1)
    referenced_table: str
    referenced_schema: Optional[str] = None
    referenced_columns: List[str] = Field(..., min_length=1)
    on_delete: Optional[str] = Field(None, description="CASCADE, SET NULL, RESTRICT, NO ACTION")
    on_update: Optional[str] = Field(None, description="CASCADE, SET NULL, RESTRICT, NO ACTION")
    table_name: str
    schema: Optional[str] = None  # type: ignore[assignment]

    # Alias para compatibilidad
    @property
    def name(self) -> str:
        return self.constraint_name

    @property
    def columns(self) -> List[str]:
        return self.column_names

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)

    def is_composite(self) -> bool:
        """Retorna True si la FK es compuesta"""
        return len(self.columns) > 1

    def get_full_referenced_table(self) -> str:
        """Retorna nombre completo de tabla referenciada"""
        if self.referenced_schema:
            return f"{self.referenced_schema}.{self.referenced_table}"
        return self.referenced_table


class UniqueConstraintMetadata(BaseModel):
    """
    Metadata de un constraint UNIQUE.

    Atributos:
        constraint_name: Nombre del constraint
        constraint_type: Tipo de constraint (UNIQUE)
        column_names: Columnas que componen el unique
        table_name: Nombre de la tabla
        schema: Schema de la tabla
    """

    constraint_name: str = Field(..., description="Nombre del constraint")
    constraint_type: ConstraintType = Field(default=ConstraintType.UNIQUE)
    column_names: List[str] = Field(..., min_length=1)
    table_name: str
    schema: Optional[str] = None  # type: ignore[assignment]

    # Alias para compatibilidad
    @property
    def name(self) -> str:
        return self.constraint_name

    @property
    def columns(self) -> List[str]:
        return self.column_names

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)

    def is_composite(self) -> bool:
        """Retorna True si el unique es compuesto"""
        return len(self.columns) > 1


class CheckConstraintMetadata(BaseModel):
    """
    Metadata de un constraint CHECK.

    Atributos:
        constraint_name: Nombre del constraint
        constraint_type: Tipo de constraint (CHECK)
        check_clause: Expresión SQL del check (ej: "age >= 18")
        table_name: Nombre de la tabla
        schema: Schema de la tabla
    """

    constraint_name: str = Field(..., description="Nombre del constraint")
    constraint_type: ConstraintType = Field(default=ConstraintType.CHECK)
    check_clause: str = Field(..., description="Expresión SQL del CHECK")
    table_name: str
    schema: Optional[str] = None  # type: ignore[assignment]

    # Alias para compatibilidad
    @property
    def name(self) -> str:
        return self.constraint_name

    @property
    def expression(self) -> str:
        return self.check_clause

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)
