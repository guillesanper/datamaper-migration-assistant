"""
Type Mappers

Convierte tipos SQL nativos de cada dialecto a tipos genéricos DataType.

Esto permite:
- Comparar schemas entre diferentes BDs
- Generar scripts de migración con mapeo correcto de tipos
- Detectar incompatibilidades de tipos
"""

from typing import Optional, Tuple, Type

from app.models.db_metadata import DataType


class TypeMapper:
    """Base class for type mapping"""

    @staticmethod
    def map_to_generic(native_type: str) -> DataType:
        """
        Mapea un tipo SQL nativo a DataType genérico.

        Args:
            native_type: Tipo nativo (ej: "VARCHAR", "INT", "TIMESTAMP")

        Returns:
            DataType genérico

        Note:
            El tipo nativo debe estar en mayúsculas y sin parámetros.
            Ej: "VARCHAR" no "VARCHAR(255)"
        """
        raise NotImplementedError

    @staticmethod
    def map_to_standard(native_type: str) -> DataType:
        """Alias for map_to_generic - used by adapters for compatibility"""
        raise NotImplementedError

    @staticmethod
    def extract_type_name(full_type: str) -> str:
        """
        Extrae el nombre del tipo sin parámetros.

        Args:
            full_type: Tipo completo (ej: "VARCHAR(255)", "DECIMAL(10,2)")

        Returns:
            Nombre del tipo en mayúsculas (ej: "VARCHAR", "DECIMAL")

        Examples:
            >>> TypeMapper.extract_type_name("VARCHAR(255)")
            'VARCHAR'
            >>> TypeMapper.extract_type_name("DECIMAL(10, 2)")
            'DECIMAL'
            >>> TypeMapper.extract_type_name("INTEGER")
            'INTEGER'
        """
        # Remover parámetros y espacios
        type_name = full_type.split("(")[0].strip().upper()
        return type_name

    @staticmethod
    def extract_type_params(full_type: str) -> Optional[Tuple]:
        """
        Extrae los parámetros de un tipo.

        Args:
            full_type: Tipo completo (ej: "VARCHAR(255)", "DECIMAL(10,2)")

        Returns:
            Tupla con parámetros o None si no tiene

        Examples:
            >>> TypeMapper.extract_type_params("VARCHAR(255)")
            (255,)
            >>> TypeMapper.extract_type_params("DECIMAL(10, 2)")
            (10, 2)
            >>> TypeMapper.extract_type_params("INTEGER")
            None
        """
        if "(" not in full_type:
            return None

        # Extraer contenido entre paréntesis
        params_str = full_type.split("(")[1].split(")")[0]
        params = tuple(int(p.strip()) for p in params_str.split(","))
        return params


class PostgreSQLTypeMapper(TypeMapper):
    """Type mapper para PostgreSQL"""

    # Mapeo de tipos PostgreSQL a tipos genéricos
    TYPE_MAP = {
        # Strings
        "CHARACTER VARYING": DataType.STRING,
        "VARCHAR": DataType.STRING,
        "CHARACTER": DataType.CHAR,
        "CHAR": DataType.CHAR,
        "TEXT": DataType.TEXT,
        "BPCHAR": DataType.CHAR,  # Internal name for CHAR
        # Numbers
        "INTEGER": DataType.INTEGER,
        "INT": DataType.INTEGER,
        "INT4": DataType.INTEGER,
        "BIGINT": DataType.BIGINT,
        "INT8": DataType.BIGINT,
        "SMALLINT": DataType.SMALLINT,
        "INT2": DataType.SMALLINT,
        "DECIMAL": DataType.DECIMAL,
        "NUMERIC": DataType.DECIMAL,
        "REAL": DataType.FLOAT,
        "FLOAT4": DataType.FLOAT,
        "DOUBLE PRECISION": DataType.DOUBLE,
        "FLOAT8": DataType.DOUBLE,
        "FLOAT": DataType.DOUBLE,
        "MONEY": DataType.DECIMAL,
        # Boolean
        "BOOLEAN": DataType.BOOLEAN,
        "BOOL": DataType.BOOLEAN,
        # Date/Time
        "DATE": DataType.DATE,
        "TIME": DataType.TIME,
        "TIME WITHOUT TIME ZONE": DataType.TIME,
        "TIME WITH TIME ZONE": DataType.TIME,
        "TIMESTAMP": DataType.TIMESTAMP,
        "TIMESTAMP WITHOUT TIME ZONE": DataType.TIMESTAMP,
        "TIMESTAMP WITH TIME ZONE": DataType.TIMESTAMP,
        "TIMESTAMPTZ": DataType.TIMESTAMP,
        # Binary
        "BYTEA": DataType.BINARY,
        # UUID
        "UUID": DataType.UUID,
        # JSON
        "JSON": DataType.JSON,
        "JSONB": DataType.JSON,
        # Array
        "ARRAY": DataType.ARRAY,
        # XML
        "XML": DataType.XML,
        # Special PostgreSQL types que no tienen equivalente directo
        "SERIAL": DataType.INTEGER,  # Auto-increment integer
        "BIGSERIAL": DataType.BIGINT,  # Auto-increment bigint
        "SMALLSERIAL": DataType.SMALLINT,  # Auto-increment smallint
        "INTERVAL": DataType.STRING,  # Time interval -> string por simplicidad
        "POINT": DataType.STRING,  # Geometric types -> string
        "LINE": DataType.STRING,
        "POLYGON": DataType.STRING,
        "CIDR": DataType.UNKNOWN,  # Network types -> unknown (no direct equivalent)
        "INET": DataType.UNKNOWN,
        "MACADDR": DataType.STRING,
    }

    @staticmethod
    def map_to_generic(native_type: str) -> DataType:
        """Mapea tipo PostgreSQL a genérico"""
        type_name = PostgreSQLTypeMapper.extract_type_name(native_type).upper()
        return PostgreSQLTypeMapper.TYPE_MAP.get(type_name, DataType.UNKNOWN)

    @staticmethod
    def map_to_standard(native_type: str) -> DataType:
        """Alias for map_to_generic"""
        return PostgreSQLTypeMapper.map_to_generic(native_type)


