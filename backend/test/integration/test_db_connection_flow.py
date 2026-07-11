"""
Integration Tests for Database Connection Flow

Tests the complete end-to-end flow against real databases:
- PostgreSQL connection and introspection
- MySQL connection and introspection
- Session lifecycle management
- Credential validation
- Session expiration

IMPORTANT: Requires docker-compose.test.yml to be running:
    docker-compose -f docker-compose.test.yml up -d
"""

import time
from datetime import datetime, timedelta

import pytest
import redis

from app.models.db_connection import DBConnectionConfig
from app.models.db_metadata import ConstraintType, DataType, TableType
from app.services.db_connection_service import (
    DBConnectionService,
    SessionExpiredError,
    SessionNotFoundError,
)
from app.utils.db_adapters import DBAuthenticationError, MySQLAdapter, PostgreSQLAdapter

# =============================================
# FIXTURES
# =============================================


@pytest.fixture(scope="session")
def redis_test_client():
    """Redis client for test instance (port 6380)"""
    client = redis.Redis(host="localhost", port=6380, db=0, decode_responses=False)

    # Wait for Redis to be ready
    for _ in range(10):
        try:
            client.ping()
            break
        except redis.ConnectionError:
            time.sleep(0.5)
    else:
        pytest.skip("Redis test instance not available on port 6380")

    # Clear test database before tests
    client.flushdb()

    yield client

    # Cleanup
    client.flushdb()
    client.close()


@pytest.fixture
def encryption_key():
    """Test encryption key (32 bytes minimum for AES-256)"""
    return "test-encryption-key-min-32-chars-long-for-security"


@pytest.fixture
def db_connection_service(redis_test_client, encryption_key):
    """Initialized DBConnectionService"""
    return DBConnectionService(redis_test_client, encryption_key)


@pytest.fixture
def postgres_config():
    """PostgreSQL test database configuration"""
    return DBConnectionConfig(
        dialect="postgresql",
        host="localhost",
        port=5433,
        database="test_database",
        user="test_user",
        password="test_password",
    )


@pytest.fixture
def mysql_config():
    """MySQL test database configuration"""
    return DBConnectionConfig(
        dialect="mysql",
        host="localhost",
        port=3307,
        database="test_database",
        user="test_user",
        password="test_password",
    )


@pytest.fixture
def postgres_invalid_config():
    """Invalid PostgreSQL configuration (wrong password)"""
    return DBConnectionConfig(
        dialect="postgresql",
        host="localhost",
        port=5433,
        database="test_database",
        user="test_user",
        password="wrong_password",
    )


@pytest.fixture
def mysql_invalid_config():
    """Invalid MySQL configuration (wrong password)"""
    return DBConnectionConfig(
        dialect="mysql",
        host="localhost",
        port=3307,
        database="test_database",
        user="test_user",
        password="wrong_password",
    )


# =============================================
# TEST: Connection Validation
# =============================================


class TestConnectionValidation:
    """Tests for connection credential validation"""

    def test_postgres_connection_success(self, db_connection_service, postgres_config):
        """Test successful PostgreSQL connection"""
        result = db_connection_service.test_connection(postgres_config)

        assert result.success is True
        assert result.dialect == "postgresql"
        assert result.host == "localhost"
        assert result.database == "test_database"
        assert result.error_message is None
        assert result.error_type is None

    def test_mysql_connection_success(self, db_connection_service, mysql_config):
        """Test successful MySQL connection"""
        result = db_connection_service.test_connection(mysql_config)

        assert result.success is True
        assert result.dialect == "mysql"
        assert result.host == "localhost"
        assert result.database == "test_database"
        assert result.error_message is None
        assert result.error_type is None

    def test_postgres_connection_invalid_credentials(
        self, db_connection_service, postgres_invalid_config
    ):
        """Test PostgreSQL connection with invalid credentials"""
        result = db_connection_service.test_connection(postgres_invalid_config)

        assert result.success is False
        assert result.dialect == "postgresql"
        assert result.error_type == "authentication"
        assert result.error_message is not None
        assert (
            "password" in result.error_message.lower()
            or "authentication" in result.error_message.lower()
        )

    def test_mysql_connection_invalid_credentials(
        self, db_connection_service, mysql_invalid_config
    ):
        """Test MySQL connection with invalid credentials"""
        result = db_connection_service.test_connection(mysql_invalid_config)

        assert result.success is False
        assert result.dialect == "mysql"
        assert result.error_type == "authentication"
        assert result.error_message is not None


