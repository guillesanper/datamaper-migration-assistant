"""
TLS de SQLServerAdapter (pyodbc + ODBC Driver 18).

- Por defecto: Encrypt=yes y TrustServerCertificate=no (certificado y hostname).
- Opt-out: Encrypt=yes y TrustServerCertificate=yes (cifra, no verifica).
- ODBC Driver 18 solo confía en el almacén del sistema: una CA propia no se puede aplicar
  por conexión, así que el adaptador la rechaza en vez de ignorarla en silencio.
"""

from unittest.mock import MagicMock, patch

import pyodbc
import pytest

from app.utils.db_adapters.exceptions import (
    DBAuthenticationError,
    DBConnectionError,
    DBTimeoutError,
    DBTLSError,
    DBValidationError,
)
from app.utils.db_adapters.sqlserver_adapter import SQLServerAdapter

CONNECT = "app.utils.db_adapters.sqlserver_adapter.pyodbc.connect"

# Mensaje real del driver: el fallo de certificado llega seguido de un "Login timeout expired"
MENSAJE_CERTIFICADO = (
    "('08001', '[08001] [Microsoft][ODBC Driver 18 for SQL Server]SSL Provider: "
    "[error:0A000086:SSL routines::certificate verify failed:self-signed certificate] (-1) "
    "(SQLDriverConnect); [08001] [Microsoft][ODBC Driver 18 for SQL Server]Client unable to "
    "establish connection (-1); [HYT00] [Microsoft][ODBC Driver 18 for SQL Server]Login timeout "
    "expired (0)')"
)


def _config(**extra):
    config = {
        "host": "db.example.com",
        "port": 1433,
        "database": "app",
        "user": "u",
        "password": "p",
    }
    config.update(extra)
    return config


def _connection_string(**extra) -> str:
    with patch(CONNECT) as mock_connect:
        mock_connect.return_value = MagicMock()
        SQLServerAdapter(_config(**extra)).connect()
    return mock_connect.call_args[0][0]


class TestVerificacionPorDefecto:
    def test_cifra_y_verifica_el_certificado(self):
        conn_str = _connection_string()

        assert "Encrypt=yes;" in conn_str
        assert "TrustServerCertificate=no;" in conn_str

    def test_los_atributos_tls_aparecen_una_sola_vez(self):
        conn_str = _connection_string()

        assert conn_str.lower().count("encrypt=") == 1
        assert conn_str.lower().count("trustservercertificate=") == 1

    def test_nunca_se_confia_en_el_certificado_por_defecto(self):
        assert "TrustServerCertificate=yes" not in _connection_string()
        assert "TrustServerCertificate=yes" not in _connection_string(tls_verify=True)

    def test_una_password_maliciosa_no_cambia_la_politica(self):
        conn_str = _connection_string(password="x;TrustServerCertificate=yes;Encrypt=no")

        assert "PWD={x;TrustServerCertificate=yes;Encrypt=no};" in conn_str
        assert conn_str.endswith("Connection Timeout=30;")
        assert "Encrypt=yes;TrustServerCertificate=no;" in conn_str


class TestOptOut:
    def test_cifra_sin_verificar(self):
        conn_str = _connection_string(tls_verify=False, confirm_hostname="db.example.com")

        assert "Encrypt=yes;" in conn_str
        assert "TrustServerCertificate=yes;" in conn_str

    def test_el_opt_out_sigue_cifrando(self):
        conn_str = _connection_string(tls_verify=False, confirm_hostname="db.example.com")

        assert "Encrypt=no" not in conn_str
        assert "Encrypt=optional" not in conn_str


class TestCAPropia:
    def test_el_adaptador_rechaza_una_ca_propia(self, ca_pem):
        with pytest.raises(DBValidationError, match="SQL Server"):
            SQLServerAdapter(_config(tls_ca_pem=ca_pem))


class TestErroresTLS:
    def test_fallo_de_certificado_no_se_confunde_con_timeout(self):
        with patch(CONNECT, side_effect=pyodbc.Error("08001", MENSAJE_CERTIFICADO)):
            with pytest.raises(DBTLSError):
                SQLServerAdapter(_config()).connect()

    def test_un_timeout_real_sigue_siendo_dbtimeouterror(self):
        with patch(CONNECT, side_effect=pyodbc.Error("HYT00", "Login timeout expired")):
            with pytest.raises(DBTimeoutError):
                SQLServerAdapter(_config()).connect()

    def test_login_fallido_sigue_siendo_autenticacion(self):
        with patch(CONNECT, side_effect=pyodbc.Error("28000", "Login failed for user 'u' (18456)")):
            with pytest.raises(DBAuthenticationError):
                SQLServerAdapter(_config()).connect()

    def test_otros_fallos_siguen_siendo_dbconnectionerror(self):
        with patch(CONNECT, side_effect=pyodbc.Error("08001", "Named Pipes Provider: no server")):
            with pytest.raises(DBConnectionError) as excinfo:
                SQLServerAdapter(_config()).connect()

        assert not isinstance(excinfo.value, (DBTLSError, DBTimeoutError))
