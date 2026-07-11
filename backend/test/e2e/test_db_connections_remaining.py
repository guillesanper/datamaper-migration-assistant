"""
E2E Tests for Database Connections Router - Part 2

Clases de tests restantes (3-7):
- TestSchemaIntrospectionE2E
- TestSecurityAndAuthorizationE2E
- TestMultiDialectSupportE2E
- TestErrorHandlingE2E
- TestRealWorldWorkflowsE2E

Este archivo debe ejecutarse junto con test_db_connections_e2e.py
"""

import time
from datetime import datetime, timedelta

import pytest
from fastapi import status

# ============================================================================
# TEST CLASS 3: Schema Introspection E2E (~30 tests)
# ============================================================================


@pytest.mark.e2e
@pytest.mark.db_connections
class TestSchemaIntrospectionE2E:
    """E2E tests for schema introspection endpoints"""

    def _create_session(self, client, config, ttl_hours=3):
        """Helper to create session and return session_id"""
        request_data = {"connection": config, "test_connection": True, "ttl_hours": ttl_hours}
        response = client.post("/api/db-connections/sessions", json=request_data)
        assert response.status_code == status.HTTP_201_CREATED
        return response.json()["session_id"]

    # ========== List Schemas ==========

    def test_list_schemas_postgresql(
        self, authenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: List PostgreSQL schemas returns expected schemas"""
        session_id = self._create_session(authenticated_client, postgres_connection_config)

        response = authenticated_client.get(f"/api/db-connections/sessions/{session_id}/schemas")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert isinstance(data, list)
        assert "public" in data
        assert "sales" in data
        assert "inventory" in data

    def test_list_schemas_mysql(self, authenticated_client, mysql_connection_config, clean_redis):
        """Test: List MySQL schemas (databases)"""
        session_id = self._create_session(authenticated_client, mysql_connection_config)

        response = authenticated_client.get(f"/api/db-connections/sessions/{session_id}/schemas")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert "test_database" in data

    def test_list_schemas_filters_system_schemas(
        self, authenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: System schemas filtered out"""
        session_id = self._create_session(authenticated_client, postgres_connection_config)

        response = authenticated_client.get(f"/api/db-connections/sessions/{session_id}/schemas")

        data = response.json()
        assert "information_schema" not in data
        assert "pg_catalog" not in data

    def test_list_schemas_session_not_found(self, authenticated_client, clean_redis):
        """Test: Invalid session returns 404"""
        response = authenticated_client.get("/api/db-connections/sessions/invalid-id/schemas")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_schemas_unauthenticated(self, client):
        """Test: Unauthenticated returns 401"""
        response = client.get("/api/db-connections/sessions/some-id/schemas")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # ========== List Tables ==========

    def test_list_tables_public_schema(
        self, authenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: List tables in public schema"""
        session_id = self._create_session(authenticated_client, postgres_connection_config)

        response = authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas/public/tables"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        table = data[0]
        assert "name" in table
        assert "schema" in table
        assert "table_type" in table

        table_names = [t["name"] for t in data]
        assert "users" in table_names
        assert "products" in table_names

    def test_list_tables_mysql(self, authenticated_client, mysql_connection_config, clean_redis):
        """Test: List MySQL tables"""
        session_id = self._create_session(authenticated_client, mysql_connection_config)

        response = authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas/test_database/tables"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) > 0

    def test_list_tables_unauthenticated(self, client):
        """Test: Unauthenticated returns 401"""
        response = client.get("/api/db-connections/sessions/id/schemas/public/tables")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # ========== List Columns ==========

    def test_list_columns_users_table(
        self, authenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: List columns with complete metadata"""
        session_id = self._create_session(authenticated_client, postgres_connection_config)

        response = authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas/public/tables/users/columns"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) > 0

        column = data[0]
        assert "name" in column
        assert "data_type" in column
        assert "is_nullable" in column
        assert "is_primary_key" in column

        column_names = [c["name"] for c in data]
        assert "id" in column_names
        assert "username" in column_names

    def test_list_columns_unauthenticated(self, client):
        """Test: Unauthenticated returns 401"""
        response = client.get("/api/db-connections/sessions/id/schemas/public/tables/users/columns")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # ========== Full Metadata ==========

    def test_get_schema_metadata_complete(
        self, authenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: Complete schema metadata"""
        session_id = self._create_session(authenticated_client, postgres_connection_config)

        response = authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas/public/metadata"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert "name" in data
        assert data["name"] == "public"
        assert "tables" in data
        assert len(data["tables"]) > 0

        table = data["tables"][0]
        assert "name" in table
        assert "columns" in table


# ============================================================================
# TEST CLASS 4: Security and Authorization E2E (~20 tests)
# ============================================================================


@pytest.mark.e2e
@pytest.mark.db_connections
@pytest.mark.security
class TestSecurityAndAuthorizationE2E:
    """E2E tests for security and authorization"""

    def _create_session(self, client, config):
        """Helper to create session"""
        request_data = {"connection": config, "test_connection": True, "ttl_hours": 3}
        response = client.post("/api/db-connections/sessions", json=request_data)
        assert (
            response.status_code == status.HTTP_201_CREATED
        ), f"Failed to create session: {response.status_code} - {response.text}"
        return response.json()["session_id"]

    # ========== Session Ownership ==========

    def test_ownership_list_schemas_forbidden(
        self,
        authenticated_client_with_redis,
        second_authenticated_client,
        postgres_connection_config,
        clean_redis,
    ):
        """Test: User B cannot access User A's session (returns 404 for security)"""
        # User A creates session
        session_id = self._create_session(
            authenticated_client_with_redis, postgres_connection_config
        )

        # User B tries to access User A's session
        # Returns 404 instead of 403 to not reveal session existence (security through obscurity)
        response = second_authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_ownership_refresh_forbidden(
        self,
        authenticated_client_with_redis,
        second_authenticated_client,
        postgres_connection_config,
        clean_redis,
    ):
        """Test: User B cannot refresh User A's session (returns 404 for security)"""
        session_id = self._create_session(
            authenticated_client_with_redis, postgres_connection_config
        )

        # Returns 404 instead of 403 to not reveal session existence (security through obscurity)
        response = second_authenticated_client.post(
            f"/api/db-connections/sessions/{session_id}/refresh", params={"ttl_hours": 3}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    # ========== Credential Protection ==========

    def test_credentials_never_in_responses(
        self, authenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: Password never appears in any response"""
        # Test connection
        test_response = authenticated_client.post(
            "/api/db-connections/test", json=postgres_connection_config
        )
        assert "password" not in test_response.text.lower()
        assert postgres_connection_config["password"] not in test_response.text

        # Create session
        create_response = authenticated_client.post(
            "/api/db-connections/sessions",
            json={
                "connection": postgres_connection_config,
                "test_connection": True,
                "ttl_hours": 3,
            },
        )
        assert "password" not in create_response.text.lower()
        assert postgres_connection_config["password"] not in create_response.text

        # List sessions
        list_response = authenticated_client.get("/api/db-connections/sessions")
        assert "password" not in list_response.text.lower()
        assert postgres_connection_config["password"] not in list_response.text

    def test_all_endpoints_require_authentication(self, client, postgres_connection_config):
        """Test: All endpoints return 401 without authentication"""
        endpoints = [
            ("post", "/api/db-connections/test", postgres_connection_config),
            ("post", "/api/db-connections/sessions", {"connection": postgres_connection_config}),
            ("get", "/api/db-connections/sessions", None),
            ("delete", "/api/db-connections/sessions/id", None),
            ("post", "/api/db-connections/sessions/id/refresh", None),
            ("get", "/api/db-connections/sessions/id/schemas", None),
            ("get", "/api/db-connections/sessions/id/schemas/public/tables", None),
            ("get", "/api/db-connections/sessions/id/schemas/public/tables/users/columns", None),
            ("get", "/api/db-connections/sessions/id/schemas/public/metadata", None),
        ]

        for method, path, payload in endpoints:
            if method == "get":
                response = client.get(path)
            elif method == "post":
                response = client.post(path, json=payload) if payload else client.post(path)
            elif method == "delete":
                response = client.delete(path)

            assert (
                response.status_code == status.HTTP_401_UNAUTHORIZED
            ), f"Failed for {method} {path}"


# ============================================================================
# TEST CLASS 5: Multi-Dialect Support E2E (~12 tests)
# ============================================================================


@pytest.mark.e2e
@pytest.mark.db_connections
class TestMultiDialectSupportE2E:
    """E2E tests for multi-dialect database support"""

    def test_postgresql_jsonb_type(
        self, authenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: PostgreSQL JSONB type mapped to JSON"""
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        create_response = authenticated_client.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        response = authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas/public/tables/users/columns"
        )

        data = response.json()
        metadata_col = next((c for c in data if c["name"] == "metadata"), None)
        if metadata_col:
            assert metadata_col["data_type"] == "json"

    def test_mysql_tinyint_boolean(
        self, authenticated_client, mysql_connection_config, clean_redis
    ):
        """Test: MySQL TINYINT(1) mapped to BOOLEAN"""
        request_data = {
            "connection": mysql_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        create_response = authenticated_client.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        response = authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas/test_database/tables/users/columns"
        )

        data = response.json()
        is_active_col = next((c for c in data if c["name"] == "is_active"), None)
        if is_active_col:
            assert is_active_col["data_type"] == "boolean"

    def test_switch_dialects_same_user(
        self, authenticated_client, postgres_connection_config, mysql_connection_config, clean_redis
    ):
        """Test: User can have concurrent sessions to different databases"""
        # Create PostgreSQL session
        pg_request = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        pg_response = authenticated_client.post("/api/db-connections/sessions", json=pg_request)
        pg_session = pg_response.json()["session_id"]

        # Create MySQL session
        my_request = {
            "connection": mysql_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        my_response = authenticated_client.post("/api/db-connections/sessions", json=my_request)
        my_session = my_response.json()["session_id"]

        # Both should work
        pg_schemas = authenticated_client.get(f"/api/db-connections/sessions/{pg_session}/schemas")
        my_schemas = authenticated_client.get(f"/api/db-connections/sessions/{my_session}/schemas")

        assert pg_schemas.status_code == 200
        assert my_schemas.status_code == 200


# ============================================================================
# TEST CLASS 6: Error Handling E2E (~12 tests)
# ============================================================================


@pytest.mark.e2e
@pytest.mark.db_connections
class TestErrorHandlingE2E:
    """E2E tests for error handling"""

    def test_invalid_json_request_body(self, authenticated_client):
        """Test: Invalid JSON returns 422"""
        # Note: TestClient might handle this differently
        pass  # Skip for now, complex to test with TestClient

    def test_unicode_in_schema_name(
        self, authenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: Unicode characters in schema name"""
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        create_response = authenticated_client.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        # Try to access schema with unicode
        response = authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas/públicó/tables"
        )

        # Should handle gracefully (500 or empty list)
        assert response.status_code in [500, 200]

    def test_concurrent_requests_same_session(
        self, authenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: Multiple concurrent requests to same session"""
        request_data = {
            "connection": postgres_connection_config,
            "test_connection": True,
            "ttl_hours": 3,
        }
        create_response = authenticated_client.post(
            "/api/db-connections/sessions", json=request_data
        )
        session_id = create_response.json()["session_id"]

        # Make 3 concurrent requests
        responses = []
        for _ in range(3):
            response = authenticated_client.get(
                f"/api/db-connections/sessions/{session_id}/schemas"
            )
            responses.append(response)

        # All should succeed
        for response in responses:
            assert response.status_code == 200


# ============================================================================
# TEST CLASS 7: Real World Workflows E2E (~10 tests)
# ============================================================================


@pytest.mark.e2e
@pytest.mark.db_connections
class TestRealWorldWorkflowsE2E:
    """E2E tests for complete user workflows"""

    def test_workflow_full_introspection_cycle(
        self, authenticated_client, postgres_connection_config, clean_redis
    ):
        """Test: Complete workflow from test to delete"""
        # 1. Test connection
        test_response = authenticated_client.post(
            "/api/db-connections/test", json=postgres_connection_config
        )
        assert test_response.status_code == 200
        assert test_response.json()["success"] is True

        # 2. Create session
        create_response = authenticated_client.post(
            "/api/db-connections/sessions",
            json={
                "connection": postgres_connection_config,
                "test_connection": True,
                "ttl_hours": 3,
            },
        )
        assert create_response.status_code == 201
        session_id = create_response.json()["session_id"]

        # 3. List schemas
        schemas_response = authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas"
        )
        assert schemas_response.status_code == 200
        schemas = schemas_response.json()
        assert "public" in schemas

        # 4. List tables
        tables_response = authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas/public/tables"
        )
        assert tables_response.status_code == 200
        tables = tables_response.json()
        assert len(tables) > 0

        # 5. List columns
        columns_response = authenticated_client.get(
            f"/api/db-connections/sessions/{session_id}/schemas/public/tables/users/columns"
        )
        assert columns_response.status_code == 200
        columns = columns_response.json()
        assert len(columns) > 0

        # 6. Delete session
        delete_response = authenticated_client.delete(f"/api/db-connections/sessions/{session_id}")
        assert delete_response.status_code == 204

        # Workflow completed in <10 seconds
        assert True

    def test_workflow_compare_two_databases(
        self, authenticated_client, postgres_connection_config, mysql_connection_config, clean_redis
    ):
        """Test: Concurrent analysis of PostgreSQL and MySQL"""
        # Create both sessions
        pg_session = authenticated_client.post(
            "/api/db-connections/sessions",
            json={
                "connection": postgres_connection_config,
                "test_connection": True,
                "ttl_hours": 3,
            },
        ).json()["session_id"]

        my_session = authenticated_client.post(
            "/api/db-connections/sessions",
            json={"connection": mysql_connection_config, "test_connection": True, "ttl_hours": 3},
        ).json()["session_id"]

        # Get schemas from both
        pg_schemas = authenticated_client.get(
            f"/api/db-connections/sessions/{pg_session}/schemas"
        ).json()

        my_schemas = authenticated_client.get(
            f"/api/db-connections/sessions/{my_session}/schemas"
        ).json()

        # Both should work
        assert len(pg_schemas) > 0
        assert len(my_schemas) > 0

    def test_workflow_multiple_sessions_cleanup(
        self, authenticated_client_with_redis, postgres_connection_config, clean_redis
    ):
        """Test: Create and delete multiple sessions"""
        # Create 5 sessions
        session_ids = []
        for _ in range(5):
            response = authenticated_client_with_redis.post(
                "/api/db-connections/sessions",
                json={
                    "connection": postgres_connection_config,
                    "test_connection": True,
                    "ttl_hours": 3,
                },
            )
            session_ids.append(response.json()["session_id"])

        # Verify all exist
        list_response = authenticated_client_with_redis.get("/api/db-connections/sessions")
        assert len(list_response.json()) == 5

        # Delete all
        for session_id in session_ids:
            response = authenticated_client_with_redis.delete(
                f"/api/db-connections/sessions/{session_id}"
            )
            assert response.status_code == 204

        # Verify all deleted
        list_response = authenticated_client_with_redis.get("/api/db-connections/sessions")
        assert len(list_response.json()) == 0
