"""
Unit tests for app.utils.db_adapters.oracle_adapter module

Tests for OracleAdapter with mocked oracledb:
- Connection management (connect, disconnect, test_connection)
- Schema introspection (list_schemas, list_tables)
- Column metadata (get_table_columns with type mapping)
- Constraints (get_primary_keys, get_foreign_keys, get_unique_constraints, get_check_constraints)
- Indexes (get_indexes)
- Statistics (get_table_statistics)
- Error handling
"""

from unittest.mock import MagicMock, Mock, call, patch

import pytest

from app.models.db_metadata import DataType, IndexType, TableType
from app.utils.db_adapters.exceptions import (
    DBAuthenticationError,
    DBConnectionError,
    DBMetadataNotFoundError,
    DBQueryExecutionError,
)
from app.utils.db_adapters.oracle_adapter import OracleAdapter

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def valid_config_service_name():
    """Valid Oracle connection config with service_name"""
    return {
        "host": "localhost",
        "port": 1521,
        "database": "ORCL",
        "user": "testuser",
        "password": "testpass",
        "service_name": "ORCL",
    }


@pytest.fixture
def valid_config_sid():
    """Valid Oracle connection config with SID"""
    return {
        "host": "localhost",
        "port": 1521,
        "database": "ORCL",
        "user": "testuser",
        "password": "testpass",
        "sid": "ORCL",
    }


@pytest.fixture
def adapter(valid_config_service_name):
    """OracleAdapter instance with valid config"""
    return OracleAdapter(valid_config_service_name)


# Mock oracledb.DatabaseError
class MockDatabaseError(Exception):
    def __init__(self, code, message):
        self.args = [Mock(code=code, message=message)]


# ============================================================================
# TEST: Connection Management
# ============================================================================