# =============================================
# TEST: Session Lifecycle
# =============================================


class TestSessionLifecycle:
    """Tests for session creation, retrieval, and deletion"""

    def test_create_session_postgres(self, db_connection_service, postgres_config):
        """Test creating a PostgreSQL session"""
        user_id = "1"

        response = db_connection_service.create_session(
            user_id=user_id,
            config=postgres_config,
            ttl_hours=3,
        )

        assert response.session_id is not None
        assert response.dialect == "postgresql"
        assert response.host == "localhost"
        assert response.database == "test_database"
        assert response.expires_at > datetime.utcnow()

        # Verify session is retrievable
        session = db_connection_service.get_session(user_id, response.session_id)
        assert session.user_id == user_id
        assert session.dialect == "postgresql"
        assert session.encrypted_credentials is not None

    def test_create_session_mysql(self, db_connection_service, mysql_config):
        """Test creating a MySQL session"""
        user_id = "2"

        response = db_connection_service.create_session(
            user_id=user_id,
            config=mysql_config,
            ttl_hours=3,
        )

        assert response.session_id is not None
        assert response.dialect == "mysql"
        assert response.host == "localhost"
        assert response.database == "test_database"

        # Verify session is retrievable
        session = db_connection_service.get_session(user_id, response.session_id)
        assert session.user_id == user_id
        assert session.dialect == "mysql"

    def test_create_session_with_invalid_credentials_fails(
        self, db_connection_service, postgres_invalid_config
    ):
        """Test that session creation fails with invalid credentials"""
        user_id = "3"

        with pytest.raises(Exception) as exc_info:
            db_connection_service.create_session(
                user_id=user_id,
                config=postgres_invalid_config,
                ttl_hours=3,
            )

        assert "Connection test failed" in str(exc_info.value)

    def test_get_session_not_found(self, db_connection_service):
        """Test retrieving non-existent session"""
        with pytest.raises(SessionNotFoundError):
            db_connection_service.get_session("999", "non-existent-session-id")

    def test_delete_session(self, db_connection_service, postgres_config):
        """Test deleting a session"""
        user_id = "4"

        # Create session
        response = db_connection_service.create_session(
            user_id=user_id,
            config=postgres_config,
        )

        # Verify it exists
        session = db_connection_service.get_session(user_id, response.session_id)
        assert session is not None

        # Delete session
        deleted = db_connection_service.delete_session(user_id, response.session_id)
        assert deleted is True

        # Verify it's gone
        with pytest.raises(SessionNotFoundError):
            db_connection_service.get_session(user_id, response.session_id)

    def test_refresh_session(self, db_connection_service, postgres_config):
        """Test refreshing session TTL"""
        user_id = "5"

        # Create session with 1 hour TTL
        response = db_connection_service.create_session(
            user_id=user_id,
            config=postgres_config,
            ttl_hours=1,
        )

        original_expires_at = response.expires_at

        # Wait a bit
        time.sleep(1)

        # Refresh with 3 hours
        new_expires_at = db_connection_service.refresh_session(
            user_id, response.session_id, ttl_hours=3
        )

        assert new_expires_at > original_expires_at

        # Verify new expiration
        session = db_connection_service.get_session(user_id, response.session_id)
        # Allow small difference due to timing
        assert abs((session.expires_at - new_expires_at).total_seconds()) < 5

    def test_list_user_sessions(self, db_connection_service, postgres_config, mysql_config):
        """Test listing all user sessions"""
        user_id = "6"

        # Create multiple sessions
        session1 = db_connection_service.create_session(user_id, postgres_config)
        session2 = db_connection_service.create_session(user_id, mysql_config)

        # List sessions
        sessions = db_connection_service.list_user_sessions(user_id)

        assert len(sessions) == 2
        session_ids = [s.session_id for s in sessions]
        assert session1.session_id in session_ids
        assert session2.session_id in session_ids

    def test_credential_encryption(self, db_connection_service, postgres_config):
        """Test that credentials are encrypted in storage"""
        user_id = "7"

        # Create session
        response = db_connection_service.create_session(
            user_id=user_id,
            config=postgres_config,
        )

        # Retrieve session
        session = db_connection_service.get_session(user_id, response.session_id)

        # Encrypted credentials should not contain plaintext password
        assert postgres_config.password not in session.encrypted_credentials
        assert "test_password" not in session.encrypted_credentials

        # Decrypt and verify
        decrypted_config = db_connection_service.get_decrypted_config(session)
        assert decrypted_config.password == postgres_config.password
        assert decrypted_config.username == postgres_config.username

    def test_ttl_validation(self, db_connection_service, postgres_config):
        """Test TTL maximum validation"""
        user_id = "8"

        # Test with max TTL (24 hours) - should succeed
        response = db_connection_service.create_session(
            user_id=user_id,
            config=postgres_config,
            ttl_hours=24,
        )
        assert response.session_id is not None

        # Test with TTL > 24 hours - should fail
        with pytest.raises(ValueError) as exc_info:
            db_connection_service.create_session(
                user_id=user_id,
                config=postgres_config,
                ttl_hours=25,
            )
        assert "cannot exceed 24 hours" in str(exc_info.value)


