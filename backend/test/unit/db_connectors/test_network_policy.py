"""
Unit Tests for the connector network policy (SSRF protection), TLS modes and the
connector router's rate limiting / error sanitization.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.utils.db_adapters import DBHostNotAllowedError
from app.utils.db_adapters.network_policy import validate_connection_host


@pytest.fixture
def production_policy(monkeypatch):
    """Política por defecto de producción: solo hosts públicos"""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("DB_CONNECTOR_ALLOW_PRIVATE_HOSTS", raising=False)
    monkeypatch.delenv("DB_CONNECTOR_ALLOWED_NETWORKS", raising=False)
    return monkeypatch


def _resolves_to(*addresses):
    infos = [(None, None, None, "", (address, 5432)) for address in addresses]
    return patch("app.utils.db_adapters.network_policy.socket.getaddrinfo", return_value=infos)


class TestNetworkPolicy:
    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "10.1.2.3",
            "172.16.0.5",
            "192.168.1.10",
            "169.254.169.254",  # metadata cloud
            "100.64.0.1",  # CGNAT
            "0.0.0.0",
            "::1",
            "fd00::1",
            "::ffff:10.0.0.1",
            "224.0.0.1",
        ],
    )
    def test_internal_addresses_blocked(self, production_policy, address):
        with _resolves_to(address), pytest.raises(DBHostNotAllowedError):
            validate_connection_host("db.example.com", 5432)

    def test_public_address_allowed(self, production_policy):
        with _resolves_to("8.8.8.8"):
            validate_connection_host("db.example.com", 5432)

    def test_any_internal_resolution_blocks(self, production_policy):
        """Un host que resuelve a una IP pública y otra privada se rechaza"""
        with _resolves_to("8.8.8.8", "10.0.0.1"), pytest.raises(DBHostNotAllowedError):
            validate_connection_host("db.example.com", 5432)

    def test_unresolvable_host_rejected(self, production_policy):
        import socket

        with (
            patch(
                "app.utils.db_adapters.network_policy.socket.getaddrinfo",
                side_effect=socket.gaierror,
            ),
            pytest.raises(DBHostNotAllowedError),
        ):
            validate_connection_host("nope.invalid", 5432)

    def test_explicit_allowed_network(self, production_policy):
        production_policy.setenv("DB_CONNECTOR_ALLOWED_NETWORKS", "10.20.0.0/16")
        with _resolves_to("10.20.3.4"):
            validate_connection_host("db.internal", 5432)
        with _resolves_to("10.21.0.1"), pytest.raises(DBHostNotAllowedError):
            validate_connection_host("other.internal", 5432)

    def test_private_hosts_flag(self, production_policy):
        production_policy.setenv("DB_CONNECTOR_ALLOW_PRIVATE_HOSTS", "true")
        with _resolves_to("127.0.0.1"):
            validate_connection_host("localhost", 5432)

    def test_development_allows_private_by_default(self, production_policy):
        production_policy.setenv("ENV", "development")
        with _resolves_to("127.0.0.1"):
            validate_connection_host("localhost", 5432)

    def test_service_blocks_before_connecting(self, production_policy):
        from app.models.db_connection import DBConnectionConfig
        from app.services.db_connection_service import DBConnectionService

        service = DBConnectionService(MagicMock(), "ZGF0YW1hcC10ZXN0LW1hc3Rlci1rZXktMzItYnl0ZXM=")
        config = DBConnectionConfig(
            dialect="postgresql", host="127.0.0.1", port=5432, database="db", user="u", password="p"
        )

        with patch("app.services.db_connection_service.PostgreSQLAdapter") as adapter:
            result = service.test_connection(config)

        adapter.assert_not_called()
        assert result.success is False
        assert result.error_type == "host_not_allowed"


class TestConnectorRouterHardening:
    def test_connect_rate_limit_per_user(self, monkeypatch):
        from app.middleware.rate_limiting import simple_limiter
        from app.routers import db_connections

        monkeypatch.setattr(db_connections, "CONNECT_RATE_LIMIT", 2)
        simple_limiter.reset("db-connect:user-rl")

        db_connections.enforce_connect_rate_limit("user-rl")
        db_connections.enforce_connect_rate_limit("user-rl")
        with pytest.raises(HTTPException) as exc_info:
            db_connections.enforce_connect_rate_limit("user-rl")

        assert exc_info.value.status_code == 429
        db_connections.enforce_connect_rate_limit("other-user")  # límite independiente
        simple_limiter.reset("db-connect:user-rl")
        simple_limiter.reset("db-connect:other-user")

    def test_driver_errors_are_not_returned(self):
        from app.routers.db_connections import raise_db_error
        from app.utils.db_adapters import DBQueryExecutionError

        error = DBQueryExecutionError('connection to server at "10.0.0.5", port 5432 failed')
        with pytest.raises(HTTPException) as exc_info:
            raise_db_error("listing schemas", error)

        assert exc_info.value.status_code == 500
        assert "10.0.0.5" not in exc_info.value.detail

    def test_host_not_allowed_maps_to_403(self):
        from app.routers.db_connections import raise_db_error

        with pytest.raises(HTTPException) as exc_info:
            raise_db_error("listing schemas", DBHostNotAllowedError("blocked"))

        assert exc_info.value.status_code == 403
