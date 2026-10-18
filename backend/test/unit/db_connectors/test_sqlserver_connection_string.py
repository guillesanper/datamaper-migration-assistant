"""
Tests de la cadena de conexión ODBC de SQLServerAdapter y de la validación del host.

La cadena ODBC separa atributos con ';'. Si host, usuario o contraseña se interpolan
sin escapar, un valor como "x;Encrypt=no" añade o sobrescribe atributos del driver
(por ejemplo los que fijan la política TLS).
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models.db_connection import DBConnectionConfig
from app.utils.db_adapters.exceptions import DBValidationError
from app.utils.db_adapters.sqlserver_adapter import SQLServerAdapter
from app.utils.db_adapters.validators import validate_connection_config, validate_host


def _config(**overrides):
    config = {
        "host": "db.example.com",
        "port": 1433,
        "database": "testdb",
        "user": "testuser",
        "password": "testpass",
    }
    config.update(overrides)
    return config


def _connection_string(**overrides) -> str:
    adapter = SQLServerAdapter(_config(**overrides))
    with patch("app.utils.db_adapters.sqlserver_adapter.pyodbc.connect") as mock_connect:
        mock_connect.return_value = MagicMock()
        adapter.connect()
    return mock_connect.call_args[0][0]


def _attributes(connection_string: str) -> list:
    """Nombres de atributo de primer nivel, respetando los valores entre llaves."""
    names, depth, current = [], 0, ""
    for char in connection_string:
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(depth - 1, 0)
        if char == ";" and depth == 0:
            if current:
                names.append(current.split("=", 1)[0].strip().lower())
            current = ""
        else:
            current += char
    if current:
        names.append(current.split("=", 1)[0].strip().lower())
    return names


class TestValoresEscapados:
    """usuario y contraseña con caracteres especiales no inyectan atributos."""

    def test_valores_simples_no_cambian(self):
        conn_str = _connection_string()

        assert "UID=testuser;" in conn_str
        assert "PWD=testpass;" in conn_str

    def test_password_con_punto_y_coma_no_inyecta_atributos(self):
        conn_str = _connection_string(password="x;Encrypt=no")

        assert "PWD={x;Encrypt=no};" in conn_str
        assert _attributes(conn_str).count("encrypt") == 0

    def test_usuario_con_punto_y_coma_no_inyecta_atributos(self):
        conn_str = _connection_string(user="sa;TrustServerCertificate=yes")

        assert "UID={sa;TrustServerCertificate=yes};" in conn_str
        assert _attributes(conn_str).count("trustservercertificate") == 1

    def test_llave_de_cierre_se_duplica(self):
        conn_str = _connection_string(password="a}b;Encrypt=no")

        assert "PWD={a}}b;Encrypt=no};" in conn_str

    def test_password_con_igual_y_espacios_va_entre_llaves(self):
        conn_str = _connection_string(password=" p=ss ")

        assert "PWD={ p=ss };" in conn_str


class TestValidacionDeHost:
    """El host se interpola en SERVER=... y en el DSN: solo hostnames o IPs."""

    @pytest.mark.parametrize(
        "host",
        [
            "localhost",
            "db.example.com",
            "postgres-test",
            "db_1.internal",
            "10.0.0.5",
            "::1",
            "2001:db8::10",
            "DB.Example.COM",
            "db.example.com.",
        ],
    )
    def test_hosts_validos(self, host):
        assert validate_host(host) == host

    @pytest.mark.parametrize(
        "host",
        [
            "x;Encrypt=no",
            "db{evil}",
            "db host",
            "db'host",
            'db"host',
            "db,1433",
            "db=1",
            "-leading-dash.com",
            "a" * 64 + ".com",
            "a" * 254,
            "",
            "   ",
            "(DESCRIPTION=x)",
        ],
    )
    def test_hosts_invalidos(self, host):
        with pytest.raises(DBValidationError):
            validate_host(host)

    def test_validate_connection_config_rechaza_host_con_punto_y_coma(self):
        with pytest.raises(DBValidationError):
            validate_connection_config(_config(host="x;Encrypt=no"))

    def test_el_adaptador_rechaza_host_con_punto_y_coma_al_construirse(self):
        with pytest.raises(DBValidationError):
            SQLServerAdapter(_config(host="x;Encrypt=no"))

    def test_la_api_rechaza_host_con_punto_y_coma(self):
        with pytest.raises(ValueError):
            DBConnectionConfig(
                dialect="sqlserver",
                host="x;Encrypt=no",
                port=1433,
                database="testdb",
                user="u",
                password="p",
            )
