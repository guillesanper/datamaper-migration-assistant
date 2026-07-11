"""
Unit tests for app.utils.db_adapters.type_mappers module

Tests for type mapping between SQL dialects and generic DataType:
- PostgreSQL type mapping
- MySQL type mapping (including TINYINT(1) special case)
- SQL Server type mapping
- Oracle type mapping
- Type name/parameter extraction
"""

import pytest

from app.models.db_metadata import DataType
from app.utils.db_adapters.type_mappers import (
    MySQLTypeMapper,
    OracleTypeMapper,
    PostgreSQLTypeMapper,
    SQLServerTypeMapper,
    TypeMapper,
    get_type_mapper,
)

# ============================================================================
# TEST TypeMapper base class
# ============================================================================


class TestTypeMapper:
    """Tests for TypeMapper base class"""

    def test_extract_type_name_without_params(self):
        """Test: Extract type name without parameters"""
        assert TypeMapper.extract_type_name("VARCHAR") == "VARCHAR"
        assert TypeMapper.extract_type_name("INTEGER") == "INTEGER"
        assert TypeMapper.extract_type_name("text") == "TEXT"

    def test_extract_type_name_with_params(self):
        """Test: Extract type name from types with parameters"""
        assert TypeMapper.extract_type_name("VARCHAR(255)") == "VARCHAR"
        assert TypeMapper.extract_type_name("DECIMAL(10,2)") == "DECIMAL"
        assert TypeMapper.extract_type_name("CHAR(10)") == "CHAR"

    def test_extract_type_params_no_params(self):
        """Test: Extract params from types without parameters"""
        assert TypeMapper.extract_type_params("VARCHAR") is None
        assert TypeMapper.extract_type_params("INTEGER") is None

    def test_extract_type_params_single_param(self):
        """Test: Extract single parameter"""
        assert TypeMapper.extract_type_params("VARCHAR(255)") == (255,)
        assert TypeMapper.extract_type_params("CHAR(10)") == (10,)

    def test_extract_type_params_multiple_params(self):
        """Test: Extract multiple parameters"""
        assert TypeMapper.extract_type_params("DECIMAL(10,2)") == (10, 2)
        assert TypeMapper.extract_type_params("NUMERIC(18, 4)") == (18, 4)


# ============================================================================
# TEST PostgreSQLTypeMapper
# ============================================================================


class TestPostgreSQLTypeMapper:
    """Tests for PostgreSQL type mapping"""

    def test_string_types(self):
        """Test: PostgreSQL string types"""
        assert PostgreSQLTypeMapper.map_to_generic("VARCHAR") == DataType.STRING
        assert PostgreSQLTypeMapper.map_to_generic("CHARACTER VARYING") == DataType.STRING
        assert PostgreSQLTypeMapper.map_to_generic("TEXT") == DataType.TEXT
        assert PostgreSQLTypeMapper.map_to_generic("CHAR") == DataType.CHAR

    def test_integer_types(self):
        """Test: PostgreSQL integer types"""
        assert PostgreSQLTypeMapper.map_to_generic("INTEGER") == DataType.INTEGER
        assert PostgreSQLTypeMapper.map_to_generic("INT") == DataType.INTEGER
        assert PostgreSQLTypeMapper.map_to_generic("INT4") == DataType.INTEGER
        assert PostgreSQLTypeMapper.map_to_generic("BIGINT") == DataType.BIGINT
        assert PostgreSQLTypeMapper.map_to_generic("SMALLINT") == DataType.SMALLINT

    def test_decimal_types(self):
        """Test: PostgreSQL decimal types"""
        assert PostgreSQLTypeMapper.map_to_generic("DECIMAL") == DataType.DECIMAL
        assert PostgreSQLTypeMapper.map_to_generic("NUMERIC") == DataType.DECIMAL
        assert PostgreSQLTypeMapper.map_to_generic("MONEY") == DataType.DECIMAL

    def test_float_types(self):
        """Test: PostgreSQL float types"""
        assert PostgreSQLTypeMapper.map_to_generic("REAL") == DataType.FLOAT
        assert PostgreSQLTypeMapper.map_to_generic("FLOAT4") == DataType.FLOAT
        assert PostgreSQLTypeMapper.map_to_generic("DOUBLE PRECISION") == DataType.DOUBLE
        assert PostgreSQLTypeMapper.map_to_generic("FLOAT8") == DataType.DOUBLE

    def test_boolean_type(self):
        """Test: PostgreSQL boolean type"""
        assert PostgreSQLTypeMapper.map_to_generic("BOOLEAN") == DataType.BOOLEAN
        assert PostgreSQLTypeMapper.map_to_generic("BOOL") == DataType.BOOLEAN

    def test_datetime_types(self):
        """Test: PostgreSQL date/time types"""
        assert PostgreSQLTypeMapper.map_to_generic("DATE") == DataType.DATE
        assert PostgreSQLTypeMapper.map_to_generic("TIME") == DataType.TIME
        assert PostgreSQLTypeMapper.map_to_generic("TIMESTAMP") == DataType.TIMESTAMP
        assert PostgreSQLTypeMapper.map_to_generic("TIMESTAMPTZ") == DataType.TIMESTAMP

    def test_special_types(self):
        """Test: PostgreSQL special types"""
        assert PostgreSQLTypeMapper.map_to_generic("UUID") == DataType.UUID
        assert PostgreSQLTypeMapper.map_to_generic("JSON") == DataType.JSON
        assert PostgreSQLTypeMapper.map_to_generic("JSONB") == DataType.JSON
        assert PostgreSQLTypeMapper.map_to_generic("BYTEA") == DataType.BINARY
        assert PostgreSQLTypeMapper.map_to_generic("XML") == DataType.XML

    def test_serial_types(self):
        """Test: PostgreSQL auto-increment types"""
        assert PostgreSQLTypeMapper.map_to_generic("SERIAL") == DataType.INTEGER
        assert PostgreSQLTypeMapper.map_to_generic("BIGSERIAL") == DataType.BIGINT
        assert PostgreSQLTypeMapper.map_to_generic("SMALLSERIAL") == DataType.SMALLINT

    def test_unknown_type(self):
        """Test: Unknown types return UNKNOWN"""
        assert PostgreSQLTypeMapper.map_to_generic("CUSTOM_TYPE") == DataType.UNKNOWN


