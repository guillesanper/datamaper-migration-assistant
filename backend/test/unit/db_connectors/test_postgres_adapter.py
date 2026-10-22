"""
Unit tests for app.utils.db_adapters.postgres_adapter module

Tests for PostgreSQLAdapter with mocked psycopg2:
- Connection management (connect, disconnect, test_connection)
- Schema introspection (get_schemas, get_tables)
- Column metadata (get_columns with type mapping)
- Constraints (get_primary_keys, get_foreign_keys)
- Indexes (get_indexes)
- Statistics (get_table_statistics)
- Error handling
"""

from unittest.mock import MagicMock, Mock, call, patch

import pytest

from app.models.db_metadata import DataType, TableType
from app.utils.db_adapters.exceptions import (
    DBAuthenticationError,
    DBConnectionError,
    DBQueryExecutionError,
)
from app.utils.db_adapters.postgres_adapter import PostgreSQLAdapter

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def valid_config():
    """Valid PostgreSQL connection config"""
    return {
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "user": "testuser",
        "password": "testpass",
    }


@pytest.fixture
def adapter(valid_config):
    """PostgreSQLAdapter instance with valid config"""
    return PostgreSQLAdapter(valid_config)


# ============================================================================
# TEST Connection Management
# ============================================================================


class TestConnection:
    """Tests for connection management"""

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_connect_success(self, mock_connect, adapter):
        """Test: Successful connection"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        adapter.connect()

        assert adapter.is_connected is True
        assert adapter.connection == mock_conn
        mock_connect.assert_called_once()

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_connect_authentication_error(self, mock_connect, adapter):
        """Test: Authentication error raises DBAuthenticationError"""
        from psycopg2.errors import InvalidPassword

        mock_connect.side_effect = InvalidPassword("Invalid password")

        with pytest.raises(DBAuthenticationError):
            adapter.connect()

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_connect_connection_error(self, mock_connect, adapter):
        """Test: Connection error raises DBConnectionError"""
        from psycopg2 import OperationalError

        mock_connect.side_effect = OperationalError("Cannot connect")

        with pytest.raises(DBConnectionError):
            adapter.connect()

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_disconnect(self, mock_connect, adapter):
        """Test: Disconnect closes connection"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        adapter.connect()
        adapter.disconnect()

        mock_conn.close.assert_called_once()
        assert adapter.is_connected is False

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_context_manager(self, mock_connect, valid_config):
        """Test: Context manager properly manages connection"""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with PostgreSQLAdapter(valid_config) as adapter:
            assert adapter.is_connected is True

        mock_conn.close.assert_called_once()


# ============================================================================
# TEST get_schemas()
# ============================================================================


class TestGetSchemas:
    """Tests for get_schemas() method"""

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_schemas_returns_list(self, mock_connect, adapter):
        """Test: get_schemas returns list of schema names"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"schema_name": "public"},
            {"schema_name": "app_schema"},
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        schemas = adapter.get_schemas()

        assert schemas == ["public", "app_schema"]
        mock_cursor.execute.assert_called_once()

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_schemas_filters_system_schemas(self, mock_connect, adapter):
        """Test: System schemas should be filtered out in query"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{"schema_name": "public"}]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        adapter.get_schemas()

        # Verify query filters pg_* and information_schema
        query = mock_cursor.execute.call_args[0][0]
        assert "NOT LIKE 'pg_%'" in query
        assert "!= 'information_schema'" in query


# ============================================================================
# TEST get_tables()
# ============================================================================


class TestGetTables:
    """Tests for get_tables() method"""

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_tables_returns_metadata(self, mock_connect, adapter):
        """Test: get_tables returns TableMetadata objects"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"table_name": "users", "table_schema": "public", "table_type": "BASE TABLE"},
            {"table_name": "orders", "table_schema": "public", "table_type": "VIEW"},
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        tables = adapter.get_tables(schema="public")

        assert len(tables) == 2
        assert tables[0].name == "users"
        assert tables[0].table_type == TableType.BASE_TABLE
        assert tables[1].name == "orders"
        assert tables[1].table_type == TableType.VIEW

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_tables_uses_default_schema(self, mock_connect, adapter):
        """Test: Uses 'public' as default schema"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        adapter.get_tables()

        # Should use 'public' as default
        call_args = mock_cursor.execute.call_args
        assert call_args[0][1] == ("public",)


# ============================================================================
# TEST get_columns()
# ============================================================================