# =============================================
# TEST: Schema Introspection (PostgreSQL)
# =============================================


class TestPostgreSQLIntrospection:
    """Tests for PostgreSQL schema introspection"""

    @pytest.fixture
    def postgres_adapter(self, postgres_config):
        """PostgreSQL adapter connected to test database"""
        adapter = PostgreSQLAdapter(postgres_config.to_adapter_config())
        adapter.connect()
        yield adapter
        adapter.disconnect()

    def test_list_schemas(self, postgres_adapter):
        """Test listing all schemas"""
        schemas = postgres_adapter.list_schemas()

        assert "public" in schemas
        assert "sales" in schemas
        assert "inventory" in schemas
        assert "information_schema" not in schemas  # Should be filtered
        assert "pg_catalog" not in schemas  # Should be filtered

    def test_list_tables_public_schema(self, postgres_adapter):
        """Test listing tables in public schema"""
        tables = postgres_adapter.list_tables("public")

        table_names = [t.table_name for t in tables]
        assert "users" in table_names
        assert "products" in table_names
        assert "orders" in table_names
        assert "categories" in table_names
        assert "reviews" in table_names
        assert "audit_logs" in table_names

        # Check table types
        for table in tables:
            assert table.table_type == TableType.TABLE

    def test_list_tables_sales_schema(self, postgres_adapter):
        """Test listing tables in sales schema"""
        tables = postgres_adapter.list_tables("sales")

        table_names = [t.table_name for t in tables]
        assert "invoices" in table_names
        assert "monthly_reports" in table_names

    def test_get_table_columns_users(self, postgres_adapter):
        """Test getting columns for users table"""
        columns = postgres_adapter.get_table_columns("public", "users")

        column_map = {col.column_name: col for col in columns}

        # Check specific columns exist
        assert "id" in column_map
        assert "username" in column_map
        assert "email" in column_map
        assert "age" in column_map
        assert "balance" in column_map
        assert "is_active" in column_map
        assert "created_at" in column_map
        assert "metadata" in column_map

        # Check column properties
        id_col = column_map["id"]
        assert id_col.data_type == DataType.INTEGER
        assert id_col.is_nullable is False
        assert id_col.is_primary_key is True

        username_col = column_map["username"]
        assert username_col.data_type == DataType.VARCHAR
        assert username_col.max_length == 50
        assert username_col.is_nullable is False

        balance_col = column_map["balance"]
        assert balance_col.data_type == DataType.DECIMAL
        assert balance_col.numeric_precision == 12
        assert balance_col.numeric_scale == 2

        is_active_col = column_map["is_active"]
        assert is_active_col.data_type == DataType.BOOLEAN

        metadata_col = column_map["metadata"]
        assert metadata_col.data_type == DataType.JSON

    def test_get_table_columns_audit_logs(self, postgres_adapter):
        """Test getting columns for audit_logs table (UUID primary key)"""
        columns = postgres_adapter.get_table_columns("public", "audit_logs")

        column_map = {col.column_name: col for col in columns}

        # Check UUID column
        id_col = column_map["id"]
        assert id_col.data_type == DataType.UUID
        assert id_col.is_primary_key is True

        # Check INET column
        ip_col = column_map["ip_address"]
        assert ip_col.data_type == DataType.OTHER  # INET mapped to OTHER

    def test_get_primary_keys(self, postgres_adapter):
        """Test getting primary key constraints"""
        pks = postgres_adapter.get_primary_keys("public", "users")

        assert len(pks) == 1
        pk = pks[0]
        assert pk.constraint_type == ConstraintType.PRIMARY_KEY
        assert "id" in pk.column_names

    def test_get_foreign_keys(self, postgres_adapter):
        """Test getting foreign key constraints"""
        fks = postgres_adapter.get_foreign_keys("public", "products")

        # Products table has FK to categories
        assert len(fks) >= 1

        category_fk = next(fk for fk in fks if "category" in fk.constraint_name.lower())

        assert category_fk.constraint_type == ConstraintType.FOREIGN_KEY
        assert "category_id" in category_fk.column_names
        assert category_fk.referenced_table == "categories"
        assert "id" in category_fk.referenced_columns

    def test_get_unique_constraints(self, postgres_adapter):
        """Test getting unique constraints"""
        uniques = postgres_adapter.get_unique_constraints("public", "users")

        # Users has unique constraints on username and email
        constraint_names = [u.constraint_name for u in uniques]
        column_sets = [tuple(u.column_names) for u in uniques]

        assert ("username",) in column_sets or any("username" in cols for cols in column_sets)
        assert ("email",) in column_sets or any("email" in cols for cols in column_sets)

    def test_get_check_constraints(self, postgres_adapter):
        """Test getting check constraints"""
        checks = postgres_adapter.get_check_constraints("public", "users")

        # Users has check constraints on age and balance
        assert len(checks) >= 2

        check_names = [c.constraint_name.lower() for c in checks]
        definitions = [c.check_clause.lower() for c in checks]

        # Check for age constraint
        assert any("age" in defn for defn in definitions)

        # Check for balance constraint
        assert any("balance" in defn for defn in definitions)

    def test_get_indexes(self, postgres_adapter):
        """Test getting indexes"""
        indexes = postgres_adapter.get_indexes("public", "users")

        # Should have indexes on email, username, created_at
        index_names = [idx.index_name.lower() for idx in indexes]

        assert any("email" in name for name in index_names)
        assert any("username" in name for name in index_names)

        # Check index properties
        for idx in indexes:
            assert idx.table_name == "users"
            assert len(idx.column_names) > 0

    def test_get_table_statistics(self, postgres_adapter):
        """Test getting table statistics"""
        stats = postgres_adapter.get_table_statistics("public", "users")

        assert stats.table_name == "users"
        assert stats.row_count >= 0  # Should have sample data
        assert stats.total_size_bytes >= 0

    def test_get_database_metadata(self, postgres_adapter):
        """Test getting complete database metadata"""
        db_metadata = postgres_adapter.get_database_metadata()

        assert db_metadata.database_name == "test_database"
        assert len(db_metadata.schemas) >= 3  # public, sales, inventory

        # Find public schema
        public_schema = next(s for s in db_metadata.schemas if s.schema_name == "public")
        assert len(public_schema.tables) >= 7  # users, products, orders, etc.

        # Find users table
        users_table = next(t for t in public_schema.tables if t.table_name == "users")
        assert len(users_table.columns) >= 10
        assert len(users_table.primary_keys) == 1
        assert len(users_table.indexes) >= 3