class TestConnection:
    """Tests for connection management"""

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_connect_success_with_service_name(self, mock_connect, adapter):
        """Test successful connection with service_name (TLS verificado por defecto)"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        adapter.connect()

        assert adapter.is_connected is True
        assert adapter.connection == mock_conn
        kwargs = mock_connect.call_args.kwargs
        assert kwargs["host"] == "localhost"
        assert kwargs["port"] == 1521
        assert kwargs["service_name"] == "ORCL"
        assert kwargs["protocol"] == "tcps"
        assert kwargs["ssl_server_dn_match"] is True
        # python-oracledb >= 2 rechaza `encoding` con TypeError
        assert "encoding" not in kwargs

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_connect_success_with_sid(self, mock_connect, valid_config_sid):
        """Test successful connection with SID"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        adapter = OracleAdapter(valid_config_sid)
        adapter.connect()

        assert adapter.is_connected is True
        assert mock_connect.call_args.kwargs["sid"] == "ORCL"

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_connect_without_tls(self, mock_connect, valid_config_sid):
        adapter = OracleAdapter({**valid_config_sid, "ssl_mode": "disable"})
        adapter.connect()

        assert mock_connect.call_args.kwargs["protocol"] == "tcp"
        assert "ssl_server_dn_match" not in mock_connect.call_args.kwargs

    def test_connect_accepted_by_installed_oracledb(self, valid_config_sid):
        """Los kwargs que se pasan existen en la versión instalada (sin mocks de firma)"""
        import oracledb

        adapter = OracleAdapter({**valid_config_sid, "port": 1, "timeout": 5})
        with pytest.raises(DBConnectionError) as exc_info:
            adapter.connect()
        assert "unexpected keyword" not in str(exc_info.value)
        assert oracledb.__version__

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.DatabaseError", MockDatabaseError)
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_connect_authentication_error(self, mock_connect, mock_makedsn, adapter):
        """Test authentication error raises DBAuthenticationError"""
        mock_makedsn.return_value = "dsn"
        # ORA-01017: invalid username/password
        mock_connect.side_effect = MockDatabaseError(1017, "Invalid username/password")

        with pytest.raises(DBAuthenticationError) as exc_info:
            adapter.connect()

        assert "Invalid credentials" in str(exc_info.value)

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.DatabaseError", MockDatabaseError)
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_connect_no_listener_error(self, mock_connect, mock_makedsn, adapter):
        """Test no listener error raises DBConnectionError"""
        mock_makedsn.return_value = "dsn"
        # ORA-12541: TNS:no listener
        mock_connect.side_effect = MockDatabaseError(12541, "TNS:no listener")

        with pytest.raises(DBConnectionError) as exc_info:
            adapter.connect()

        assert "Cannot connect" in str(exc_info.value)

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_disconnect(self, mock_connect, mock_makedsn, adapter):
        """Test disconnect closes connection"""
        mock_makedsn.return_value = "dsn"
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        adapter.connect()
        adapter.disconnect()

        mock_conn.close.assert_called_once()
        assert adapter.is_connected is False

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_test_connection_success(self, mock_connect, mock_makedsn, adapter):
        """Test successful connection test"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        result = adapter.test_connection()

        assert result is True
        mock_cursor.execute.assert_called_with("SELECT 1 FROM DUAL")
        mock_conn.close.assert_called_once()

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_context_manager(self, mock_connect, mock_makedsn, valid_config_service_name):
        """Test context manager properly manages connection"""
        mock_makedsn.return_value = "dsn"
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with OracleAdapter(valid_config_service_name) as adapter:
            assert adapter.is_connected is True

        mock_conn.close.assert_called_once()


# ============================================================================
# TEST: list_schemas()
# ============================================================================


class TestListSchemas:
    """Tests for list_schemas() method"""

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_list_schemas_returns_list(self, mock_connect, mock_makedsn, adapter):
        """Test list_schemas returns list of schema names"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("APP_SCHEMA",),
            ("SALES_SCHEMA",),
            ("HR_SCHEMA",),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        schemas = adapter.get_schemas()

        assert schemas == ["APP_SCHEMA", "SALES_SCHEMA", "HR_SCHEMA"]
        mock_cursor.execute.assert_called_once()

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_list_schemas_filters_system_schemas(self, mock_connect, mock_makedsn, adapter):
        """Test that system schemas are filtered in query"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("APP_SCHEMA",)]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        adapter.get_schemas()

        # Verify query filters system schemas
        query = mock_cursor.execute.call_args[0][0]
        assert "NOT IN" in query
        assert "SYS" in query
        assert "SYSTEM" in query


# ============================================================================
# TEST: list_tables()
# ============================================================================


class TestListTables:
    """Tests for list_tables() method"""

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_list_tables_returns_metadata(self, mock_connect, mock_makedsn, adapter):
        """Test list_tables returns TableMetadata objects"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("APP_SCHEMA", "USERS", "USERS_TS", 1000),
            ("APP_SCHEMA", "PRODUCTS", "PRODUCTS_TS", 500),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        tables = adapter.get_tables("APP_SCHEMA")

        assert len(tables) == 2
        assert tables[0].schema_name == "APP_SCHEMA"
        assert tables[0].table_name == "USERS"
        assert tables[0].table_type == TableType.TABLE

        assert tables[1].table_name == "PRODUCTS"

        # Verify query uses uppercase schema name
        mock_cursor.execute.assert_called_once()
        assert mock_cursor.execute.call_args[1] == {"schema_name": "APP_SCHEMA"}

    def test_list_tables_invalid_schema_name(self, adapter):
        """Test get_tables validates schema name"""
        with pytest.raises(ValueError):
            adapter.get_tables("invalid; DROP TABLE")


# ============================================================================
# TEST: get_table_columns()
# ============================================================================


