"""
Integration Tests for GET /api/db-connections/sessions/{session_id}/connector-tables

Tests the endpoint that reads tables from an external DB, computes SHA-256 hashes
per table/column, and returns the structure WITHOUT saving it locally.

No external DB or real Redis is required — all adapter/service calls are mocked.
Auth uses the standard authenticated_client fixture (real login flow with FakeRedis).
"""

import hashlib
from unittest.mock import MagicMock

import pytest

from app.models.db_metadata import (
    ColumnMetadata,
    DataType,
    SchemaMetadata,
    TableMetadata,
    TableType,
)
from app.routers.db_connections import get_db_connection_service, get_user_session
from main import app

SESSION_ID = "test-connector-session-uuid"
ENDPOINT = f"/api/db-connections/sessions/{SESSION_ID}/connector-tables"


# =============================================================================
# HELPERS
# =============================================================================


def _make_column(name: str, pos: int, is_pk: bool = False) -> ColumnMetadata:
    return ColumnMetadata(
        name=name,
        data_type=DataType.STRING,
        native_type="VARCHAR",
        is_nullable=not is_pk,
        is_primary_key=is_pk,
        is_auto_increment=is_pk,
        ordinal_position=pos,
    )


def _make_table(name: str, schema: str, columns: list) -> TableMetadata:
    return TableMetadata(name=name, schema=schema, table_type=TableType.BASE_TABLE, columns=columns)


def _make_schema(name: str, tables: list) -> SchemaMetadata:
    return SchemaMetadata(name=name, tables=tables)


def _make_adapter(schemas_map: dict, get_schemas_side_effect=None) -> MagicMock:
    """
    Build a context-manager-compatible adapter mock.

    schemas_map: {schema_name: SchemaMetadata | Exception}
      - If value is an Exception instance, get_full_schema_metadata raises it.
      - If value is None, get_schemas returns empty list.
    get_schemas_side_effect: if provided, replaces the default get_schemas behaviour.
    """
    adapter = MagicMock()
    adapter.__enter__ = MagicMock(return_value=adapter)
    adapter.__exit__ = MagicMock(return_value=False)

    if get_schemas_side_effect is not None:
        adapter.get_schemas.side_effect = get_schemas_side_effect
    else:
        adapter.get_schemas.return_value = list(schemas_map.keys())

    def _get_full_schema_metadata(schema):
        result = schemas_map.get(schema)
        if isinstance(result, Exception):
            raise result
        return result

    adapter.get_full_schema_metadata.side_effect = _get_full_schema_metadata
    return adapter


def _make_service(adapter: MagicMock) -> MagicMock:
    service = MagicMock()
    service.get_decrypted_config.return_value = MagicMock()
    service._get_adapter.return_value = adapter
    return service


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.user_id = "test-user-id"
    session.session_id = SESSION_ID
    return session


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def two_schema_adapter() -> MagicMock:
    """Adapter with 2 schemas, 1 table each, 2 columns each."""
    users_table = _make_table(
        "users",
        "public",
        [_make_column("id", 1, is_pk=True), _make_column("email", 2)],
    )
    invoices_table = _make_table(
        "invoices",
        "sales",
        [_make_column("invoice_id", 1, is_pk=True), _make_column("amount", 2)],
    )
    return _make_adapter(
        {
            "public": _make_schema("public", [users_table]),
            "sales": _make_schema("sales", [invoices_table]),
        }
    )


@pytest.fixture
def single_schema_adapter() -> MagicMock:
    """Adapter with a single 'public' schema for schema-filter tests."""
    users_table = _make_table(
        "users",
        "public",
        [_make_column("id", 1, is_pk=True), _make_column("username", 2)],
    )
    return _make_adapter({"public": _make_schema("public", [users_table])})


@pytest.fixture
def with_session_and_service(authenticated_client, two_schema_adapter):
    """authenticated_client + overrides for get_user_session and get_db_connection_service."""
    mock_service = _make_service(two_schema_adapter)

    app.dependency_overrides[get_user_session] = lambda: _mock_session()
    app.dependency_overrides[get_db_connection_service] = lambda: mock_service

    yield authenticated_client, mock_service, two_schema_adapter

    app.dependency_overrides.pop(get_user_session, None)
    app.dependency_overrides.pop(get_db_connection_service, None)


# =============================================================================
# HAPPY PATH
# =============================================================================