# =============================================
# TEST: Schema Introspection (MySQL)
# =============================================


class TestMySQLIntrospection:
    """Tests for MySQL schema introspection"""

    @pytest.fixture
    def mysql_adapter(self, mysql_config):
        """MySQL adapter connected to test database"""
        adapter = MySQLAdapter(mysql_config.to_adapter_config())
        adapter.connect()
        yield adapter
        adapter.disconnect()

    def test_list_tables(self, mysql_adapter):
        """Test listing all tables in test_database"""
        tables = mysql_adapter.list_tables("test_database")

        table_names = [t.table_name for t in tables]
        assert "users" in table_names
        assert "products" in table_names
        assert "orders" in table_names
        assert "categories" in table_names
        assert "reviews" in table_names

    def test_get_table_columns_users(self, mysql_adapter):
        """Test getting columns for users table"""
        columns = mysql_adapter.get_table_columns("test_database", "users")

        column_map = {col.column_name: col for col in columns}

        # Check specific columns
        assert "id" in column_map
        assert "username" in column_map
        assert "email" in column_map

        # Check TINYINT(1) → BOOLEAN mapping
        is_active_col = column_map["is_active"]
        assert is_active_col.data_type == DataType.BOOLEAN

        # Check JSON column
        metadata_col = column_map["metadata"]
        assert metadata_col.data_type == DataType.JSON

    def test_get_table_columns_user_profiles(self, mysql_adapter):
        """Test getting columns with ENUM type"""
        columns = mysql_adapter.get_table_columns("test_database", "user_profiles")

        column_map = {col.column_name: col for col in columns}

        # Check ENUM column
        gender_col = column_map["gender"]
        assert gender_col.data_type == DataType.VARCHAR  # ENUM mapped to VARCHAR
        assert gender_col.enum_values is not None
        assert "male" in gender_col.enum_values
        assert "female" in gender_col.enum_values

    def test_get_foreign_keys(self, mysql_adapter):
        """Test getting foreign key constraints"""
        fks = mysql_adapter.get_foreign_keys("products", "test_database")

        # Products has FK to categories
        assert len(fks) >= 1

        category_fk = next(fk for fk in fks if "category" in fk.constraint_name.lower())

        assert category_fk.referenced_table == "categories"
        assert "category_id" in category_fk.column_names

    def test_get_database_metadata(self, mysql_adapter):
        """Test getting complete database metadata"""
        db_metadata = mysql_adapter.get_database_metadata()

        assert db_metadata.database_name == "test_database"
        assert len(db_metadata.schemas) == 1  # MySQL uses single schema per connection

        schema = db_metadata.schemas[0]
        assert len(schema.tables) >= 10