class TestGetTableColumns:
    """Tests for get_table_columns() method"""

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_table_columns_returns_metadata(self, mock_connect, mock_makedsn, adapter):
        """Test get_table_columns returns ColumnMetadata objects"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            # column_name, data_type, length, precision, scale, nullable, default, position, is_pk
            ("ID", "NUMBER", None, 10, 0, "N", None, 1, "Y"),
            ("USERNAME", "VARCHAR2", 50, None, None, "N", None, 2, "N"),
            ("BALANCE", "NUMBER", None, 12, 2, "Y", "0", 3, "N"),
            ("IS_ACTIVE", "NUMBER", None, 1, 0, "N", "1", 4, "N"),
            ("CREATED_AT", "TIMESTAMP(6)", None, None, None, "N", "SYSDATE", 5, "N"),
            ("DESCRIPTION", "CLOB", None, None, None, "Y", None, 6, "N"),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        columns = adapter.get_columns("USERS", "APP_SCHEMA")

        assert len(columns) == 6

        # Test ID column (NUMBER with scale 0 → INTEGER, primary key)
        id_col = columns[0]
        assert id_col.column_name == "ID"
        assert id_col.data_type == DataType.INTEGER
        assert id_col.is_nullable is False
        assert id_col.is_primary_key is True
        assert id_col.ordinal_position == 1
        assert id_col.native_type == "NUMBER"

        # Test USERNAME column (VARCHAR2 with length)
        username_col = columns[1]
        assert username_col.column_name == "USERNAME"
        assert username_col.data_type == DataType.VARCHAR
        assert username_col.max_length == 50
        assert username_col.is_nullable is False

        # Test BALANCE column (NUMBER with scale → DECIMAL)
        balance_col = columns[2]
        assert balance_col.column_name == "BALANCE"
        assert balance_col.data_type == DataType.DECIMAL
        assert balance_col.numeric_precision == 12
        assert balance_col.numeric_scale == 2
        assert balance_col.is_nullable is True

        # Test IS_ACTIVE column (NUMBER(1,0) → BOOLEAN by convention)
        is_active_col = columns[3]
        assert is_active_col.column_name == "IS_ACTIVE"
        assert is_active_col.data_type == DataType.BOOLEAN

        # Test CREATED_AT column (TIMESTAMP)
        created_col = columns[4]
        assert created_col.column_name == "CREATED_AT"
        assert created_col.data_type == DataType.TIMESTAMP

        # Test DESCRIPTION column (CLOB → TEXT)
        desc_col = columns[5]
        assert desc_col.column_name == "DESCRIPTION"
        assert desc_col.data_type == DataType.TEXT

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_table_columns_table_not_found(self, mock_connect, mock_makedsn, adapter):
        """Test get_table_columns with non-existent table"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()

        with pytest.raises(DBMetadataNotFoundError) as exc_info:
            adapter.get_columns("NONEXISTENT", "APP_SCHEMA")

        assert "not found" in str(exc_info.value)

    def test_get_table_columns_validates_names(self, adapter):
        """Test get_columns validates schema and table names"""
        with pytest.raises(ValueError):
            adapter.get_columns("users", "invalid; DROP")

        with pytest.raises(ValueError):
            adapter.get_columns("invalid; DROP", "schema")


# ============================================================================
# TEST: get_primary_keys()
# ============================================================================


class TestGetPrimaryKeys:
    """Tests for get_primary_keys() method"""

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_primary_keys_single_column(self, mock_connect, mock_makedsn, adapter):
        """Test get_primary_keys with single-column PK"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("PK_USERS", "ID", 1),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        pks = adapter.get_primary_keys("APP_SCHEMA", "USERS")

        assert len(pks) == 1
        assert pks[0].constraint_name == "PK_USERS"
        assert pks[0].table_name == "USERS"
        assert pks[0].column_names == ["ID"]

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_primary_keys_composite(self, mock_connect, mock_makedsn, adapter):
        """Test get_primary_keys with composite PK"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("PK_ORDER_ITEMS", "ORDER_ID", 1),
            ("PK_ORDER_ITEMS", "PRODUCT_ID", 2),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        pks = adapter.get_primary_keys("APP_SCHEMA", "ORDER_ITEMS")

        assert len(pks) == 1
        assert pks[0].column_names == ["ORDER_ID", "PRODUCT_ID"]

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_primary_keys_none(self, mock_connect, mock_makedsn, adapter):
        """Test get_primary_keys with no primary key"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        pks = adapter.get_primary_keys("APP_SCHEMA", "LOGS")

        assert pks == []


# ============================================================================
# TEST: get_foreign_keys()
# ============================================================================


class TestGetForeignKeys:
    """Tests for get_foreign_keys() method"""

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_foreign_keys_single_column(self, mock_connect, mock_makedsn, adapter):
        """Test get_foreign_keys with single-column FK"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("FK_PRODUCTS_CATEGORY", "CATEGORY_ID", "CATEGORIES", "ID", "CASCADE", 1),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        fks = adapter.get_foreign_keys("APP_SCHEMA", "PRODUCTS")

        assert len(fks) == 1
        assert fks[0].constraint_name == "FK_PRODUCTS_CATEGORY"
        assert fks[0].column_names == ["CATEGORY_ID"]
        assert fks[0].referenced_table == "CATEGORIES"
        assert fks[0].referenced_columns == ["ID"]
        assert fks[0].on_delete == "CASCADE"
        assert fks[0].on_update is None  # Oracle doesn't support ON UPDATE

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_foreign_keys_none(self, mock_connect, mock_makedsn, adapter):
        """Test get_foreign_keys with no foreign keys"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        fks = adapter.get_foreign_keys("APP_SCHEMA", "CATEGORIES")

        assert fks == []


# ============================================================================
# TEST: get_unique_constraints()
# ============================================================================


class TestGetUniqueConstraints:
    """Tests for get_unique_constraints() method"""

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_unique_constraints(self, mock_connect, mock_makedsn, adapter):
        """Test get_unique_constraints returns unique constraints"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("UQ_USERS_EMAIL", "EMAIL", 1),
            ("UQ_USERS_USERNAME", "USERNAME", 1),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        uniques = adapter.get_unique_constraints("APP_SCHEMA", "USERS")

        assert len(uniques) == 2
        assert uniques[0].constraint_name == "UQ_USERS_EMAIL"
        assert uniques[0].column_names == ["EMAIL"]
        assert uniques[1].constraint_name == "UQ_USERS_USERNAME"


