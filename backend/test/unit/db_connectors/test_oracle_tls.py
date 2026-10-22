"""
TLS de OracleAdapter (python-oracledb en modo thin).

- Siempre TCPS; por defecto con un SSLContext que exige certificado y hostname.
- CA propia: se carga en el SSLContext desde memoria.
- Opt-out: TCPS con CERT_NONE y sin comprobar el DN (cifra, no verifica).

Además de comprobar los parámetros de connect() con un mock, hay pruebas con oracledb
REAL contra un servidor TLS falso: el handshake ocurre antes del protocolo Oracle, así que
se observa si el driver acepta o rechaza el certificado sin necesitar una base de datos.
"""

import ssl
from unittest.mock import MagicMock, patch

import pytest

from app.utils.db_adapters.exceptions import DBConnectionError, DBTLSError
from app.utils.db_adapters.oracle_adapter import OracleAdapter

CONNECT = "app.utils.db_adapters.oracle_adapter.oracledb.connect"


def _config(**extra):
    config = {
        "host": "db.example.com",
        "port": 2484,
        "database": "ORCL",
        "user": "u",
        "password": "p",
        "timeout": 7,
    }
    config.update(extra)
    return config


def _connect_kwargs(**extra) -> dict:
    with patch(CONNECT) as mock_connect:
        mock_connect.return_value = MagicMock()
        OracleAdapter(_config(**extra)).connect()
    return mock_connect.call_args.kwargs


class TestParametrosDeConexion:
    def test_siempre_tcps(self):
        assert _connect_kwargs()["protocol"] == "tcps"
        assert (
            _connect_kwargs(tls_verify=False, confirm_hostname="db.example.com")["protocol"]
            == "tcps"
        )

    def test_por_defecto_verifica_certificado_y_hostname(self):
        kwargs = _connect_kwargs()

        assert kwargs["ssl_server_dn_match"] is True
        assert isinstance(kwargs["ssl_context"], ssl.SSLContext)
        assert kwargs["ssl_context"].verify_mode == ssl.CERT_REQUIRED
        assert kwargs["ssl_context"].check_hostname is True

    def test_con_ca_propia_solo_confia_en_ella(self, ca_pem):
        context = _connect_kwargs(tls_ca_pem=ca_pem)["ssl_context"]

        assert context.verify_mode == ssl.CERT_REQUIRED
        assert len(context.get_ca_certs()) == 1

    def test_opt_out_cifra_sin_verificar(self):
        kwargs = _connect_kwargs(tls_verify=False, confirm_hostname="db.example.com")

        assert kwargs["ssl_server_dn_match"] is False
        assert kwargs["ssl_context"].verify_mode == ssl.CERT_NONE
        assert kwargs["ssl_context"].check_hostname is False

    def test_host_y_puerto_van_como_parametros_no_en_un_descriptor(self):
        kwargs = _connect_kwargs()

        assert kwargs["host"] == "db.example.com"
        assert kwargs["port"] == 2484
        assert "dsn" not in kwargs

    def test_el_timeout_de_la_conexion_se_respeta(self):
        assert _connect_kwargs()["tcp_connect_timeout"] == 7

    def test_no_se_pasa_encoding(self):
        """oracledb reciente lo rechaza con TypeError; el modo thin ya usa UTF-8."""
        assert "encoding" not in _connect_kwargs()


class TestIdentificadorDeServicio:
    """service_name tiene prioridad sobre sid; sin ninguno se usa database."""

    def test_service_name(self):
        kwargs = _connect_kwargs(service_name="SALES")

        assert kwargs["service_name"] == "SALES"
        assert "sid" not in kwargs

    def test_sid(self):
        kwargs = _connect_kwargs(sid="XE")

        assert kwargs["sid"] == "XE"
        assert "service_name" not in kwargs

    def test_service_name_gana_sobre_sid(self):
        kwargs = _connect_kwargs(service_name="SALES", sid="XE")

        assert kwargs["service_name"] == "SALES"
        assert "sid" not in kwargs

    def test_sin_ninguno_usa_el_nombre_de_la_base_de_datos(self):
        assert _connect_kwargs()["service_name"] == "ORCL"