class MySQLTypeMapper(TypeMapper):
    """Type mapper para MySQL/MariaDB"""

    TYPE_MAP = {
        # Strings
        "VARCHAR": DataType.STRING,
        "CHAR": DataType.CHAR,
        "TEXT": DataType.TEXT,
        "TINYTEXT": DataType.TEXT,
        "MEDIUMTEXT": DataType.TEXT,
        "LONGTEXT": DataType.TEXT,
        # Numbers
        "INT": DataType.INTEGER,
        "INTEGER": DataType.INTEGER,
        "BIGINT": DataType.BIGINT,
        "SMALLINT": DataType.SMALLINT,
        "TINYINT": DataType.SMALLINT,  # Note: TINYINT(1) se usa para boolean
        "MEDIUMINT": DataType.INTEGER,
        "DECIMAL": DataType.DECIMAL,
        "NUMERIC": DataType.DECIMAL,
        "FLOAT": DataType.FLOAT,
        "DOUBLE": DataType.DOUBLE,
        "REAL": DataType.DOUBLE,
        # Boolean (MySQL no tiene tipo boolean nativo, usa TINYINT(1))
        "BOOLEAN": DataType.BOOLEAN,
        "BOOL": DataType.BOOLEAN,
        # Date/Time
        "DATE": DataType.DATE,
        "TIME": DataType.TIME,
        "DATETIME": DataType.DATETIME,
        "TIMESTAMP": DataType.TIMESTAMP,
        "YEAR": DataType.INTEGER,
        # Binary
        "BINARY": DataType.BINARY,
        "VARBINARY": DataType.BINARY,
        "BLOB": DataType.BINARY,
        "TINYBLOB": DataType.BINARY,
        "MEDIUMBLOB": DataType.BINARY,
        "LONGBLOB": DataType.BINARY,
        # JSON
        "JSON": DataType.JSON,
        # Enum and Set (tratados como string)
        "ENUM": DataType.STRING,
        "SET": DataType.STRING,
        # Spatial types
        "GEOMETRY": DataType.BINARY,
        "POINT": DataType.BINARY,
        "LINESTRING": DataType.BINARY,
        "POLYGON": DataType.BINARY,
    }

    @staticmethod
    def map_to_generic(native_type: str) -> DataType:
        """Mapea tipo MySQL a genérico"""
        type_name = MySQLTypeMapper.extract_type_name(native_type).upper()

        # Caso especial: TINYINT(1) es boolean en MySQL
        if type_name == "TINYINT" and "(1)" in native_type:
            return DataType.BOOLEAN

        return MySQLTypeMapper.TYPE_MAP.get(type_name, DataType.UNKNOWN)

    @staticmethod
    def map_to_standard(native_type: str) -> DataType:
        """Alias for map_to_generic"""
        return MySQLTypeMapper.map_to_generic(native_type)


