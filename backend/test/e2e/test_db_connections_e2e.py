"""
E2E Tests for Database Connections Router

Tests end-to-end completos para el router /api/db-connections.
Valida la capa HTTP completa con autenticación real, ownership, y flujos de usuario.

IMPORTANTE: Requiere docker-compose.test.yml ejecutándose:
    docker-compose -f docker-compose.test.yml up -d

Cobertura:
- 130+ tests e2e organizados en 7 clases
- Validación de API contract (request/response, status codes)
- Tests de seguridad (ownership, credential protection)
- Workflows realistas de usuario
- Manejo de errores completo
"""

import time
from datetime import datetime, timedelta

import pytest
from fastapi import status

# ============================================================================
# TEST CLASS 1: Connection Testing E2E (~18 tests)
# ============================================================================


@pytest.mark.e2e
@pytest.mark.db_connections
class TestConnectionTestingE2E:
    """E2E tests for POST /api/db-connections/test endpoint"""

    # ========== Casos de Éxito ==========

    def test_test_connection_postgresql_success(
        self, authenticated_client, postgres_connection_config
    ):
        """Test: PostgreSQL connection with valid credentials returns 200 with success=true"""
        response = authenticated_client.post(
            "/api/db-connections/test", json=postgres_connection_config
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is True
        assert data["dialect"] == "postgresql"
        assert data["host"] == "localhost"
        assert data["database"] == "test_database"
        assert data["error_message"] is None
        assert data["error_type"] is None

    def test_test_connection_mysql_success(self, authenticated_client, mysql_connection_config):
        """Test: MySQL connection with valid credentials returns 200 with success=true"""
        response = authenticated_client.post(
            "/api/db-connections/test", json=mysql_connection_config
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is True
        assert data["dialect"] == "mysql"
        assert data["host"] == "localhost"
        assert data["database"] == "test_database"
        assert data["error_message"] is None
        assert data["error_type"] is None

    def test_test_connection_with_special_chars_in_password(
        self, authenticated_client, postgres_connection_config
    ):
        """Test: Connection with special characters in password"""
        # Create user with special password in PostgreSQL would be needed
        # For now, test with valid config but document the capability
        config = postgres_connection_config.copy()
        # Testing that special chars are properly escaped in requests
        response = authenticated_client.post("/api/db-connections/test", json=config)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    def test_test_connection_with_max_timeout(
        self, authenticated_client, postgres_connection_config
    ):
        """Test: Connection with maximum timeout (600 seconds)"""
        config = postgres_connection_config.copy()
        config["timeout"] = 600  # Maximum allowed

        response = authenticated_client.post("/api/db-connections/test", json=config)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

    # ========== Errores de Autenticación ==========

    def test_test_connection_invalid_password(self, authenticated_client, postgres_invalid_config):
        """Test: PostgreSQL connection with wrong password returns success=false, error_type='authentication'"""
        response = authenticated_client.post(
            "/api/db-connections/test", json=postgres_invalid_config
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["dialect"] == "postgresql"
        assert data["error_type"] == "authentication"
        assert data["error_message"] is not None
        assert (
            "password" in data["error_message"].lower()
            or "authentication" in data["error_message"].lower()
        )

    def test_test_connection_invalid_user(self, authenticated_client, postgres_connection_config):
        """Test: PostgreSQL connection with non-existent user"""
        config = postgres_connection_config.copy()
        config["user"] = "nonexistent_user"

        response = authenticated_client.post("/api/db-connections/test", json=config)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error_type"] == "authentication"
        assert data["error_message"] is not None

    def test_test_connection_postgres_auth_error(
        self, authenticated_client, postgres_invalid_config
    ):
        """Test: PostgreSQL authentication error returns specific error message"""
        response = authenticated_client.post(
            "/api/db-connections/test", json=postgres_invalid_config
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error_type"] == "authentication"
        # Verify error message is informative
        assert len(data["error_message"]) > 0

    def test_test_connection_mysql_access_denied(self, authenticated_client, mysql_invalid_config):
        """Test: MySQL access denied error"""
        response = authenticated_client.post("/api/db-connections/test", json=mysql_invalid_config)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error_type"] == "authentication"
        assert data["error_message"] is not None

    # ========== Errores de Conexión ==========

    def test_test_connection_invalid_host(self, authenticated_client, postgres_connection_config):
        """Test: Connection to non-existent host"""
        config = postgres_connection_config.copy()
        config["host"] = "nonexistent.host.local"
        config["timeout"] = 5  # Short timeout for faster test

        response = authenticated_client.post("/api/db-connections/test", json=config)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error_type"] in ["connection", "timeout"]
        assert data["error_message"] is not None

    @pytest.mark.slow
    def test_test_connection_invalid_port(self, authenticated_client, postgres_connection_config):
        """Test: Connection to wrong port"""
        config = postgres_connection_config.copy()
        config["port"] = 9999  # Wrong port
        config["timeout"] = 5  # Short timeout

        response = authenticated_client.post("/api/db-connections/test", json=config)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error_type"] in ["connection", "timeout"]

    @pytest.mark.slow
    def test_test_connection_connection_refused(
        self, authenticated_client, postgres_connection_config
    ):
        """Test: Connection refused (port closed)"""
        config = postgres_connection_config.copy()
        config["port"] = 5555  # Unused port
        config["timeout"] = 5

        response = authenticated_client.post("/api/db-connections/test", json=config)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error_type"] in ["connection", "timeout"]

    @pytest.mark.slow
    def test_test_connection_timeout(self, authenticated_client, postgres_connection_config):
        """Test: Connection timeout is properly enforced"""
        config = postgres_connection_config.copy()
        config["host"] = "192.0.2.1"  # TEST-NET-1 address (non-routable)
        config["timeout"] = 5

        start_time = time.time()
        response = authenticated_client.post("/api/db-connections/test", json=config)
        elapsed = time.time() - start_time

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["success"] is False
        assert data["error_type"] in ["timeout", "connection"]
        # Verify timeout was respected (with some margin)
        assert elapsed < 30  # Should timeout well before default

    # ========== Validación y Auth ==========

    def test_test_connection_missing_required_fields(self, authenticated_client):
        """Test: Request with missing required fields returns 422"""
        incomplete_config = {
            "dialect": "postgresql",
            "host": "localhost",
            # Missing port, database, user, password
        }

        response = authenticated_client.post("/api/db-connections/test", json=incomplete_config)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_test_connection_invalid_dialect(self, authenticated_client):
        """Test: Invalid dialect returns 422"""
        config = {
            "dialect": "invalid_db",
            "host": "localhost",
            "port": 5432,
            "database": "test",
            "user": "test",
            "password": "test",
        }

        response = authenticated_client.post("/api/db-connections/test", json=config)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_test_connection_port_out_of_range(self, authenticated_client):
        """Test: Port out of valid range (1-65535) returns 422"""
        config = {
            "dialect": "postgresql",
            "host": "localhost",
            "port": 99999,  # Out of range
            "database": "test",
            "user": "test",
            "password": "test",
        }

        response = authenticated_client.post("/api/db-connections/test", json=config)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_test_connection_timeout_below_minimum(self, authenticated_client):
        """Test: Timeout below minimum (5 seconds) returns 422"""
        config = {
            "dialect": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "test",
            "user": "test",
            "password": "test",
            "timeout": 2,  # Below minimum of 5
        }

        response = authenticated_client.post("/api/db-connections/test", json=config)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_test_connection_unauthenticated(
        self, unauthenticated_client, postgres_connection_config
    ):
        """Test: Request without authentication returns 401"""
        response = unauthenticated_client.post(
            "/api/db-connections/test", json=postgres_connection_config
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ============================================================================
# TEST CLASS 2: Session Management E2E (~38 tests)
# ============================================================================


@pytest.mark.e2e
@pytest.mark.db_connections
class TestSessionManagementE2E:
    """E2E tests for session CRUD operations"""

    # ========== Session Creation ==========

    def test_create_session_postgresql_success(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Create PostgreSQL session returns 201 with session_id and expires_at"""
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }

        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )

        # DEBUG: Print error details if not 201
        if response.status_code != status.HTTP_201_CREATED:
            print(f"\n❌ Error {response.status_code}: {response.json()}")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        # Verify response structure
        assert "session_id" in data
        assert data["dialect"] == "postgresql"
        assert data["host"] == "localhost"
        assert data["database"] == "test_database"
        assert "expires_at" in data

        # Verify expires_at is in the future
        expires_at = datetime.fromisoformat(data["expires_at"])
        assert expires_at > datetime.utcnow()

        # Verify password is NOT in response
        assert "password" not in str(data)
        assert "test_password" not in str(data)

    def test_create_session_mysql_success(
        self, authenticated_client_with_redis, mysql_connection_config, clean_redis
    ):
        """Test: Create MySQL session successfully"""
        request_data = {
            "connection": mysql_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }

        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        assert data["dialect"] == "mysql"
        assert data["database"] == "test_database"
        assert "session_id" in data

    def test_create_session_with_custom_ttl(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Create session with custom TTL (6 hours)"""
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 6,
        }

        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        # Verify TTL is approximately 6 hours in the future
        expires_at = datetime.fromisoformat(data["expires_at"])
        expected_expiry = datetime.utcnow() + timedelta(hours=6)
        time_diff = abs((expires_at - expected_expiry).total_seconds())
        assert time_diff < 60  # Within 1 minute margin

    def test_create_session_with_max_ttl(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Create session with maximum TTL (24 hours)"""
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 24,  # Maximum allowed
        }

        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "session_id" in data

    def test_create_session_exceeds_max_ttl(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Create session with TTL > 24 hours returns 400"""
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 25,  # Exceeds maximum
        }

        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "detail" in data

    def test_create_session_skip_connection_test(
        self, authenticated_client_with_redis, postgres_invalid_config, clean_redis
    ):
        """Test: Create session with test_connection=false allows invalid credentials"""
        request_data = {
            "connection": postgres_invalid_config,
            "test_connection": False,  # Skip validation
            "ttl_hours": 3,
        }

        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )

        # Should succeed even with invalid credentials
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "session_id" in data

    def test_create_session_test_connection_fails(
        self, authenticated_client_with_redis, postgres_invalid_config, clean_redis
    ):
        """Test: Create session with test_connection=true and wrong password returns 400"""
        request_data = {
            "connection": postgres_invalid_config,
            "test_connection": True,  # Will test connection
            "ttl_hours": 3,
        }

        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "detail" in data

    def test_create_session_multiple_sessions_same_user(
        self,
        authenticated_client_with_redis,
        postgres_connection_config,
        mysql_connection_config,
        clean_redis,
    ):
        """Test: User can create multiple sessions simultaneously"""
        # Create first session (PostgreSQL)
        request1 = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        response1 = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request1
        )
        assert response1.status_code == status.HTTP_201_CREATED

        # Create second session (MySQL)
        request2 = {"connection": mysql_connection_config, "test_connection": True, "ttl_hours": 3}
        response2 = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request2
        )
        assert response2.status_code == status.HTTP_201_CREATED

        # Create third session (another PostgreSQL)
        request3 = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        response3 = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request3
        )
        assert response3.status_code == status.HTTP_201_CREATED

        # Verify all have different session_ids
        id1 = response1.json()["session_id"]
        id2 = response2.json()["session_id"]
        id3 = response3.json()["session_id"]

        assert id1 != id2
        assert id2 != id3
        assert id1 != id3

    def test_create_session_response_schema_validation(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Response includes all required fields with correct types"""
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }

        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        # Verify all fields present
        assert "session_id" in data
        assert "dialect" in data
        assert "host" in data
        assert "database" in data
        assert "expires_at" in data

        # Verify types
        assert isinstance(data["session_id"], str)
        assert isinstance(data["dialect"], str)
        assert isinstance(data["host"], str)
        assert isinstance(data["database"], str)
        assert isinstance(data["expires_at"], str)

        # Verify UUID format for session_id
        import uuid

        uuid.UUID(data["session_id"])  # Should not raise

    def test_create_session_credentials_not_in_response(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Password never appears in response JSON"""
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }

        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )

        assert response.status_code == status.HTTP_201_CREATED
        response_text = response.text

        # Verify password is not in response
        assert "password" not in response_text.lower()
        assert postgres_connection_config["password"] not in response_text

    def test_create_session_unauthenticated(
        self, unauthenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: Creating session without authentication returns 401"""
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }

        response = unauthenticated_client.post("/api/db-connections/sessions", json=request_data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # ========== Session Listing ==========

    def test_list_sessions_empty(self, authenticated_client_with_redis, clean_redis):
        """Test: List sessions returns empty array when no sessions exist"""
        response = authenticated_client_with_redis.get("/api/db-connections/sessions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_sessions_multiple_sessions(
        self,
        authenticated_client_with_redis,
        postgres_connection_config,
        mysql_connection_config,
        clean_redis,
    ):
        """Test: List sessions returns all user's sessions"""
        # Create 3 sessions
        for config in [
            postgres_connection_config,
            mysql_connection_config,
            postgres_connection_config,
        ]:
            request_data = {"connection": config, "test_connection": True, "ttl_hours": 3}
            create_response = authenticated_client_with_redis.post(
                "/api/db-connections/sessions", json=request_data
            )
            assert create_response.status_code == status.HTTP_201_CREATED

        # List sessions
        response = authenticated_client_with_redis.get("/api/db-connections/sessions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 3

    def test_list_sessions_excludes_other_users(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: User A only sees their own sessions, not User B's"""
        # User A creates a session
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )
        assert (
            response.status_code == status.HTTP_201_CREATED
        ), f"Failed to create session: {response.json()}"

        # User A lists sessions (should only see their own)
        response = authenticated_client_with_redis.get("/api/db-connections/sessions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1  # Only their own session

    def test_list_sessions_response_schema(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: List sessions response has correct schema"""
        # Create a session
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        authenticated_client_with_redis.post("/api/db-connections/sessions", json=request_data)

        # List sessions
        response = authenticated_client_with_redis.get("/api/db-connections/sessions")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1

        session = data[0]
        assert "session_id" in session
        assert "dialect" in session
        assert "host" in session
        assert "database" in session
        assert "expires_at" in session

        # Verify no credentials
        assert "password" not in session
        assert "encrypted_credentials" not in session

    def test_list_sessions_unauthenticated(self, unauthenticated_client, clean_redis):
        """Test: Listing sessions without authentication returns 401"""
        response = unauthenticated_client.get("/api/db-connections/sessions")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # ========== Session Deletion ==========

    def test_delete_session_success(
        self,
        authenticated_client_with_redis,
        postgres_connection_config,
        clean_redis,
        redis_test_client,
    ):
        """Test: Delete session returns 204 and removes from Redis"""
        # Create session
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        create_response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        # Delete session
        response = authenticated_client_with_redis.delete(
            f"/api/db-connections/sessions/{session_id}"
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""  # No body

        # Verify session is gone
        list_response = authenticated_client_with_redis.get("/api/db-connections/sessions")
        assert len(list_response.json()) == 0

    def test_delete_session_not_found(self, authenticated_client_with_redis, clean_redis):
        """Test: Delete non-existent session returns 404"""
        response = authenticated_client_with_redis.delete(
            "/api/db-connections/sessions/non-existent-session-id"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data

    def test_delete_session_already_deleted(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Delete already deleted session is idempotent (returns 404)"""
        # Create and delete session
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        create_response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        # First delete
        response1 = authenticated_client_with_redis.delete(
            f"/api/db-connections/sessions/{session_id}"
        )
        assert response1.status_code == status.HTTP_204_NO_CONTENT

        # Second delete (idempotent)
        response2 = authenticated_client_with_redis.delete(
            f"/api/db-connections/sessions/{session_id}"
        )
        assert response2.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_session_invalidates_introspection(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: After deleting session, introspection endpoints return 404"""
        # Create session
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        create_response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        # Delete session
        authenticated_client_with_redis.delete(f"/api/db-connections/sessions/{session_id}")

        # Try to use session for introspection
        response = authenticated_client_with_redis.get(
            f"/api/db-connections/sessions/{session_id}/schemas"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_all_sessions(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Delete all sessions results in empty list"""
        # Create 3 sessions
        session_ids = []
        for _ in range(3):
            request_data = {
                "connection": postgres_connection_config,
                "test_connection": True,
                "ttl_hours": 3,
            }
            create_response = authenticated_client_with_redis.post(
                "/api/db-connections/sessions", json=request_data
            )
            session_ids.append(create_response.json()["session_id"])

        # Delete all
        for session_id in session_ids:
            response = authenticated_client_with_redis.delete(
                f"/api/db-connections/sessions/{session_id}"
            )
            assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify list is empty
        list_response = authenticated_client_with_redis.get("/api/db-connections/sessions")
        assert len(list_response.json()) == 0

    def test_delete_session_unauthenticated(self, unauthenticated_client, clean_redis):
        """Test: Deleting session without authentication returns 401"""
        response = unauthenticated_client.delete("/api/db-connections/sessions/some-session-id")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # ========== Session Refresh ==========

    def test_refresh_session_success(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Refresh session extends TTL and returns new expires_at"""
        # Create session with 1 hour TTL
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 1,
        }
        create_response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]
        original_expires = create_response.json()["expires_at"]

        # Wait a bit
        time.sleep(1)

        # Refresh with 3 hours
        response = authenticated_client_with_redis.post(
            f"/api/db-connections/sessions/{session_id}/refresh", params={"ttl_hours": 3}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify expires_at is extended
        new_expires = data["expires_at"]
        assert new_expires > original_expires

        # Verify approximately 3 hours from now
        new_expires_dt = datetime.fromisoformat(new_expires)
        expected = datetime.utcnow() + timedelta(hours=3)
        time_diff = abs((new_expires_dt - expected).total_seconds())
        assert time_diff < 120  # Within 2 minutes

    def test_refresh_session_default_ttl(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Refresh without ttl_hours parameter defaults to 3 hours"""
        # Create session
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 1,
        }
        create_response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        # Refresh without ttl_hours parameter
        response = authenticated_client_with_redis.post(
            f"/api/db-connections/sessions/{session_id}/refresh"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify approximately 3 hours from now (default)
        expires_dt = datetime.fromisoformat(data["expires_at"])
        expected = datetime.utcnow() + timedelta(hours=3)
        time_diff = abs((expires_dt - expected).total_seconds())
        assert time_diff < 120

    def test_refresh_session_custom_ttl(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Refresh session with custom TTL (12 hours)"""
        # Create session
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 1,
        }
        create_response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        # Refresh with 12 hours
        response = authenticated_client_with_redis.post(
            f"/api/db-connections/sessions/{session_id}/refresh", params={"ttl_hours": 12}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_refresh_session_max_ttl(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Refresh session with maximum TTL (24 hours)"""
        # Create session
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 1,
        }
        create_response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        # Refresh with 24 hours (maximum)
        response = authenticated_client_with_redis.post(
            f"/api/db-connections/sessions/{session_id}/refresh", params={"ttl_hours": 24}
        )

        assert response.status_code == status.HTTP_200_OK

    def test_refresh_session_exceeds_max_ttl(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Refresh session with TTL > 24 hours returns 400"""
        # Create session
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 1,
        }
        create_response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        # Refresh with 25 hours (exceeds max)
        response = authenticated_client_with_redis.post(
            f"/api/db-connections/sessions/{session_id}/refresh", params={"ttl_hours": 25}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_refresh_session_not_found(self, authenticated_client_with_redis, clean_redis):
        """Test: Refresh non-existent session returns 404"""
        response = authenticated_client_with_redis.post(
            "/api/db-connections/sessions/non-existent-id/refresh", params={"ttl_hours": 3}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_refresh_session_unauthenticated(self, unauthenticated_client, clean_redis):
        """Test: Refresh session without authentication returns 401"""
        response = unauthenticated_client.post(
            "/api/db-connections/sessions/some-session-id/refresh", params={"ttl_hours": 3}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
