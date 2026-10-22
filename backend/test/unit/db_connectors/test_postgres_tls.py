"""
TLS de PostgreSQLAdapter (psycopg2 / libpq).

- Por defecto: sslmode=verify-full (certificado y hostname) contra el bundle del sistema.
- CA propia: sslrootcert apunta a un archivo temporal que se borra al terminar.
- Opt-out: sslmode=require (cifra, no verifica) y sin sslrootcert, porque libpq con
  require + sslrootcert verificaría la CA igualmente.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import OperationalError

from app.utils.db_adapters.exceptions import (
    DBAuthenticationError,
    DBConnectionError,
    DBTLSError,
)
from app.utils.db_adapters.postgres_adapter import PostgreSQLAdapter
from app.utils.db_adapters.tls import default_ca_bundle

CONNECT = "app.utils.db_adapters.postgres_adapter.psycopg2.connect"


def _config(**extra):
    config = {
        "host": "db.example.com",
        "port": 5432,
        "database": "app",
        "user": "u",
        "password": "p",
    }
    config.update(extra)
    return config


def _connect_kwargs(**extra) -> dict:
    with patch(CONNECT) as mock_connect:
        mock_connect.return_value = MagicMock()
        PostgreSQLAdapter(_config(**extra)).connect()
    return mock_connect.call_args.kwargs


class TestVerificacionPorDefecto:
    def test_verify_full_con_el_bundle_del_sistema(self):
        kwargs = _connect_kwargs()

        assert kwargs["sslmode"] == "verify-full"
        assert kwargs["sslrootcert"] == default_ca_bundle()

    def test_tls_verify_true_explicito_es_igual_que_el_default(self):
        assert _connect_kwargs(tls_verify=True)["sslmode"] == "verify-full"

    def test_nunca_se_usa_un_sslmode_que_caiga_a_texto_plano(self):
        permitido = {"verify-full", "require"}

        for extra in ({}, {"tls_verify": False, "confirm_hostname": "db.example.com"}):
            assert _connect_kwargs(**extra)["sslmode"] in permitido


class TestCAPropia:
    def test_sslrootcert_apunta_a_la_ca_subida(self, ca_pem):
        visto = {}

        def espiar(**kwargs):
            visto["sslmode"] = kwargs["sslmode"]
            visto["ruta"] = kwargs["sslrootcert"]
            visto["contenido"] = Path(kwargs["sslrootcert"]).read_text()
            return MagicMock()

        with patch(CONNECT, side_effect=espiar):
            PostgreSQLAdapter(_config(tls_ca_pem=ca_pem)).connect()

        assert visto["sslmode"] == "verify-full"
        assert visto["contenido"] == ca_pem
        assert visto["ruta"] != default_ca_bundle()

    def test_el_archivo_temporal_se_borra_tras_conectar(self, ca_pem):
        with patch(CONNECT) as mock_connect:
            mock_connect.return_value = MagicMock()
            PostgreSQLAdapter(_config(tls_ca_pem=ca_pem)).connect()

        assert not Path(mock_connect.call_args.kwargs["sslrootcert"]).exists()

    def test_el_archivo_temporal_se_borra_si_la_conexion_falla(self, ca_pem):
        with patch(CONNECT, side_effect=OperationalError("fallo de red")) as mock_connect:
            with pytest.raises(DBConnectionError):
                PostgreSQLAdapter(_config(tls_ca_pem=ca_pem)).connect()

        assert not Path(mock_connect.call_args.kwargs["sslrootcert"]).exists()


class TestOptOut:
    def test_require_cifra_sin_verificar(self):
        kwargs = _connect_kwargs(tls_verify=False, confirm_hostname="db.example.com")

        assert kwargs["sslmode"] == "require"
        assert "sslrootcert" not in kwargs


class TestErroresTLS:
    @pytest.mark.parametrize(
        "mensaje",
        [
            'connection to server at "db" failed: SSL error: certificate verify failed',
            "connection to server failed: server does not support SSL, but SSL was required",
            'root certificate file "/tmp/x.pem" does not exist',
        ],
    )
    def test_fallos_de_verificacion_son_dbtlserror(self, mensaje):
        with patch(CONNECT, side_effect=OperationalError(mensaje)):
            with pytest.raises(DBTLSError):
                PostgreSQLAdapter(_config()).connect()

    def test_dbtlserror_sigue_siendo_dbconnectionerror(self):
        with patch(CONNECT, side_effect=OperationalError("SSL error: certificate verify failed")):
            with pytest.raises(DBConnectionError):
                PostgreSQLAdapter(_config()).connect()

    def test_la_autenticacion_sigue_siendo_dbauthenticationerror(self):
        with patch(CONNECT, side_effect=OperationalError("password authentication failed")):
            with pytest.raises(DBAuthenticationError):
                PostgreSQLAdapter(_config()).connect()

    def test_un_fallo_de_red_no_se_confunde_con_tls(self):
        with patch(CONNECT, side_effect=OperationalError("Connection refused")):
            with pytest.raises(DBConnectionError) as excinfo:
                PostgreSQLAdapter(_config()).connect()

        assert not isinstance(excinfo.value, DBTLSError)