class TestGetConnectorTablesHappyPath:
    @pytest.mark.integration
    def test_returns_200_with_session_id(self, with_session_and_service):
        client, _, _ = with_session_and_service
        response = client.get(ENDPOINT)
        assert response.status_code == 200
        assert response.json()["session_id"] == SESSION_ID

    @pytest.mark.integration
    def test_returns_tables_from_all_schemas_when_no_filter(self, with_session_and_service):
        client, _, adapter = with_session_and_service
        response = client.get(ENDPOINT)
        data = response.json()

        assert len(data["tables"]) == 2
        table_names = {t["name"] for t in data["tables"]}
        assert table_names == {"users", "invoices"}
        adapter.get_schemas.assert_called_once()

    @pytest.mark.integration
    def test_schema_filter_skips_get_schemas(self, authenticated_client, single_schema_adapter):
        mock_service = _make_service(single_schema_adapter)
        app.dependency_overrides[get_user_session] = lambda: _mock_session()
        app.dependency_overrides[get_db_connection_service] = lambda: mock_service
        try:
            response = authenticated_client.get(f"{ENDPOINT}?schema=public")
            assert response.status_code == 200
            data = response.json()
            assert len(data["tables"]) == 1
            assert data["tables"][0]["schema"] == "public"
            single_schema_adapter.get_schemas.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_table_hashes_are_sha256_of_table_name(self, with_session_and_service):
        client, _, _ = with_session_and_service
        response = client.get(ENDPOINT)
        for table in response.json()["tables"]:
            expected = hashlib.sha256(table["name"].encode()).hexdigest()
            assert table["table_hash"] == expected

    @pytest.mark.integration
    def test_column_hashes_are_sha256_of_column_name(self, with_session_and_service):
        client, _, _ = with_session_and_service
        response = client.get(ENDPOINT)
        for table in response.json()["tables"]:
            for col in table["columns"]:
                expected = hashlib.sha256(col["name"].encode()).hexdigest()
                assert col["column_hash"] == expected

    @pytest.mark.integration
    def test_response_columns_have_all_required_fields(self, with_session_and_service):
        client, _, _ = with_session_and_service
        response = client.get(ENDPOINT)
        required_fields = {
            "name",
            "column_hash",
            "data_type",
            "native_type",
            "is_nullable",
            "is_primary_key",
            "is_auto_increment",
            "ordinal_position",
        }
        for table in response.json()["tables"]:
            for col in table["columns"]:
                assert required_fields.issubset(col.keys()), f"Missing fields in column {col}"

    @pytest.mark.integration
    def test_response_tables_have_schema_and_table_type(self, with_session_and_service):
        client, _, _ = with_session_and_service
        response = client.get(ENDPOINT)
        for table in response.json()["tables"]:
            assert "schema" in table
            assert "table_type" in table
            assert table["table_type"]  # non-empty


# =============================================================================
# CORNER CASES
# =============================================================================


class TestGetConnectorTablesCornerCases:
    @pytest.mark.integration
    def test_unauthenticated_returns_401(self, client):
        """Without auth, CurrentUser() dependency should reject with 401."""
        # Still need to mock the service so we don't attempt a real Redis connection.
        app.dependency_overrides[get_db_connection_service] = lambda: MagicMock()
        try:
            response = client.get(ENDPOINT)
            assert response.status_code == 401
        finally:
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_session_not_found_returns_404(self, authenticated_client):
        from fastapi import HTTPException

        def raise_404():
            raise HTTPException(status_code=404, detail=f"Session not found: {SESSION_ID}")

        app.dependency_overrides[get_user_session] = raise_404
        app.dependency_overrides[get_db_connection_service] = lambda: MagicMock()
        try:
            response = authenticated_client.get(ENDPOINT)
            assert response.status_code == 404
            assert SESSION_ID in response.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_session_expired_returns_410(self, authenticated_client):
        from fastapi import HTTPException

        def raise_410():
            raise HTTPException(status_code=410, detail=f"Session expired: {SESSION_ID}")

        app.dependency_overrides[get_user_session] = raise_410
        app.dependency_overrides[get_db_connection_service] = lambda: MagicMock()
        try:
            response = authenticated_client.get(ENDPOINT)
            assert response.status_code == 410
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_failing_schema_is_skipped_others_still_returned(self, authenticated_client):
        """If one schema raises during introspection, the rest still come through (no 500)."""
        good_table = _make_table("products", "inventory", [_make_column("sku", 1)])
        adapter = _make_adapter(
            {
                "broken_schema": RuntimeError("introspection failed"),
                "inventory": _make_schema("inventory", [good_table]),
            }
        )
        mock_service = _make_service(adapter)
        app.dependency_overrides[get_user_session] = lambda: _mock_session()
        app.dependency_overrides[get_db_connection_service] = lambda: mock_service
        try:
            response = authenticated_client.get(ENDPOINT)
            assert response.status_code == 200
            data = response.json()
            assert len(data["tables"]) == 1
            assert data["tables"][0]["name"] == "products"
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_all_schemas_fail_returns_empty_tables(self, authenticated_client):
        adapter = _make_adapter(
            {
                "schema_a": RuntimeError("fail"),
                "schema_b": RuntimeError("fail"),
            }
        )
        mock_service = _make_service(adapter)
        app.dependency_overrides[get_user_session] = lambda: _mock_session()
        app.dependency_overrides[get_db_connection_service] = lambda: mock_service
        try:
            response = authenticated_client.get(ENDPOINT)
            assert response.status_code == 200
            assert response.json()["tables"] == []
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_empty_database_no_schemas_returns_empty_tables(self, authenticated_client):
        adapter = _make_adapter({})  # get_schemas returns []
        mock_service = _make_service(adapter)
        app.dependency_overrides[get_user_session] = lambda: _mock_session()
        app.dependency_overrides[get_db_connection_service] = lambda: mock_service
        try:
            response = authenticated_client.get(ENDPOINT)
            assert response.status_code == 200
            assert response.json()["tables"] == []
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_adapter_connection_error_returns_500(self, authenticated_client):
        """If the adapter raises on __enter__ (connect), expect HTTP 500."""
        adapter = MagicMock()
        adapter.__enter__ = MagicMock(side_effect=RuntimeError("connection refused"))
        adapter.__exit__ = MagicMock(return_value=False)
        mock_service = _make_service(adapter)
        app.dependency_overrides[get_user_session] = lambda: _mock_session()
        app.dependency_overrides[get_db_connection_service] = lambda: mock_service
        try:
            response = authenticated_client.get(ENDPOINT)
            assert response.status_code == 500
            assert "connector" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_schema_with_no_tables_returns_empty_list(self, authenticated_client):
        adapter = _make_adapter({"public": _make_schema("public", [])})
        mock_service = _make_service(adapter)
        app.dependency_overrides[get_user_session] = lambda: _mock_session()
        app.dependency_overrides[get_db_connection_service] = lambda: mock_service
        try:
            response = authenticated_client.get(ENDPOINT)
            assert response.status_code == 200
            assert response.json()["tables"] == []
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)


