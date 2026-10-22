"""
Unit tests for app.services.db_connection_service module

Tests for DBConnectionService with mocked Redis and database adapters:
- Connection testing
- Session creation with encryption
- Session retrieval and decryption
- Session deletion
- Session refresh (TTL extension)
- Error handling
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.models.db_connection import DBConnectionConfig, DBConnectionSession, DBConnectionTestResult
from app.services.db_connection_service import (
    DBConnectionService,
    DBConnectionServiceError,
    SessionExpiredError,
    SessionNotFoundError,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis = MagicMock()
    redis.hset = MagicMock(return_value=True)
    redis.hgetall = MagicMock(return_value={})
    redis.expire = MagicMock(return_value=True)
    redis.delete = MagicMock(return_value=1)
    redis.keys = MagicMock(return_value=[])
    return redis


@pytest.fixture
def encryption_key():
    """Test encryption key"""
    return "ZGF0YW1hcC10ZXN0LW1hc3Rlci1rZXktMzItYnl0ZXM="  # base64 de 32 bytes


@pytest.fixture
def service(mock_redis, encryption_key):
    """DBConnectionService instance"""
    return DBConnectionService(mock_redis, encryption_key)


@pytest.fixture
def valid_pg_config():
    """Valid PostgreSQL config"""
    return DBConnectionConfig(
        dialect="postgresql",
        host="localhost",
        port=5432,
        database="testdb",
        user="testuser",
        password="testpass",
    )


@pytest.fixture
def valid_mysql_config():
    """Valid MySQL config"""
    return DBConnectionConfig(
        dialect="mysql",
        host="localhost",
        port=3306,
        database="testdb",
        user="testuser",
        password="testpass",
    )


# ============================================================================
# TEST test_connection()
# ============================================================================


class TestTestConnection:
    """Tests for test_connection() method"""

    @patch("app.services.db_connection_service.PostgreSQLAdapter")
    def test_successful_postgresql_connection(self, mock_adapter_class, service, valid_pg_config):
        """Test: Successful PostgreSQL connection test"""
        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter_class.return_value = mock_adapter

        result = service.test_connection(valid_pg_config)

        assert result.success is True
        assert result.dialect == "postgresql"
        assert result.host == "localhost"
        assert result.database == "testdb"
        assert result.error_message is None

    @patch("app.services.db_connection_service.MySQLAdapter")
    def test_successful_mysql_connection(self, mock_adapter_class, service, valid_mysql_config):
        """Test: Successful MySQL connection test"""
        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter_class.return_value = mock_adapter

        result = service.test_connection(valid_mysql_config)

        assert result.success is True
        assert result.dialect == "mysql"

    @patch("app.services.db_connection_service.PostgreSQLAdapter")
    def test_authentication_error(self, mock_adapter_class, service, valid_pg_config):
        """Test: Authentication error returns error result"""
        from app.utils.db_adapters import DBAuthenticationError

        mock_adapter = MagicMock()
        mock_adapter.test_connection.side_effect = DBAuthenticationError("Invalid password")
        mock_adapter_class.return_value = mock_adapter

        result = service.test_connection(valid_pg_config)

        assert result.success is False
        assert result.error_type == "authentication"
        # El detalle del driver solo va al log, no a la respuesta
        assert "Invalid password" not in result.error_message
        assert "Authentication failed" in result.error_message

    @patch("app.services.db_connection_service.PostgreSQLAdapter")
    def test_connection_error(self, mock_adapter_class, service, valid_pg_config):
        """Test: Connection error returns error result"""
        from app.utils.db_adapters import DBConnectionError

        mock_adapter = MagicMock()
        mock_adapter.test_connection.side_effect = DBConnectionError("Cannot connect")
        mock_adapter_class.return_value = mock_adapter

        result = service.test_connection(valid_pg_config)

        assert result.success is False
        assert result.error_type == "connection"


# ============================================================================
# TEST create_session()
# ============================================================================


class TestCreateSession:
    """Tests for create_session() method"""

    @patch("app.services.db_connection_service.PostgreSQLAdapter")
    def test_create_session_success(self, mock_adapter_class, service, valid_pg_config, mock_redis):
        """Test: Successfully create session"""
        # Mock successful connection test
        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        mock_adapter_class.return_value = mock_adapter

        response = service.create_session(
            user_id="123",
            config=valid_pg_config,
            ttl_hours=3,
        )

        # Verify response
        assert response.session_id is not None
        assert response.dialect == "postgresql"
        assert response.host == "localhost"
        assert response.database == "testdb"

        # Verify Redis calls
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

    def test_create_session_ttl_validation(self, service, valid_pg_config):
        """Test: TTL validation (max 24 hours)"""
        with pytest.raises(ValueError, match="TTL cannot exceed"):
            service.create_session(
                user_id="123",
                config=valid_pg_config,
                ttl_hours=25,  # Exceeds max
            )

    @patch("app.services.db_connection_service.PostgreSQLAdapter")
    def test_create_session_skip_connection_test(
        self, mock_adapter_class, service, valid_pg_config, mock_redis
    ):
        """Test: Create session without testing connection"""
        response = service.create_session(
            user_id="123",
            config=valid_pg_config,
            test_connection=False,
        )

        assert response.session_id is not None
        # Adapter should not be called
        mock_adapter_class.assert_not_called()

    @patch("app.services.db_connection_service.PostgreSQLAdapter")
    def test_create_session_failed_connection_test(
        self, mock_adapter_class, service, valid_pg_config
    ):
        """Test: Failed connection test prevents session creation"""
        from app.utils.db_adapters import DBAuthenticationError

        mock_adapter = MagicMock()
        mock_adapter.test_connection.side_effect = DBAuthenticationError("Invalid password")
        mock_adapter_class.return_value = mock_adapter

        with pytest.raises(DBConnectionServiceError, match="Connection test failed"):
            service.create_session(
                user_id="123",
                config=valid_pg_config,
                test_connection=True,
            )


# ============================================================================
# TEST get_session()
# ============================================================================


class TestGetSession:
    """Tests for get_session() method"""

    def test_get_session_success(self, service, mock_redis):
        """Test: Successfully retrieve session"""
        # Mock Redis response
        session_id = "test-session-123"
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=3)

        mock_redis.hgetall.return_value = {
            b"session_id": session_id.encode(),
            b"user_id": b"123",
            b"project_id": b"456",
            b"dialect": b"postgresql",
            b"host": b"localhost",
            b"database": b"testdb",
            b"encrypted_credentials": b"encrypted_data",
            b"created_at": now.isoformat().encode(),
            b"expires_at": expires_at.isoformat().encode(),
            b"last_used_at": now.isoformat().encode(),
        }

        session = service.get_session(user_id="123", session_id=session_id)

        assert session.session_id == session_id
        assert session.user_id == "123"
        assert session.dialect == "postgresql"

    def test_get_session_not_found(self, service, mock_redis):
        """Test: Session not found raises error"""
        mock_redis.hgetall.return_value = {}

        with pytest.raises(SessionNotFoundError):
            service.get_session(user_id="123", session_id="nonexistent")

    def test_get_session_expired(self, service, mock_redis):
        """Test: Expired session raises error"""
        session_id = "test-session-123"
        now = datetime.utcnow()
        expired_at = now - timedelta(hours=1)  # Expired 1 hour ago

        mock_redis.hgetall.return_value = {
            b"session_id": session_id.encode(),
            b"user_id": b"123",
            b"dialect": b"postgresql",
            b"host": b"localhost",
            b"database": b"testdb",
            b"encrypted_credentials": b"encrypted_data",
            b"created_at": (now - timedelta(hours=4)).isoformat().encode(),
            b"expires_at": expired_at.isoformat().encode(),
            b"last_used_at": now.isoformat().encode(),
        }

        with pytest.raises(SessionExpiredError):
            service.get_session(user_id="123", session_id=session_id)

        # Should delete expired session
        mock_redis.delete.assert_called_once()


# ============================================================================
# TEST delete_session()
# ============================================================================


class TestDeleteSession:
    """Tests for delete_session() method"""

    def test_delete_session_success(self, service, mock_redis):
        """Test: Successfully delete session"""
        mock_redis.delete.return_value = 1

        result = service.delete_session(user_id="123", session_id="test-session-123")

        assert result is True
        mock_redis.delete.assert_called_once()

    def test_delete_session_not_found(self, service, mock_redis):
        """Test: Delete non-existent session returns False"""
        mock_redis.delete.return_value = 0

        result = service.delete_session(user_id="123", session_id="nonexistent")

        assert result is False


# ============================================================================
# TEST refresh_session()
# ============================================================================


class TestRefreshSession:
    """Tests for refresh_session() method"""

    def test_refresh_session_success(self, service, mock_redis):
        """Test: Successfully refresh session TTL"""
        session_id = "test-session-123"
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=3)

        mock_redis.hgetall.return_value = {
            b"session_id": session_id.encode(),
            b"user_id": b"123",
            b"dialect": b"postgresql",
            b"host": b"localhost",
            b"database": b"testdb",
            b"encrypted_credentials": b"encrypted_data",
            b"created_at": now.isoformat().encode(),
            b"expires_at": expires_at.isoformat().encode(),
            b"last_used_at": now.isoformat().encode(),
        }

        new_expires_at = service.refresh_session(
            user_id="123",
            session_id=session_id,
            ttl_hours=5,
        )

        assert new_expires_at > expires_at
        mock_redis.expire.assert_called_once()

    def test_refresh_session_ttl_validation(self, service):
        """Test: Refresh session validates TTL max"""
        with pytest.raises(ValueError, match="TTL cannot exceed"):
            service.refresh_session(
                user_id="123",
                session_id="test-session-123",
                ttl_hours=25,
            )


# ============================================================================
# TEST get_decrypted_config()
# ============================================================================


class TestGetDecryptedConfig:
    """Tests for get_decrypted_config() method"""

    @patch("app.services.db_connection_service.EncryptionManager")
    def test_get_decrypted_config_success(self, mock_encryption_class, service):
        """Test: Successfully decrypt config"""
        # Mock encryption manager
        mock_encryption = MagicMock()
        credentials_dict = {
            "host": "localhost",
            "port": 5432,
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
            "timeout": 30,
        }

        # Mock the methods that get_decrypted_config actually uses
        mock_encryption.AES_NONCE_LENGTH = 12
        mock_encryption.decode_from_storage.return_value = (
            b"\x00" * 12 + b"encrypted_data"
        )  # nonce + ciphertext
        mock_encryption.decrypt_field.return_value = json.dumps(credentials_dict)
        service.encryption_manager = mock_encryption

        # Create session
        session = DBConnectionSession(
            session_id="test-123",
            user_id="123",
            dialect="postgresql",
            host="localhost",
            database="testdb",
            encrypted_credentials="encrypted_data",
            expires_at=datetime.utcnow() + timedelta(hours=3),
        )

        config = service.get_decrypted_config(session)

        assert config.dialect == "postgresql"
        assert config.host == "localhost"
        assert config.password == "testpass"


# ============================================================================
# TEST _get_adapter()
# ============================================================================


class TestGetAdapter:
    """Tests for _get_adapter() method"""

    def test_get_adapter_postgresql(self, service, valid_pg_config):
        """Test: Get PostgreSQL adapter"""
        from app.utils.db_adapters import PostgreSQLAdapter

        with patch("app.services.db_connection_service.PostgreSQLAdapter") as mock:
            service._get_adapter(valid_pg_config)
            mock.assert_called_once()

    def test_get_adapter_mysql(self, service, valid_mysql_config):
        """Test: Get MySQL adapter"""
        with patch("app.services.db_connection_service.MySQLAdapter") as mock:
            service._get_adapter(valid_mysql_config)
            mock.assert_called_once()

    def test_get_adapter_unsupported_dialect(self, service):
        """Test: Unsupported dialect raises error"""
        # Use model_construct to bypass Pydantic validation
        config = DBConnectionConfig.model_construct(
            dialect="mongodb",  # Not supported
            host="localhost",
            port=27017,
            database="testdb",
            user="testuser",
            password="testpass",
        )

        with pytest.raises(DBConnectionServiceError, match="Unsupported dialect"):
            service._get_adapter(config)


# ============================================================================
# TEST: Redis real (fakeredis) con y sin decode_responses
# ============================================================================


class TestRedisClientCompatibility:
    """
    El router de migración usa el cliente compartido (decode_responses=True) y el de
    conexiones uno sin decodificar; el servicio debe funcionar con ambos.
    """

    @pytest.mark.parametrize("decode_responses", [False, True])
    def test_session_roundtrip(self, decode_responses, encryption_key):
        import fakeredis

        redis_client = fakeredis.FakeRedis(decode_responses=decode_responses)
        service = DBConnectionService(redis_client, encryption_key)
        config = DBConnectionConfig(
            dialect="oracle",
            host="db.example.com",
            port=1521,
            database="ORCLPDB1.dominio",
            user="scott",
            password="tiger",
            service_name="ORCLPDB1.dominio",
        )

        with patch("app.services.db_connection_service.validate_connection_host"):
            session = service.create_session("user-1", config, test_connection=False)

        restored = service.get_session("user-1", session.session_id)
        decrypted = service.get_decrypted_config(restored)

        assert decrypted.service_name == "ORCLPDB1.dominio"
        assert decrypted.to_adapter_config()["service_name"] == "ORCLPDB1.dominio"
        assert [s.session_id for s in service.list_user_sessions("user-1")] == [session.session_id]


class TestOracleConnectionTarget:
    """service_name/sid se conservan (antes Pydantic los descartaba)"""

    def test_service_name_and_sid_reach_adapter_config(self):
        config = DBConnectionConfig(
            dialect="oracle",
            host="db.example.com",
            port=1521,
            database="ORCL",
            user="scott",
            password="tiger",
            sid="ORCL1",
        )
        adapter_config = config.to_adapter_config()
        assert adapter_config["sid"] == "ORCL1"
        assert "service_name" not in adapter_config

    def test_blank_values_are_ignored(self):
        config = DBConnectionConfig(
            dialect="oracle",
            host="db.example.com",
            port=1521,
            database="ORCL",
            user="scott",
            password="tiger",
            service_name="  ",
        )
        assert config.service_name is None

    def test_control_characters_rejected(self):
        with pytest.raises(ValueError):
            DBConnectionConfig(
                dialect="oracle",
                host="db.example.com",
                port=1521,
                database="ORCL",
                user="scott",
                password="tiger",
                service_name="ORCL)(HOST=evil\n",
            )


class TestRefreshTtlBounds:
    """Con ttl_hours <= 0 la sesión acababa como clave huérfana sin TTL"""

    @pytest.mark.parametrize("ttl_hours", [0, -1])
    def test_non_positive_ttl_is_rejected(self, ttl_hours, encryption_key):
        import fakeredis

        redis_client = fakeredis.FakeRedis()
        service = DBConnectionService(redis_client, encryption_key)
        config = DBConnectionConfig(
            dialect="postgresql",
            host="db.example.com",
            port=5432,
            database="d",
            user="u",
            password="p",
        )
        with patch("app.services.db_connection_service.validate_connection_host"):
            session = service.create_session("u1", config, test_connection=False)
        key = service._get_redis_key("u1", session.session_id)

        with pytest.raises(ValueError):
            service.refresh_session("u1", session.session_id, ttl_hours)

        assert redis_client.ttl(key) > 0
        assert service.get_session("u1", session.session_id).session_id == session.session_id

    def test_session_expiring_meanwhile_is_not_recreated(self, encryption_key):
        import fakeredis

        redis_client = fakeredis.FakeRedis()
        service = DBConnectionService(redis_client, encryption_key)
        config = DBConnectionConfig(
            dialect="postgresql",
            host="db.example.com",
            port=5432,
            database="d",
            user="u",
            password="p",
        )
        with patch("app.services.db_connection_service.validate_connection_host"):
            session = service.create_session("u1", config, test_connection=False)
        key = service._get_redis_key("u1", session.session_id)

        real_get_session = service.get_session

        def get_then_expire(*args):
            result = real_get_session(*args)
            redis_client.delete(key)  # caduca justo después de comprobarla
            return result

        with patch.object(service, "get_session", side_effect=get_then_expire):
            with pytest.raises(SessionNotFoundError):
                service.refresh_session("u1", session.session_id, 3)

        assert not redis_client.exists(key)


# ============================================================================
# TEST: Sesiones atadas a un proyecto
# ============================================================================


class TestSessionProjectScope:
    """Una sesión creada con project_id solo se puede usar desde ese proyecto"""

    @pytest.fixture
    def real_service(self, encryption_key):
        import fakeredis

        return DBConnectionService(fakeredis.FakeRedis(decode_responses=True), encryption_key)

    def _create(self, service, config, project_id):
        with patch("app.services.db_connection_service.validate_connection_host"):
            return service.create_session(
                "user-1", config, project_id=project_id, test_connection=False
            ).session_id

    def test_bound_session_is_usable_from_its_project(self, real_service, valid_pg_config):
        session_id = self._create(real_service, valid_pg_config, "project-a")

        session = real_service.get_session("user-1", session_id, project_id="project-a")

        assert session.project_id == "project-a"

    def test_bound_session_is_not_found_from_another_project(self, real_service, valid_pg_config):
        from app.services.db_connection_service import SessionProjectMismatchError

        session_id = self._create(real_service, valid_pg_config, "project-a")

        with pytest.raises(SessionProjectMismatchError):
            real_service.get_session("user-1", session_id, project_id="project-b")
        # Para los que la usan, es como si no existiera (404)
        assert issubclass(SessionProjectMismatchError, SessionNotFoundError)

    def test_unbound_session_is_usable_from_any_project(self, real_service, valid_pg_config):
        session_id = self._create(real_service, valid_pg_config, None)

        assert real_service.get_session("user-1", session_id, project_id="project-b")
        assert real_service.get_session("user-1", session_id)

    def test_bound_session_without_project_context_still_works(self, real_service, valid_pg_config):
        # Endpoints de /db-connections (introspección) no tienen proyecto en la ruta
        session_id = self._create(real_service, valid_pg_config, "project-a")

        assert real_service.get_session("user-1", session_id).project_id == "project-a"