# ============================================================================
# TEST MySQLTypeMapper
# ============================================================================


class TestMySQLTypeMapper:
    """Tests for MySQL type mapping"""

    def test_string_types(self):
        """Test: MySQL string types"""
        assert MySQLTypeMapper.map_to_generic("VARCHAR") == DataType.STRING
        assert MySQLTypeMapper.map_to_generic("CHAR") == DataType.CHAR
        assert MySQLTypeMapper.map_to_generic("TEXT") == DataType.TEXT
        assert MySQLTypeMapper.map_to_generic("LONGTEXT") == DataType.TEXT

    def test_integer_types(self):
        """Test: MySQL integer types"""
        assert MySQLTypeMapper.map_to_generic("INT") == DataType.INTEGER
        assert MySQLTypeMapper.map_to_generic("INTEGER") == DataType.INTEGER
        assert MySQLTypeMapper.map_to_generic("BIGINT") == DataType.BIGINT
        assert MySQLTypeMapper.map_to_generic("SMALLINT") == DataType.SMALLINT
        assert MySQLTypeMapper.map_to_generic("MEDIUMINT") == DataType.INTEGER

    def test_tinyint_as_smallint(self):
        """Test: TINYINT without (1) maps to SMALLINT"""
        assert MySQLTypeMapper.map_to_generic("TINYINT") == DataType.SMALLINT
        assert MySQLTypeMapper.map_to_generic("TINYINT(4)") == DataType.SMALLINT

    def test_tinyint_1_as_boolean(self):
        """Test: TINYINT(1) maps to BOOLEAN"""
        assert MySQLTypeMapper.map_to_generic("TINYINT(1)") == DataType.BOOLEAN

    def test_decimal_types(self):
        """Test: MySQL decimal types"""
        assert MySQLTypeMapper.map_to_generic("DECIMAL") == DataType.DECIMAL
        assert MySQLTypeMapper.map_to_generic("NUMERIC") == DataType.DECIMAL

    def test_float_types(self):
        """Test: MySQL float types"""
        assert MySQLTypeMapper.map_to_generic("FLOAT") == DataType.FLOAT
        assert MySQLTypeMapper.map_to_generic("DOUBLE") == DataType.DOUBLE

    def test_datetime_types(self):
        """Test: MySQL date/time types"""
        assert MySQLTypeMapper.map_to_generic("DATE") == DataType.DATE
        assert MySQLTypeMapper.map_to_generic("TIME") == DataType.TIME
        assert MySQLTypeMapper.map_to_generic("DATETIME") == DataType.DATETIME
        assert MySQLTypeMapper.map_to_generic("TIMESTAMP") == DataType.TIMESTAMP

    def test_binary_types(self):
        """Test: MySQL binary types"""
        assert MySQLTypeMapper.map_to_generic("BLOB") == DataType.BINARY
        assert MySQLTypeMapper.map_to_generic("BINARY") == DataType.BINARY

    def test_json_type(self):
        """Test: MySQL JSON type"""
        assert MySQLTypeMapper.map_to_generic("JSON") == DataType.JSON

    def test_enum_and_set(self):
        """Test: MySQL ENUM and SET map to STRING"""
        assert MySQLTypeMapper.map_to_generic("ENUM") == DataType.STRING
        assert MySQLTypeMapper.map_to_generic("SET") == DataType.STRING


# ============================================================================
# TEST SQLServerTypeMapper
# ============================================================================