# ============================================================================
# TEST: get_check_constraints()
# ============================================================================


class TestGetCheckConstraints:
    """Tests for get_check_constraints() method"""

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_check_constraints(self, mock_connect, mock_makedsn, adapter):
        """Test get_check_constraints returns check constraints"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("CK_USERS_AGE", "AGE >= 18 AND AGE <= 120"),
            ("CK_USERS_BALANCE", "BALANCE >= 0"),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        checks = adapter.get_check_constraints("APP_SCHEMA", "USERS")

        assert len(checks) == 2
        assert checks[0].constraint_name == "CK_USERS_AGE"
        assert "AGE" in checks[0].check_clause
        assert checks[1].constraint_name == "CK_USERS_BALANCE"

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_check_constraints_filters_not_null(self, mock_connect, mock_makedsn, adapter):
        """Test that NOT NULL constraints are filtered out"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("SYS_C001", "USERNAME IS NOT NULL"),
            ("CK_USERS_AGE", "AGE >= 18"),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        checks = adapter.get_check_constraints("APP_SCHEMA", "USERS")

        # Should only return the age constraint, not the NOT NULL
        assert len(checks) == 1
        assert checks[0].constraint_name == "CK_USERS_AGE"


# ============================================================================
# TEST: get_indexes()
# ============================================================================


class TestGetIndexes:
    """Tests for get_indexes() method"""

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_indexes(self, mock_connect, mock_makedsn, adapter):
        """Test get_indexes returns index metadata"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("IDX_USERS_EMAIL", "UNIQUE", "EMAIL", 1),
            ("IDX_USERS_CREATED", "NONUNIQUE", "CREATED_AT", 1),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        indexes = adapter.get_indexes("APP_SCHEMA", "USERS")

        assert len(indexes) == 2

        # Unique index
        assert indexes[0].index_name == "IDX_USERS_EMAIL"
        assert indexes[0].is_unique is True
        assert indexes[0].column_names == ["EMAIL"]
        assert indexes[0].index_type == IndexType.BTREE

        # Non-unique index
        assert indexes[1].index_name == "IDX_USERS_CREATED"
        assert indexes[1].is_unique is False
        assert indexes[1].index_type == IndexType.BTREE

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_indexes_filters_system_indexes(self, mock_connect, mock_makedsn, adapter):
        """Test that system-generated indexes are filtered out"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("SYS_C001234", "UNIQUE", "ID", 1),
            ("IDX_USERS_EMAIL", "UNIQUE", "EMAIL", 1),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        indexes = adapter.get_indexes("APP_SCHEMA", "USERS")

        # Should filter out SYS_ indexes
        assert len(indexes) == 1
        assert indexes[0].index_name == "IDX_USERS_EMAIL"


# ============================================================================
# TEST: get_table_statistics()
# ============================================================================


class TestGetTableStatistics:
    """Tests for get_table_statistics() method"""

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_table_statistics(self, mock_connect, mock_makedsn, adapter):
        """Test get_table_statistics returns statistics"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()

        # First query: get block size
        # Second query: get table stats
        mock_cursor.fetchone.side_effect = [
            ("8192",),  # block size
            (1000, 64000),  # num_rows, total_size
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        stats = adapter.get_table_statistics("APP_SCHEMA", "USERS")

        assert stats.table_name == "USERS"
        assert stats.row_count == 1000
        assert stats.total_size_bytes == 64000

    @patch("app.utils.db_adapters.oracle_adapter.oracledb.makedsn")
    @patch("app.utils.db_adapters.oracle_adapter.oracledb.connect")
    def test_get_table_statistics_empty_table(self, mock_connect, mock_makedsn, adapter):
        """Test get_table_statistics with empty table"""
        mock_makedsn.return_value = "dsn"
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [("8192",), None]  # block size  # no stats

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        stats = adapter.get_table_statistics("APP_SCHEMA", "EMPTY_TABLE")

        assert stats.row_count == 0
        assert stats.total_size_bytes == 0


# ============================================================================
# TEST: Dialect Property
# ============================================================================


class TestDialect:
    """Tests for dialect property"""

    def test_dialect_returns_oracle(self, adapter):
        """Test dialect property returns 'oracle'"""
        assert adapter.dialect == "oracle"


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