class TestErroresTLS:
    @staticmethod
    def _error(message):
        import oracledb

        class _Origen:
            code = 0
            full_code = "DPY-6005"

        _Origen.message = message
        return oracledb.OperationalError(_Origen())

    @pytest.mark.parametrize(
        "mensaje",
        [
            "DPY-6005: cannot connect to database. [SSL: CERTIFICATE_VERIFY_FAILED] certificate "
            "verify failed: self-signed certificate (_ssl.c:1006)",
            "DPY-6005: cannot connect to database. TLS handshake failed",
        ],
    )
    def test_fallos_de_verificacion_son_dbtlserror(self, mensaje):
        with patch(CONNECT, side_effect=self._error(mensaje)):
            with pytest.raises(DBTLSError):
                OracleAdapter(_config()).connect()

    def test_un_fallo_de_red_no_se_confunde_con_tls(self):
        with patch(
            CONNECT, side_effect=self._error("DPY-6005: cannot connect: Connection refused")
        ):
            with pytest.raises(DBConnectionError) as excinfo:
                OracleAdapter(_config()).connect()

        assert not isinstance(excinfo.value, DBTLSError)


class TestHandshakeReal:
    """
    oracledb real contra un servidor TLS falso: ¿acepta o rechaza el certificado?

    La señal fiable es `server.received`: si el driver aceptó el certificado envía su
    paquete CONNECT cifrado; si lo rechazó no envía nada. (`handshake_ok` del servidor no
    sirve para esto: en TLS 1.3 el servidor lo da por completado antes de que el cliente
    valide el certificado.)

    Se conecta a "localhost" y no a 127.0.0.1: la comprobación de hostname de oracledb
    (ssl_server_dn_match) solo entiende nombres DNS/CN, no IP SAN.
    """

    @staticmethod
    def _adapter(server, **extra):
        return OracleAdapter(_config(host="localhost", port=server.port, timeout=5, **extra))

    def test_acepta_un_servidor_firmado_por_la_ca_propia(self, tls_certs, tls_ca):
        cert, key = tls_certs.make_server_cert(*tls_ca)
        with tls_certs.FakeTLSServer(cert, key) as server:
            adapter = self._adapter(server, tls_ca_pem=tls_ca[0])
            with pytest.raises(DBConnectionError) as excinfo:
                adapter.connect()  # no es un Oracle: falla después del handshake, no en él
        assert server.received  # el driver llegó a enviar su paquete CONNECT cifrado
        assert not isinstance(excinfo.value, DBTLSError)

    def test_rechaza_una_ca_desconocida(self, tls_certs, tls_ca):
        cert, key = tls_certs.make_server_cert(*tls_ca)
        with tls_certs.FakeTLSServer(cert, key) as server:
            adapter = self._adapter(server)  # sin CA propia: solo el bundle del sistema
            with pytest.raises(DBTLSError):
                adapter.connect()
        assert server.received == b""

    def test_rechaza_un_certificado_de_otro_hostname(self, tls_certs, tls_ca):
        cert, key = tls_certs.make_server_cert(
            *tls_ca, dns_names=("otro.example.com",), ip_addresses=()
        )
        with tls_certs.FakeTLSServer(cert, key) as server:
            adapter = self._adapter(server, tls_ca_pem=tls_ca[0])
            with pytest.raises(DBTLSError):
                adapter.connect()
        assert server.received == b""

    def test_rechaza_un_certificado_caducado(self, tls_certs, tls_ca):
        cert, key = tls_certs.make_server_cert(*tls_ca, expired=True)
        with tls_certs.FakeTLSServer(cert, key) as server:
            adapter = self._adapter(server, tls_ca_pem=tls_ca[0])
            with pytest.raises(DBTLSError):
                adapter.connect()
        assert server.received == b""

    def test_conectar_por_ip_con_verificacion_se_rechaza(self, tls_certs, tls_ca):
        """Limitación de oracledb: no valida IP SAN. Se rechaza, no se acepta sin comprobar."""
        cert, key = tls_certs.make_server_cert(*tls_ca)  # el certificado SÍ lleva la IP
        with tls_certs.FakeTLSServer(cert, key) as server:
            adapter = OracleAdapter(
                _config(host="127.0.0.1", port=server.port, timeout=5, tls_ca_pem=tls_ca[0])
            )
            with pytest.raises(DBTLSError):
                adapter.connect()
        assert server.received == b""

    def test_opt_out_acepta_un_certificado_no_confiable_pero_cifra(self, tls_certs, tls_ca):
        cert, key = tls_certs.make_server_cert(*tls_ca)
        with tls_certs.FakeTLSServer(cert, key) as server:
            adapter = self._adapter(server, tls_verify=False, confirm_hostname="localhost")
            with pytest.raises(DBConnectionError) as excinfo:
                adapter.connect()
        assert server.received  # llegó a hablar Oracle, y por un canal TLS
        assert not isinstance(excinfo.value, DBTLSError)
