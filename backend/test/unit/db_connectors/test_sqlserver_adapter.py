"""
Unit tests for app.utils.db_adapters.sqlserver_adapter module

Tests for SQLServerAdapter with mocked pyodbc:
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

from app.models.db_metadata import ConstraintType, DataType, IndexType, TableType
from app.utils.db_adapters.exceptions import (
    DBAuthenticationError,
    DBConnectionError,
    DBMetadataNotFoundError,
    DBQueryExecutionError,
    DBTimeoutError,
)
from app.utils.db_adapters.sqlserver_adapter import SQLServerAdapter

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def valid_config():
    """Valid SQL Server connection config"""
    return {
        "host": "localhost",
        "port": 1433,
        "database": "testdb",
        "user": "testuser",
        "password": "testpass",
    }


@pytest.fixture
def adapter(valid_config):
    """SQLServerAdapter instance with valid config"""
    return SQLServerAdapter(valid_config)


# ============================================================================
# TEST: Connection Management
# ============================================================================


class TestConnection:
    """Tests for connection management"""

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_connect_success(self, mock_connect, adapter):
        """Test successful connection to SQL Server"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        adapter.connect()

        assert adapter.is_connected is True
        assert adapter.connection == mock_conn
        mock_connect.assert_called_once()

        # Verify connection string format
        conn_str = mock_connect.call_args[0][0]
        assert "DRIVER={ODBC Driver 18 for SQL Server}" in conn_str
        assert "SERVER={localhost,1433}" in conn_str
        assert "DATABASE={testdb}" in conn_str
        assert "UID={testuser}" in conn_str
        assert "PWD={testpass}" in conn_str
        # TLS verificado por defecto
        assert "Encrypt=yes;TrustServerCertificate=no;" in conn_str

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_connection_string_values_cannot_inject_attributes(self, mock_connect, valid_config):
        adapter = SQLServerAdapter(
            {**valid_config, "password": "x};SAVEFILE=/tmp/pwn;TrustServerCertificate=yes;{"}
        )

        adapter.connect()

        conn_str = mock_connect.call_args[0][0]
        assert "PWD={x}};SAVEFILE=/tmp/pwn;TrustServerCertificate=yes;{};" in conn_str
        assert "TrustServerCertificate=no;" in conn_str

    @pytest.mark.parametrize(
        "ssl_mode,expected",
        [
            ("require", "Encrypt=yes;TrustServerCertificate=yes;"),
            ("disable", "Encrypt=no;"),
        ],
    )
    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_ssl_modes(self, mock_connect, ssl_mode, expected, valid_config):
        SQLServerAdapter({**valid_config, "ssl_mode": ssl_mode}).connect()

        assert expected in mock_connect.call_args[0][0]

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_connect_authentication_error(self, mock_connect, adapter):
        """Test authentication error raises DBAuthenticationError"""
        import pyodbc

        mock_connect.side_effect = pyodbc.Error("18456", "Login failed for user")

        with pytest.raises(DBAuthenticationError) as exc_info:
            adapter.connect()

        assert "Invalid credentials" in str(exc_info.value)

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_connect_timeout_error(self, mock_connect, adapter):
        """Test connection timeout raises DBTimeoutError"""
        import pyodbc

        mock_connect.side_effect = pyodbc.Error("Connection timeout exceeded")

        with pytest.raises(DBTimeoutError) as exc_info:
            adapter.connect()

        assert "timeout" in str(exc_info.value).lower()

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_connect_generic_error(self, mock_connect, adapter):
        """Test generic connection error raises DBConnectionError"""
        import pyodbc

        mock_connect.side_effect = pyodbc.Error("Network error")

        with pytest.raises(DBConnectionError) as exc_info:
            adapter.connect()

        assert "Cannot connect to SQL Server" in str(exc_info.value)

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_disconnect(self, mock_connect, adapter):
        """Test disconnect closes connection"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        adapter.connect()
        adapter.disconnect()

        mock_conn.close.assert_called_once()
        assert adapter.is_connected is False

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_test_connection_success(self, mock_connect, adapter):
        """Test successful connection test"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        result = adapter.test_connection()

        assert result is True
        mock_cursor.execute.assert_called_with("SELECT 1 AS test")
        mock_conn.close.assert_called_once()

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_context_manager(self, mock_connect, valid_config):
        """Test context manager properly manages connection"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with SQLServerAdapter(valid_config) as adapter:
            assert adapter.is_connected is True

        mock_conn.close.assert_called_once()


# ============================================================================
# TEST: list_schemas()
# ============================================================================


class TestListSchemas:
    """Tests for list_schemas() method"""

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_list_schemas_returns_list(self, mock_connect, adapter):
        """Test list_schemas returns list of schema names"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("dbo",),
            ("app_schema",),
            ("sales",),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        schemas = adapter.get_schemas()

        assert schemas == ["dbo", "app_schema", "sales"]
        mock_cursor.execute.assert_called_once()

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_list_schemas_filters_system_schemas(self, mock_connect, adapter):
        """Test that system schemas are filtered in query"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("dbo",)]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        adapter.get_schemas()

        # Verify query filters system schemas
        query = mock_cursor.execute.call_args[0][0]
        assert "NOT IN" in query
        assert "sys" in query
        assert "INFORMATION_SCHEMA" in query

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_list_schemas_query_error(self, mock_connect, adapter):
        """Test query error raises DBQueryExecutionError"""
        import pyodbc

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = pyodbc.Error("Query failed")

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()

        with pytest.raises(DBQueryExecutionError) as exc_info:
            adapter.get_schemas()

        assert "Failed to list schemas" in str(exc_info.value)


# ============================================================================
# TEST: list_tables()
# ============================================================================


class TestListTables:
    """Tests for list_tables() method"""

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_list_tables_returns_metadata(self, mock_connect, adapter):
        """Test list_tables returns TableMetadata objects"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("dbo", "users", "BASE TABLE", 100),
            ("dbo", "products", "BASE TABLE", 50),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        tables = adapter.get_tables("dbo")

        assert len(tables) == 2
        assert tables[0].schema_name == "dbo"
        assert tables[0].table_name == "users"
        assert tables[0].table_type == TableType.TABLE

        assert tables[1].table_name == "products"

        # Verify query uses parameterized schema name
        mock_cursor.execute.assert_called_once()
        assert mock_cursor.execute.call_args[0][1] == ("dbo",)

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_list_tables_empty_schema(self, mock_connect, adapter):
        """Test list_tables with empty schema"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        tables = adapter.get_tables("empty_schema")

        assert tables == []

    def test_list_tables_invalid_schema_name(self, adapter):
        """Test get_tables validates schema name"""
        with pytest.raises(ValueError):
            adapter.get_tables("invalid; DROP TABLE users;")


# ============================================================================
# TEST: get_table_columns()
# ============================================================================


class TestGetTableColumns:
    """Tests for get_table_columns() method"""

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_table_columns_returns_metadata(self, mock_connect, adapter):
        """Test get_table_columns returns ColumnMetadata objects"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            # column_name, data_type, max_length, precision, scale, is_nullable, default, position, is_pk, is_identity
            ("id", "int", None, 10, 0, "NO", None, 1, 1, 1),
            ("username", "nvarchar", 50, None, None, "NO", None, 2, 0, 0),
            ("balance", "decimal", None, 12, 2, "YES", "0.00", 3, 0, 0),
            ("is_active", "bit", None, None, None, "NO", "1", 4, 0, 0),
            ("guid", "uniqueidentifier", None, None, None, "NO", "newid()", 5, 0, 0),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        columns = adapter.get_columns("users", "dbo")

        assert len(columns) == 5

        # Test id column (primary key, identity)
        id_col = columns[0]
        assert id_col.column_name == "id"
        assert id_col.data_type == DataType.INTEGER
        assert id_col.is_nullable is False
        assert id_col.is_primary_key is True
        assert id_col.is_auto_increment is True
        assert id_col.ordinal_position == 1
        assert id_col.native_type == "int"

        # Test username column (nvarchar with length)
        username_col = columns[1]
        assert username_col.column_name == "username"
        assert username_col.data_type == DataType.VARCHAR
        assert username_col.max_length == 50
        assert username_col.is_nullable is False
        assert username_col.is_primary_key is False

        # Test balance column (decimal with precision and scale)
        balance_col = columns[2]
        assert balance_col.column_name == "balance"
        assert balance_col.data_type == DataType.DECIMAL
        assert balance_col.numeric_precision == 12
        assert balance_col.numeric_scale == 2
        assert balance_col.is_nullable is True
        assert balance_col.default_value == "0.00"

        # Test is_active column (BIT → BOOLEAN)
        is_active_col = columns[3]
        assert is_active_col.column_name == "is_active"
        assert is_active_col.data_type == DataType.BOOLEAN

        # Test GUID column (UNIQUEIDENTIFIER → UUID)
        guid_col = columns[4]
        assert guid_col.column_name == "guid"
        assert guid_col.data_type == DataType.UUID

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_table_columns_table_not_found(self, mock_connect, adapter):
        """Test get_table_columns with non-existent table"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()

        with pytest.raises(DBMetadataNotFoundError) as exc_info:
            adapter.get_columns("nonexistent_table", "dbo")

        assert "not found" in str(exc_info.value)

    def test_get_table_columns_validates_names(self, adapter):
        """Test get_columns validates schema and table names"""
        with pytest.raises(ValueError):
            adapter.get_columns("users", "invalid; DROP")

        with pytest.raises(ValueError):
            adapter.get_columns("invalid; DROP", "dbo")


# ============================================================================
# TEST: get_primary_keys()
# ============================================================================


class TestGetPrimaryKeys:
    """Tests for get_primary_keys() method"""

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_primary_keys_single_column(self, mock_connect, adapter):
        """Test get_primary_keys with single-column PK"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("PK_users", "id", 1),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        pks = adapter.get_primary_keys("dbo", "users")

        assert len(pks) == 1
        assert pks[0].constraint_name == "PK_users"
        assert pks[0].table_name == "users"
        assert pks[0].column_names == ["id"]

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_primary_keys_composite(self, mock_connect, adapter):
        """Test get_primary_keys with composite PK"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("PK_order_items", "order_id", 1),
            ("PK_order_items", "product_id", 2),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        pks = adapter.get_primary_keys("dbo", "order_items")

        assert len(pks) == 1
        assert pks[0].constraint_name == "PK_order_items"
        assert pks[0].column_names == ["order_id", "product_id"]

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_primary_keys_none(self, mock_connect, adapter):
        """Test get_primary_keys with no primary key"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        pks = adapter.get_primary_keys("dbo", "logs")

        assert pks == []


