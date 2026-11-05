"""
Pinning de la IP validada por la política de red (DNS rebinding).

validate_connection_host resolvía y validaba el host, pero después el driver volvía a
resolver el nombre al conectar: un DNS con TTL 0 podía responder primero con una IP
pública y luego con una interna. Ahora la política devuelve la IP validada y los
adapters conectan a ella, manteniendo el nombre para verificar el certificado TLS.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models.db_connection import DBConnectionConfig
from app.utils.db_adapters.network_policy import validate_connection_host

PUBLIC_IP = "203.0.113.7"


@pytest.fixture
def production_policy(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("DB_CONNECTOR_ALLOW_PRIVATE_HOSTS", raising=False)
    monkeypatch.delenv("DB_CONNECTOR_ALLOWED_NETWORKS", raising=False)


def _resolves_to(*addresses):
    infos = [(None, None, None, "", (address, 5432)) for address in addresses]
    return patch("app.utils.db_adapters.network_policy.socket.getaddrinfo", return_value=infos)


def _base_config(**overrides):
    config = {
        "host": "db.example.com",
        "port": 5432,
        "database": "d",
        "user": "u",
        "password": "p",
    }
    config.update(overrides)
    return config


class TestPolicyReturnsValidatedAddress:
    def test_returns_first_validated_address(self, production_policy):
        with _resolves_to("8.8.8.8", "8.8.4.4"):
            assert validate_connection_host("db.example.com", 5432) == "8.8.8.8"

    def test_ipv4_mapped_address_is_returned_as_ipv4(self, production_policy):
        with _resolves_to("::ffff:8.8.8.8"):
            assert validate_connection_host("db.example.com", 5432) == "8.8.8.8"

    def test_no_pinning_when_policy_allows_any_host(self, monkeypatch):
        monkeypatch.setenv("DB_CONNECTOR_ALLOW_PRIVATE_HOSTS", "true")
        with patch("app.utils.db_adapters.network_policy.socket.getaddrinfo") as resolve:
            assert validate_connection_host("db.example.com", 5432) is None
        resolve.assert_not_called()


class TestServicePassesPinnedAddress:
    def _service(self):
        from app.services.db_connection_service import DBConnectionService

        return DBConnectionService(MagicMock(), b"0" * 32)

    def test_adapter_config_gets_hostaddr(self):
        config = DBConnectionConfig(dialect="postgresql", **_base_config())
        with patch(
            "app.services.db_connection_service.validate_connection_host", return_value=PUBLIC_IP
        ):
            adapter = self._service()._get_adapter(config)
        assert adapter.connection_config["hostaddr"] == PUBLIC_IP
        assert adapter.connection_config["host"] == "db.example.com"

    def test_no_hostaddr_without_pinning(self):
        config = DBConnectionConfig(dialect="postgresql", **_base_config())
        with patch(
            "app.services.db_connection_service.validate_connection_host", return_value=None
        ):
            adapter = self._service()._get_adapter(config)
        assert "hostaddr" not in adapter.connection_config


class TestPostgresPinning:
    def test_connects_to_hostaddr_and_keeps_host_for_tls(self):
        from app.utils.db_adapters.postgres_adapter import PostgreSQLAdapter

        adapter = PostgreSQLAdapter(_base_config(hostaddr=PUBLIC_IP))
        with patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect") as connect:
            adapter.connect()
        kwargs = connect.call_args.kwargs
        assert kwargs["hostaddr"] == PUBLIC_IP
        assert kwargs["host"] == "db.example.com"
        assert kwargs["sslmode"] == "verify-full"

    def test_without_hostaddr_nothing_changes(self):
        from app.utils.db_adapters.postgres_adapter import PostgreSQLAdapter

        adapter = PostgreSQLAdapter(_base_config())
        with patch("app.utils.db_adapters.postgres_adapter.psycopg2.connect") as connect:
            adapter.connect()
        assert "hostaddr" not in connect.call_args.kwargs


class TestMySQLPinning:
    def test_socket_goes_to_hostaddr_and_host_is_kept_for_tls(self):
        from app.utils.db_adapters.mysql_adapter import _TLSRequiredConnection

        sock = MagicMock()
        with (
            patch(
                "app.utils.db_adapters.mysql_adapter.socket.create_connection", return_value=sock
            ) as create,
            patch("pymysql.connections.Connection.connect") as parent_connect,
        ):
            conn = _TLSRequiredConnection(
                host="db.example.com", port=3306, user="u", password="p", hostaddr=PUBLIC_IP
            )

        create.assert_called_once_with((PUBLIC_IP, 3306), conn.connect_timeout)
        parent_connect.assert_called_once_with(sock)
        # PyMySQL usa self.host como server_hostname al envolver el socket con TLS
        assert conn.host == "db.example.com"

    def test_without_hostaddr_pymysql_resolves_as_before(self):
        from app.utils.db_adapters.mysql_adapter import _TLSRequiredConnection

        with (
            patch("app.utils.db_adapters.mysql_adapter.socket.create_connection") as create,
            patch("pymysql.connections.Connection.connect") as parent_connect,
        ):
            _TLSRequiredConnection(host="db.example.com", port=3306, user="u", password="p")

        create.assert_not_called()
        parent_connect.assert_called_once_with(None)

    def test_adapter_passes_hostaddr(self):
        from app.utils.db_adapters.mysql_adapter import MySQLAdapter

        adapter = MySQLAdapter(_base_config(port=3306, hostaddr=PUBLIC_IP))
        with patch("app.utils.db_adapters.mysql_adapter._TLSRequiredConnection") as connection:
            adapter.connect()
        assert connection.call_args.kwargs["hostaddr"] == PUBLIC_IP
        assert connection.call_args.kwargs["host"] == "db.example.com"


class TestSQLServerPinning:
    def _connection_string(self, **overrides) -> str:
        from app.utils.db_adapters.sqlserver_adapter import SQLServerAdapter

        adapter = SQLServerAdapter(_base_config(port=1433, **overrides))
        with patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect") as connect:
            connect.return_value = MagicMock()
            adapter.connect()
        return connect.call_args[0][0]

    def test_server_is_ip_and_certificate_checked_against_name(self):
        connection_string = self._connection_string(hostaddr=PUBLIC_IP)
        assert f"SERVER={PUBLIC_IP},1433;" in connection_string
        assert "HostNameInCertificate=db.example.com;" in connection_string

    def test_without_hostaddr_uses_name(self):
        connection_string = self._connection_string()
        assert "SERVER=db.example.com,1433;" in connection_string
        assert "HostNameInCertificate" not in connection_string

    def test_ipv6_is_not_pinned(self):
        connection_string = self._connection_string(hostaddr="2001:db8::7")
        assert "SERVER=db.example.com,1433;" in connection_string