class SQLServerTypeMapper(TypeMapper):
    """Type mapper para SQL Server"""

    TYPE_MAP = {
        # Strings
        "VARCHAR": DataType.STRING,
        "NVARCHAR": DataType.STRING,
        "CHAR": DataType.CHAR,
        "NCHAR": DataType.CHAR,
        "TEXT": DataType.TEXT,
        "NTEXT": DataType.TEXT,
        # Numbers
        "INT": DataType.INTEGER,
        "INTEGER": DataType.INTEGER,
        "BIGINT": DataType.BIGINT,
        "SMALLINT": DataType.SMALLINT,
        "TINYINT": DataType.SMALLINT,
        "DECIMAL": DataType.DECIMAL,
        "NUMERIC": DataType.DECIMAL,
        "MONEY": DataType.DECIMAL,
        "SMALLMONEY": DataType.DECIMAL,
        "FLOAT": DataType.DOUBLE,
        "REAL": DataType.FLOAT,
        # Boolean
        "BIT": DataType.BOOLEAN,
        # Date/Time
        "DATE": DataType.DATE,
        "TIME": DataType.TIME,
        "DATETIME": DataType.DATETIME,
        "DATETIME2": DataType.DATETIME,
        "SMALLDATETIME": DataType.DATETIME,
        "DATETIMEOFFSET": DataType.TIMESTAMP,
        # Binary
        "BINARY": DataType.BINARY,
        "VARBINARY": DataType.BINARY,
        "IMAGE": DataType.BINARY,
        # UUID
        "UNIQUEIDENTIFIER": DataType.UUID,
        # XML
        "XML": DataType.XML,
        # Spatial types
        "GEOGRAPHY": DataType.BINARY,
        "GEOMETRY": DataType.BINARY,
    }

    @staticmethod
    def map_to_generic(native_type: str) -> DataType:
        """Mapea tipo SQL Server a genérico"""
        type_name = SQLServerTypeMapper.extract_type_name(native_type).upper()
        return SQLServerTypeMapper.TYPE_MAP.get(type_name, DataType.UNKNOWN)

    @staticmethod
    def map_to_standard(native_type: str) -> DataType:
        """Alias for map_to_generic"""
        return SQLServerTypeMapper.map_to_generic(native_type)


class OracleTypeMapper(TypeMapper):
    """Type mapper para Oracle"""

    TYPE_MAP = {
        # Strings
        "VARCHAR2": DataType.STRING,
        "VARCHAR": DataType.STRING,
        "CHAR": DataType.CHAR,
        "NCHAR": DataType.CHAR,
        "NVARCHAR2": DataType.STRING,
        "CLOB": DataType.TEXT,
        "NCLOB": DataType.TEXT,
        "LONG": DataType.TEXT,
        # Numbers
        "NUMBER": DataType.DECIMAL,  # Oracle's universal numeric type
        "INTEGER": DataType.INTEGER,
        "INT": DataType.INTEGER,
        "SMALLINT": DataType.SMALLINT,
        "FLOAT": DataType.DOUBLE,
        "BINARY_FLOAT": DataType.FLOAT,
        "BINARY_DOUBLE": DataType.DOUBLE,
        # Date/Time
        "DATE": DataType.DATETIME,  # Oracle DATE includes time
        "TIMESTAMP": DataType.TIMESTAMP,
        "TIMESTAMP WITH TIME ZONE": DataType.TIMESTAMP,
        "TIMESTAMP WITH LOCAL TIME ZONE": DataType.TIMESTAMP,
        # Binary
        "RAW": DataType.BINARY,
        "LONG RAW": DataType.BINARY,
        "BLOB": DataType.BINARY,
        # XML
        "XMLTYPE": DataType.XML,
        # ROW ID
        "ROWID": DataType.STRING,
        "UROWID": DataType.STRING,
    }

    @staticmethod
    def map_to_generic(native_type: str) -> DataType:
        """Mapea tipo Oracle a genérico"""
        type_name = OracleTypeMapper.extract_type_name(native_type).upper()

        # Caso especial: NUMBER puede ser INTEGER, BIGINT o DECIMAL según precisión
        if type_name == "NUMBER":
            params = OracleTypeMapper.extract_type_params(native_type)
            if params:
                precision, scale = params if len(params) == 2 else (params[0], 0)
                if scale == 0:  # Sin decimales
                    if precision <= 10:
                        return DataType.INTEGER
                    elif precision <= 19:
                        return DataType.BIGINT
                return DataType.DECIMAL
            return DataType.DECIMAL  # NUMBER sin parámetros = DECIMAL

        return OracleTypeMapper.TYPE_MAP.get(type_name, DataType.UNKNOWN)

    @staticmethod
    def map_to_standard(native_type: str) -> DataType:
        """Alias for map_to_generic"""
        return OracleTypeMapper.map_to_generic(native_type)


# Factory function para obtener el mapper correcto
def get_type_mapper(dialect: str) -> Type[TypeMapper]:
    """
    Retorna el type mapper apropiado para un dialecto.

    Args:
        dialect: 'postgresql', 'mysql', 'sqlserver', 'oracle'

    Returns:
        Instancia del TypeMapper apropiado

    Raises:
        ValueError: Si el dialecto no es soportado
    """
    mappers = {
        "postgresql": PostgreSQLTypeMapper,
        "mysql": MySQLTypeMapper,
        "mariadb": MySQLTypeMapper,  # MariaDB usa los mismos tipos que MySQL
        "sqlserver": SQLServerTypeMapper,
        "oracle": OracleTypeMapper,
    }

    dialect_lower = dialect.lower()
    if dialect_lower not in mappers:
        raise ValueError(
            f"Unsupported dialect: {dialect}. " f"Supported dialects: {', '.join(mappers.keys())}"
        )

    return mappers[dialect_lower]