# ============================================================================
# TEST: get_foreign_keys()
# ============================================================================


class TestGetForeignKeys:
    """Tests for get_foreign_keys() method"""

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_foreign_keys_single_column(self, mock_connect, adapter):
        """Test get_foreign_keys with single-column FK"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (
                "FK_products_category",
                "dbo",
                "products",
                "category_id",
                "dbo",
                "categories",
                "id",
                "NO_ACTION",
                "NO_ACTION",
            ),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        fks = adapter.get_foreign_keys("dbo", "products")

        assert len(fks) == 1
        assert fks[0].constraint_name == "FK_products_category"
        assert fks[0].table_name == "products"
        assert fks[0].column_names == ["category_id"]
        assert fks[0].referenced_table == "categories"
        assert fks[0].referenced_columns == ["id"]
        assert fks[0].on_delete == "NO_ACTION"
        assert fks[0].on_update == "NO_ACTION"

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_foreign_keys_composite(self, mock_connect, adapter):
        """Test get_foreign_keys with composite FK"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (
                "FK_order_items_order",
                "dbo",
                "order_items",
                "order_id",
                "dbo",
                "orders",
                "id",
                "CASCADE",
                "CASCADE",
            ),
            (
                "FK_order_items_order",
                "dbo",
                "order_items",
                "line_number",
                "dbo",
                "orders",
                "line_number",
                "CASCADE",
                "CASCADE",
            ),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        fks = adapter.get_foreign_keys("dbo", "order_items")

        assert len(fks) == 1
        assert fks[0].column_names == ["order_id", "line_number"]
        assert fks[0].referenced_columns == ["id", "line_number"]
        assert fks[0].on_delete == "CASCADE"

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_foreign_keys_none(self, mock_connect, adapter):
        """Test get_foreign_keys with no foreign keys"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        fks = adapter.get_foreign_keys("dbo", "categories")

        assert fks == []


# ============================================================================
# TEST: get_unique_constraints()
# ============================================================================


class TestGetUniqueConstraints:
    """Tests for get_unique_constraints() method"""

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_unique_constraints(self, mock_connect, adapter):
        """Test get_unique_constraints returns unique constraints"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("UQ_users_email", "email", 1),
            ("UQ_users_username", "username", 1),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        uniques = adapter.get_unique_constraints("dbo", "users")

        assert len(uniques) == 2
        assert uniques[0].constraint_name == "UQ_users_email"
        assert uniques[0].column_names == ["email"]
        assert uniques[1].constraint_name == "UQ_users_username"
        assert uniques[1].column_names == ["username"]