class TestGetColumns:
    """Tests for get_columns() method"""

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_columns_returns_metadata(self, mock_connect, adapter):
        """Test: get_columns returns ColumnMetadata objects"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "column_name": "id",
                "data_type": "integer",
                "udt_name": "int4",
                "is_nullable": "NO",
                "column_default": "nextval('users_id_seq')",
                "character_maximum_length": None,
                "numeric_precision": 32,
                "numeric_scale": 0,
                "ordinal_position": 1,
            },
            {
                "column_name": "email",
                "data_type": "character varying",
                "udt_name": "varchar",
                "is_nullable": "NO",
                "column_default": None,
                "character_maximum_length": 255,
                "numeric_precision": None,
                "numeric_scale": None,
                "ordinal_position": 2,
            },
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        # Mock _mark_key_columns to avoid additional queries - return the input unchanged
        with patch.object(
            adapter, "_mark_key_columns", side_effect=lambda cols, *args, **kwargs: cols
        ):
            columns = adapter.get_columns("users", schema="public")

        assert len(columns) == 2
        assert columns[0].name == "id"
        assert columns[0].data_type == DataType.INTEGER
        assert columns[0].is_nullable is False
        assert columns[0].is_auto_increment is True
        assert columns[1].name == "email"
        assert columns[1].max_length == 255


# ============================================================================
# TEST get_primary_keys()
# ============================================================================


class TestGetPrimaryKeys:
    """Tests for get_primary_keys() method"""

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_primary_keys_single_column(self, mock_connect, adapter):
        """Test: Single column primary key"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"constraint_name": "users_pkey", "column_name": "id"},
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        pks = adapter.get_primary_keys("users", "public")

        assert len(pks) == 1
        assert pks[0].name == "users_pkey"
        assert pks[0].columns == ["id"]

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_primary_keys_composite(self, mock_connect, adapter):
        """Test: Composite primary key"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"constraint_name": "order_items_pkey", "column_name": "order_id"},
            {"constraint_name": "order_items_pkey", "column_name": "item_id"},
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        pks = adapter.get_primary_keys("order_items", "public")

        assert len(pks) == 1
        assert pks[0].columns == ["order_id", "item_id"]


# ============================================================================
# TEST get_foreign_keys()
# ============================================================================


class TestGetForeignKeys:
    """Tests for get_foreign_keys() method"""

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_foreign_keys(self, mock_connect, adapter):
        """Test: Foreign key metadata"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "constraint_name": "orders_user_id_fkey",
                "column_name": "user_id",
                "referenced_schema": "public",
                "referenced_table": "users",
                "referenced_column": "id",
                "update_rule": "NO ACTION",
                "delete_rule": "CASCADE",
            },
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        fks = adapter.get_foreign_keys("orders", "public")

        assert len(fks) == 1
        assert fks[0].name == "orders_user_id_fkey"
        assert fks[0].columns == ["user_id"]
        assert fks[0].referenced_table == "users"
        assert fks[0].on_delete == "CASCADE"


# ============================================================================
# TEST get_indexes()
# ============================================================================


class TestGetIndexes:
    """Tests for get_indexes() method"""

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_indexes(self, mock_connect, adapter):
        """Test: Index metadata"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "index_name": "users_email_idx",
                "column_name": "email",
                "is_unique": True,
                "is_primary": False,
                "index_type": "btree",
            },
        ]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        indexes = adapter.get_indexes("users", "public")

        assert len(indexes) == 1
        assert indexes[0].name == "users_email_idx"
        assert indexes[0].is_unique is True


# ============================================================================
# TEST get_table_statistics()
# ============================================================================


class TestGetTableStatistics:
    """Tests for get_table_statistics() method"""

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_table_statistics(self, mock_connect, adapter):
        """Test: Table statistics metadata"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "schemaname": "public",
            "relname": "users",
            "n_live_tup": 1000,
            "n_dead_tup": 50,
            "last_vacuum": None,
            "last_autovacuum": "2024-01-01",
            "last_analyze": None,
            "last_autoanalyze": "2024-01-01",
            "total_size": 8192000,
        }

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        stats = adapter.get_table_statistics("users", "public")

        assert stats.row_count == 1000
        assert stats.size_bytes == 8192000
        assert stats.table_name == "users"

    @patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect")
    def test_get_table_statistics_no_data(self, mock_connect, adapter):
        """Test: Table with no statistics returns default"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        adapter.connection = mock_conn
        adapter._is_connected = True

        stats = adapter.get_table_statistics("new_table", "public")

        assert stats.row_count == 0
        assert stats.size_bytes == 0


# ============================================================================
# TEST Error Handling
# ============================================================================


class TestErrorHandling:
    """Tests for error handling"""

    def test_invalid_config_missing_field(self):
        """Test: Invalid config raises DBValidationError"""
        from app.utils.db_adapters.exceptions import DBValidationError

        invalid_config = {"host": "localhost"}

        with pytest.raises(DBValidationError):
            PostgreSQLAdapter(invalid_config)

    def test_dialect_property(self, adapter):
        """Test: Dialect property returns 'postgresql'"""
        assert adapter.dialect == "postgresql"

    def test_default_schema(self, adapter):
        """Test: Default schema is 'public'"""
        assert adapter._get_default_schema() == "public"
