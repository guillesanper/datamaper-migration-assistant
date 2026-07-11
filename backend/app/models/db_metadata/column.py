"""
Column Metadata Models

Define la estructura de metadata de columnas de forma independiente del dialecto SQL.
"""

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class DataType(str, Enum):
    """
    Tipos de datos genéricos (independientes del dialecto SQL).

    Estos tipos se mapean a tipos específicos de cada BD cuando se generan scripts.
    """

    # Strings
    STRING = "string"  # VARCHAR, NVARCHAR, CHARACTER VARYING
    VARCHAR = "string"  # Alias for STRING - used by tests
    TEXT = "text"  # TEXT, CLOB, NVARCHAR(MAX)
    CHAR = "char"  # CHAR, NCHAR

    # Numbers
    INTEGER = "integer"  # INT, INTEGER, NUMBER(10)
    BIGINT = "bigint"  # BIGINT, NUMBER(19)
    SMALLINT = "smallint"  # SMALLINT, NUMBER(5)
    DECIMAL = "decimal"  # DECIMAL, NUMERIC, NUMBER
    FLOAT = "float"  # FLOAT, REAL, BINARY_FLOAT
    DOUBLE = "double"  # DOUBLE PRECISION, BINARY_DOUBLE

    # Boolean
    BOOLEAN = "boolean"  # BOOLEAN, BIT, TINYINT(1), NUMBER(1)

    # Date/Time
    DATE = "date"  # DATE
    TIME = "time"  # TIME, TIMESTAMP
    DATETIME = "datetime"  # DATETIME, TIMESTAMP, DATETIME2
    TIMESTAMP = "timestamp"  # TIMESTAMP, DATETIME2, TIMESTAMP WITH TIME ZONE

    # Binary
    BINARY = "binary"  # BYTEA, BLOB, VARBINARY
    UUID = "uuid"  # UUID, UNIQUEIDENTIFIER, CHAR(36)

    # JSON
    JSON = "json"  # JSON, JSONB, NVARCHAR(MAX)

    # Other
    ARRAY = "array"  # ARRAY (PostgreSQL)
    XML = "xml"  # XML
    UNKNOWN = "unknown"  # Tipo no reconocido
    OTHER = "unknown"  # Alias for UNKNOWN - used by tests


class ColumnMetadata(BaseModel):
    """
    Metadata de una columna de tabla.

    Atributos:
        name: Nombre de la columna
        data_type: Tipo de dato genérico
        native_type: Tipo nativo del dialecto SQL original (ej: "VARCHAR", "NVARCHAR2")
        is_nullable: Si permite NULL
        is_primary_key: Si es parte de la primary key
        is_foreign_key: Si es foreign key
        is_unique: Si tiene constraint UNIQUE
        is_auto_increment: Si tiene auto-increment/SERIAL/IDENTITY
        default_value: Valor por defecto (puede ser expresión SQL)
        max_length: Longitud máxima (para strings)
        numeric_precision: Precisión (para DECIMAL/NUMERIC)
        numeric_scale: Escala (para DECIMAL/NUMERIC)
        character_set: Character set (para strings)
        collation: Collation (para strings)
        ordinal_position: Posición de la columna en la tabla (1-indexed)
        description: Comentario/descripción de la columna
    """

    name: str = Field(..., min_length=1, max_length=128)
    data_type: DataType
    native_type: str = Field(..., description="Tipo nativo del dialecto SQL")

    # Constraints
    is_nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    is_unique: bool = False
    is_auto_increment: bool = False

    # Default value
    default_value: Optional[str] = None

    # Type-specific attributes
    max_length: Optional[int] = Field(None, ge=0, description="Para tipos string")
    numeric_precision: Optional[int] = Field(None, ge=0, description="Para tipos numéricos")
    numeric_scale: Optional[int] = Field(None, ge=0, description="Para tipos numéricos")

    # Character set and collation
    character_set: Optional[str] = None
    collation: Optional[str] = None

    # ENUM values (for ENUM types)
    enum_values: Optional[List[str]] = Field(
        default=None, description="Valores permitidos para tipos ENUM"
    )

    # Metadata
    ordinal_position: int = Field(..., ge=1, description="Posición en la tabla")
    description: Optional[str] = None

    class Config:
        use_enum_values = True

    @property
    def column_name(self) -> str:
        """Alias for name - used by tests"""
        return self.name

    def to_dict(self) -> dict[str, Any]:
        """Convierte a dict para serialización/comparación"""
        return self.model_dump(exclude_none=True)

    def get_full_type_definition(self) -> str:
        """
        Retorna la definición completa del tipo con precisión/escala.

        Ejemplos:
        - VARCHAR(255)
        - DECIMAL(10,2)
        - INTEGER
        """
        if self.data_type == DataType.STRING and self.max_length:
            return f"{self.native_type}({self.max_length})"
        elif self.data_type == DataType.DECIMAL and self.numeric_precision:
            if self.numeric_scale:
                return f"{self.native_type}({self.numeric_precision},{self.numeric_scale})"
            return f"{self.native_type}({self.numeric_precision})"
        else:
            return self.native_type

    def is_compatible_with(self, other: "ColumnMetadata") -> bool:
        """
        Verifica si esta columna es compatible con otra (para migración).

        Compatible significa:
        - Mismo tipo genérico
        - Si es string, longitud suficiente
        - Si es decimal, precisión/escala suficiente
        - Nullability compatible
        """
        # Mismo tipo genérico
        if self.data_type != other.data_type:
            return False

        # Si el target no permite NULL pero el source sí, no compatible
        if not self.is_nullable and other.is_nullable:
            return False

        # Verificar longitud para strings
        if self.data_type == DataType.STRING:
            if self.max_length and other.max_length:
                if self.max_length < other.max_length:
                    return False

        # Verificar precisión para decimales
        if self.data_type == DataType.DECIMAL:
            if self.numeric_precision and other.numeric_precision:
                if self.numeric_precision < other.numeric_precision:
                    return False
            if self.numeric_scale and other.numeric_scale:
                if self.numeric_scale < other.numeric_scale:
                    return False

        return True