# ============================================================================
# TEST: get_check_constraints()
# ============================================================================


class TestGetCheckConstraints:
    """Tests for get_check_constraints() method"""

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_check_constraints(self, mock_connect, adapter):
        """Test get_check_constraints returns check constraints"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("CK_users_age", "([age]>=(18) AND [age]<=(120))"),
            ("CK_users_balance", "([balance]>=(0))"),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        checks = adapter.get_check_constraints("dbo", "users")

        assert len(checks) == 2
        assert checks[0].constraint_name == "CK_users_age"
        assert checks[0].table_name == "users"
        assert "age" in checks[0].check_clause
        assert checks[1].constraint_name == "CK_users_balance"
        assert "balance" in checks[1].check_clause


# ============================================================================
# TEST: get_indexes()
# ============================================================================


class TestGetIndexes:
    """Tests for get_indexes() method"""

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_indexes(self, mock_connect, adapter):
        """Test get_indexes returns index metadata"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("IDX_users_email", 1, 0, "email", 1),
            ("IDX_users_created_at", 0, 0, "created_at", 1),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        indexes = adapter.get_indexes("dbo", "users")

        assert len(indexes) == 2

        # Unique index
        assert indexes[0].index_name == "IDX_users_email"
        assert indexes[0].is_unique is True
        assert indexes[0].column_names == ["email"]
        assert indexes[0].index_type == IndexType.BTREE

        # Non-unique index
        assert indexes[1].index_name == "IDX_users_created_at"
        assert indexes[1].is_unique is False
        assert indexes[1].index_type == IndexType.BTREE

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_indexes_composite(self, mock_connect, adapter):
        """Test get_indexes with composite index"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("IDX_orders_user_date", 0, 0, "user_id", 1),
            ("IDX_orders_user_date", 0, 0, "created_at", 2),
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        indexes = adapter.get_indexes("dbo", "orders")

        assert len(indexes) == 1
        assert indexes[0].column_names == ["user_id", "created_at"]

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_indexes_filters_primary_key(self, mock_connect, adapter):
        """Test that primary key indexes are filtered out"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("PK_users", 1, 1, "id", 1),  # is_primary_key = 1
            ("IDX_users_email", 1, 0, "email", 1),  # is_primary_key = 0
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        indexes = adapter.get_indexes("dbo", "users")

        # Should only return non-PK index
        assert len(indexes) == 1
        assert indexes[0].index_name == "IDX_users_email"


# ============================================================================
# TEST: get_table_statistics()
# ============================================================================


class TestGetTableStatistics:
    """Tests for get_table_statistics() method"""

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_table_statistics(self, mock_connect, adapter):
        """Test get_table_statistics returns statistics"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = (1000, 8192000, 6144000)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        stats = adapter.get_table_statistics("dbo", "users")

        assert stats.table_name == "users"
        assert stats.row_count == 1000
        assert stats.total_size_bytes == 8192000
        assert stats.data_size_bytes == 6144000

    @patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect")
    def test_get_table_statistics_empty_table(self, mock_connect, adapter):
        """Test get_table_statistics with empty table"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        adapter.connect()
        stats = adapter.get_table_statistics("dbo", "empty_table")

        assert stats.row_count == 0
        assert stats.total_size_bytes == 0


# ============================================================================
# TEST: Dialect Property
# ============================================================================


class TestDialect:
    """Tests for dialect property"""

    def test_dialect_returns_sqlserver(self, adapter):
        """Test dialect property returns 'sqlserver'"""
        assert adapter.dialect == "sqlserver"


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