class TestSQLServerTypeMapper:
    """Tests for SQL Server type mapping"""

    def test_string_types(self):
        """Test: SQL Server string types"""
        assert SQLServerTypeMapper.map_to_generic("VARCHAR") == DataType.STRING
        assert SQLServerTypeMapper.map_to_generic("NVARCHAR") == DataType.STRING
        assert SQLServerTypeMapper.map_to_generic("CHAR") == DataType.CHAR
        assert SQLServerTypeMapper.map_to_generic("TEXT") == DataType.TEXT

    def test_integer_types(self):
        """Test: SQL Server integer types"""
        assert SQLServerTypeMapper.map_to_generic("INT") == DataType.INTEGER
        assert SQLServerTypeMapper.map_to_generic("BIGINT") == DataType.BIGINT
        assert SQLServerTypeMapper.map_to_generic("SMALLINT") == DataType.SMALLINT
        assert SQLServerTypeMapper.map_to_generic("TINYINT") == DataType.SMALLINT

    def test_decimal_types(self):
        """Test: SQL Server decimal types"""
        assert SQLServerTypeMapper.map_to_generic("DECIMAL") == DataType.DECIMAL
        assert SQLServerTypeMapper.map_to_generic("NUMERIC") == DataType.DECIMAL
        assert SQLServerTypeMapper.map_to_generic("MONEY") == DataType.DECIMAL

    def test_datetime_types(self):
        """Test: SQL Server date/time types"""
        assert SQLServerTypeMapper.map_to_generic("DATE") == DataType.DATE
        assert SQLServerTypeMapper.map_to_generic("TIME") == DataType.TIME
        assert SQLServerTypeMapper.map_to_generic("DATETIME") == DataType.DATETIME
        assert SQLServerTypeMapper.map_to_generic("DATETIME2") == DataType.DATETIME

    def test_uniqueidentifier_as_uuid(self):
        """Test: UNIQUEIDENTIFIER maps to UUID"""
        assert SQLServerTypeMapper.map_to_generic("UNIQUEIDENTIFIER") == DataType.UUID

    def test_binary_types(self):
        """Test: SQL Server binary types"""
        assert SQLServerTypeMapper.map_to_generic("BINARY") == DataType.BINARY
        assert SQLServerTypeMapper.map_to_generic("VARBINARY") == DataType.BINARY


# ============================================================================
# TEST OracleTypeMapper
# ============================================================================


class TestOracleTypeMapper:
    """Tests for Oracle type mapping"""

    def test_string_types(self):
        """Test: Oracle string types"""
        assert OracleTypeMapper.map_to_generic("VARCHAR2") == DataType.STRING
        assert OracleTypeMapper.map_to_generic("CHAR") == DataType.CHAR
        assert OracleTypeMapper.map_to_generic("CLOB") == DataType.TEXT

    def test_number_without_params(self):
        """Test: NUMBER without parameters maps to DECIMAL"""
        assert OracleTypeMapper.map_to_generic("NUMBER") == DataType.DECIMAL

    def test_datetime_types(self):
        """Test: Oracle date/time types"""
        assert OracleTypeMapper.map_to_generic("DATE") == DataType.DATETIME
        assert OracleTypeMapper.map_to_generic("TIMESTAMP") == DataType.TIMESTAMP

    def test_binary_types(self):
        """Test: Oracle binary types"""
        assert OracleTypeMapper.map_to_generic("BLOB") == DataType.BINARY
        assert OracleTypeMapper.map_to_generic("RAW") == DataType.BINARY


# ============================================================================
# TEST get_type_mapper() factory
# ============================================================================


class TestGetTypeMapper:
    """Tests for get_type_mapper() factory function"""

    def test_postgresql_mapper(self):
        """Test: Get PostgreSQL mapper"""
        mapper = get_type_mapper("postgresql")
        assert mapper == PostgreSQLTypeMapper

    def test_mysql_mapper(self):
        """Test: Get MySQL mapper"""
        mapper = get_type_mapper("mysql")
        assert mapper == MySQLTypeMapper

    def test_sqlserver_mapper(self):
        """Test: Get SQL Server mapper"""
        mapper = get_type_mapper("sqlserver")
        assert mapper == SQLServerTypeMapper

    def test_oracle_mapper(self):
        """Test: Get Oracle mapper"""
        mapper = get_type_mapper("oracle")
        assert mapper == OracleTypeMapper

    def test_unknown_dialect_raises_error(self):
        """Test: Unknown dialect raises ValueError"""
        with pytest.raises(ValueError, match="Unsupported dialect"):
            get_type_mapper("unknown_dialect")

    def test_case_insensitive(self):
        """Test: Dialect name is case-insensitive"""
        assert get_type_mapper("POSTGRESQL") == PostgreSQLTypeMapper
        assert get_type_mapper("MySQL") == MySQLTypeMapper