# =============================================
# TEST: Session Expiration
# =============================================


class TestSessionExpiration:
    """Tests for session expiration behavior"""

    def test_session_expires_after_ttl(
        self, db_connection_service, postgres_config, redis_test_client
    ):
        """Test that session expires after TTL"""
        user_id = "100"

        # Create session with 1 second TTL (for testing)
        # Note: We'll manipulate Redis directly for faster testing
        response = db_connection_service.create_session(
            user_id=user_id,
            config=postgres_config,
            ttl_hours=3,
        )

        # Manually set TTL to 1 second for testing
        redis_key = db_connection_service._get_redis_key(user_id, response.session_id)
        redis_test_client.expire(redis_key, 1)

        # Wait for expiration
        time.sleep(2)

        # Try to retrieve - should fail
        with pytest.raises(SessionNotFoundError):
            db_connection_service.get_session(user_id, response.session_id)

    def test_expired_session_removed_from_list(
        self, db_connection_service, postgres_config, redis_test_client
    ):
        """Test that expired sessions are filtered from list"""
        user_id = "101"

        # Create two sessions
        session1 = db_connection_service.create_session(user_id, postgres_config)
        session2 = db_connection_service.create_session(user_id, postgres_config)

        # Expire session1
        redis_key1 = db_connection_service._get_redis_key(user_id, session1.session_id)
        redis_test_client.expire(redis_key1, 1)
        time.sleep(2)

        # List sessions - should only return session2
        sessions = db_connection_service.list_user_sessions(user_id)
        assert len(sessions) == 1
        assert sessions[0].session_id == session2.session_id


# =============================================
# RUN TESTS
# =============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
