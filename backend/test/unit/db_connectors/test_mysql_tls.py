"""
TLS de MySQLAdapter (PyMySQL 1.1.0).

- La política TLS llega a PyMySQL como un ssl.SSLContext (la CA propia se carga desde
  memoria, sin archivos temporales).
- PyMySQL 1.1.0 continúa en TEXTO PLANO si el servidor no anuncia soporte TLS; la
  conexión del adaptador aborta antes de autenticar. Se prueba con un servidor MySQL
  falso que no ofrece TLS.
"""

import socket
import ssl
import threading
from unittest.mock import MagicMock, patch

import pymysql
import pytest
from pymysql.constants import CLIENT
from pymysql.err import OperationalError

from app.utils.db_adapters.exceptions import (
    DBAuthenticationError,
    DBConnectionError,
    DBTLSError,
)
from app.utils.db_adapters.mysql_adapter import MySQLAdapter, _TLSRequiredConnection

CONNECTION = "app.utils.db_adapters.mysql_adapter._TLSRequiredConnection"


def _config(**extra):
    config = {
        "host": "db.example.com",
        "port": 3306,
        "database": "app",
        "user": "u",
        "password": "p",
    }
    config.update(extra)
    return config


def _connect_kwargs(**extra) -> dict:
    with patch(CONNECTION) as mock_connection:
        mock_connection.return_value = MagicMock()
        MySQLAdapter(_config(**extra)).connect()
    return mock_connection.call_args.kwargs


class TestContextoSSL:
    def test_por_defecto_verifica_certificado_y_hostname(self):
        context = _connect_kwargs()["ssl"]

        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True
        assert context.get_ca_certs()  # bundle del sistema

    def test_con_ca_propia_solo_confia_en_ella(self, ca_pem):
        context = _connect_kwargs(tls_ca_pem=ca_pem)["ssl"]

        assert context.verify_mode == ssl.CERT_REQUIRED
        assert len(context.get_ca_certs()) == 1

    def test_opt_out_cifra_sin_verificar(self):
        context = _connect_kwargs(tls_verify=False, confirm_hostname="db.example.com")["ssl"]

        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_NONE
        assert context.check_hostname is False

    @pytest.mark.parametrize(
        "extra", [{}, {"tls_verify": False, "confirm_hostname": "db.example.com"}]
    )
    def test_nunca_se_desactiva_el_tls(self, extra):
        kwargs = _connect_kwargs(**extra)

        assert kwargs["ssl"]  # SSLContext: PyMySQL activa TLS cuando ssl es verdadero
        assert not kwargs.get("ssl_disabled")


class TestSinDegradarATextoPlano:
    def test_pymysql_expone_el_hook_del_que_depende_la_defensa(self):
        """Si una actualización de PyMySQL lo renombra, hay que revisar la defensa."""
        assert callable(getattr(pymysql.connections.Connection, "_request_authentication", None))

    def test_aborta_si_el_servidor_no_anuncia_tls(self):
        conexion = object.__new__(_TLSRequiredConnection)
        conexion.ssl = True
        conexion.server_capabilities = 0

        with patch.object(pymysql.connections.Connection, "_request_authentication") as base:
            with pytest.raises(OperationalError, match="does not support TLS"):
                conexion._request_authentication()

        base.assert_not_called()

    def test_continua_si_el_servidor_anuncia_tls(self):
        conexion = object.__new__(_TLSRequiredConnection)
        conexion.ssl = True
        conexion.server_capabilities = CLIENT.SSL

        with patch.object(pymysql.connections.Connection, "_request_authentication") as base:
            conexion._request_authentication()

        base.assert_called_once()

    def test_servidor_real_sin_tls_no_recibe_credenciales(self, tls_certs):
        """Un servidor sin TLS (o un MITM que lo oculte) no ve ni la autenticación."""
        recibido = {}
        servidor = socket.socket()
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(1)
        servidor.settimeout(10)
        puerto = servidor.getsockname()[1]

        def atender():
            conexion, _ = servidor.accept()
            conexion.settimeout(10)
            conexion.sendall(tls_certs.mysql_greeting(tls_certs.MYSQL_CAPABILITIES_WITHOUT_TLS))
            recibido["datos"] = conexion.recv(4096)
            conexion.close()

        hilo = threading.Thread(target=atender, daemon=True)
        hilo.start()
        try:
            adapter = MySQLAdapter(_config(host="127.0.0.1", port=puerto, timeout=5))
            with pytest.raises(DBTLSError):
                adapter.connect()
            hilo.join(timeout=10)
        finally:
            servidor.close()

        assert recibido["datos"] == b""  # el cliente cerró sin enviar nada


class TestErrores:
    @pytest.mark.parametrize(
        "mensaje",
        [
            "Can't connect to MySQL server on 'db' ([SSL: CERTIFICATE_VERIFY_FAILED] certificate "
            "verify failed: self-signed certificate)",
            "TLS/SSL error: Hostname mismatch, certificate is not valid for 'db'",
            "TLS/SSL error: the server does not support TLS",
        ],
    )
    def test_fallos_de_verificacion_son_dbtlserror(self, mensaje):
        with patch(CONNECTION, side_effect=OperationalError(2003, mensaje)):
            with pytest.raises(DBTLSError):
                MySQLAdapter(_config()).connect()

    def test_acceso_denegado_sigue_siendo_autenticacion(self):
        with patch(CONNECTION, side_effect=OperationalError(1045, "Access denied for user 'u'")):
            with pytest.raises(DBAuthenticationError):
                MySQLAdapter(_config()).connect()

    def test_un_fallo_de_red_no_se_confunde_con_tls(self):
        with patch(CONNECTION, side_effect=OperationalError(2003, "Connection refused")):
            with pytest.raises(DBConnectionError) as excinfo:
                MySQLAdapter(_config()).connect()

        assert not isinstance(excinfo.value, DBTLSError)