# =============================================================================
# SHA-256 CORRECTNESS
# =============================================================================


class TestGetConnectorTablesSHA256Correctness:
    @pytest.mark.integration
    def test_table_hash_matches_known_value(self, authenticated_client):
        """Verify SHA-256 of 'users' matches the Python hashlib output."""
        table = _make_table("users", "public", [_make_column("id", 1)])
        adapter = _make_adapter({"public": _make_schema("public", [table])})
        mock_service = _make_service(adapter)
        app.dependency_overrides[get_user_session] = lambda: _mock_session()
        app.dependency_overrides[get_db_connection_service] = lambda: mock_service
        try:
            response = authenticated_client.get(ENDPOINT)
            assert response.status_code == 200
            result_table = response.json()["tables"][0]
            expected = hashlib.sha256(b"users").hexdigest()
            assert result_table["table_hash"] == expected
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_column_hash_matches_known_value(self, authenticated_client):
        """Verify SHA-256 of 'email' matches the Python hashlib output."""
        table = _make_table("orders", "public", [_make_column("email", 1)])
        adapter = _make_adapter({"public": _make_schema("public", [table])})
        mock_service = _make_service(adapter)
        app.dependency_overrides[get_user_session] = lambda: _mock_session()
        app.dependency_overrides[get_db_connection_service] = lambda: mock_service
        try:
            response = authenticated_client.get(ENDPOINT)
            assert response.status_code == 200
            col = response.json()["tables"][0]["columns"][0]
            expected = hashlib.sha256(b"email").hexdigest()
            assert col["column_hash"] == expected
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_distinct_names_produce_distinct_hashes(self, authenticated_client):
        """Different table and column names must never collide in their hashes."""
        t1 = _make_table("alpha", "public", [_make_column("col_a", 1)])
        t2 = _make_table("beta", "public", [_make_column("col_b", 1)])
        adapter = _make_adapter({"public": _make_schema("public", [t1, t2])})
        mock_service = _make_service(adapter)
        app.dependency_overrides[get_user_session] = lambda: _mock_session()
        app.dependency_overrides[get_db_connection_service] = lambda: mock_service
        try:
            response = authenticated_client.get(ENDPOINT)
            assert response.status_code == 200
            tables = response.json()["tables"]
            table_hashes = [t["table_hash"] for t in tables]
            assert len(set(table_hashes)) == len(table_hashes), "Table hashes must be unique"

            col_hashes = [col["column_hash"] for t in tables for col in t["columns"]]
            assert len(set(col_hashes)) == len(col_hashes), "Column hashes must be unique"
        finally:
            app.dependency_overrides.pop(get_user_session, None)
            app.dependency_overrides.pop(get_db_connection_service, None)

    @pytest.mark.integration
    def test_hash_is_hex_string_of_64_chars(self, with_session_and_service):
        """SHA-256 digest must always be a 64-character hex string."""
        client, _, _ = with_session_and_service
        response = client.get(ENDPOINT)
        for table in response.json()["tables"]:
            assert len(table["table_hash"]) == 64
            int(table["table_hash"], 16)  # must be valid hex
            for col in table["columns"]:
                assert len(col["column_hash"]) == 64
                int(col["column_hash"], 16)


# =============================================================================
# RUN DIRECTLY
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
