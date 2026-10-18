"""
PostgreSQL y MySQL con los drivers REALES (libpq y PyMySQL) contra un servidor TLS falso.

El servidor habla el preámbulo de cada protocolo (SSLRequest de PostgreSQL, saludo de MySQL)
y hace el handshake TLS con un certificado de prueba. Así se comprueba, sin Docker ni bases
de datos, qué certificados aceptan y rechazan de verdad los drivers:

- firmado por la CA propia      -> aceptado
- CA desconocida                -> DBTLSError
- hostname que no coincide      -> DBTLSError
- certificado caducado          -> DBTLSError
- opt-out (tls_verify=false)    -> aceptado, pero cifrado
- servidor sin TLS              -> DBTLSError, sin enviar nada en claro

La señal de aceptación es `server.received`: lo que el cliente envía DESPUÉS del handshake
(en TLS 1.3 el servidor da el handshake por completado antes de que el cliente valide).
"""

import pytest

from app.utils.db_adapters.exceptions import DBConnectionError, DBTLSError
from app.utils.db_adapters.mysql_adapter import MySQLAdapter
from app.utils.db_adapters.postgres_adapter import PostgreSQLAdapter

HOST = "127.0.0.1"


def _config(port, **extra):
    return {
        "host": HOST,
        "port": port,
        "database": "app",
        "user": "u",
        "password": "p",
        "timeout": 5,
        **extra,
    }


@pytest.fixture(params=["postgres", "mysql"])
def driver(request, tls_certs):
    """(clase del adaptador, preámbulo del protocolo) de cada motor."""
    if request.param == "postgres":
        return PostgreSQLAdapter, tls_certs.postgres_ssl_preamble()
    return MySQLAdapter, tls_certs.mysql_ssl_preamble()


class TestCertificadosConDriversReales:
    def test_acepta_un_servidor_firmado_por_la_ca_propia(self, driver, tls_certs, tls_ca):
        adapter_cls, preamble = driver
        cert, key = tls_certs.make_server_cert(*tls_ca)
        with tls_certs.FakeTLSServer(cert, key, preamble) as server:
            adapter = adapter_cls(_config(server.port, tls_ca_pem=tls_ca[0]))
            with pytest.raises(DBConnectionError) as excinfo:
                adapter.connect()  # no es una BD: falla tras el handshake, no en él
        assert server.received  # el driver llegó a hablar, ya cifrado
        assert not isinstance(excinfo.value, DBTLSError)

    def test_rechaza_una_ca_desconocida(self, driver, tls_certs, tls_ca):
        adapter_cls, preamble = driver
        cert, key = tls_certs.make_server_cert(*tls_ca)
        with tls_certs.FakeTLSServer(cert, key, preamble) as server:
            adapter = adapter_cls(_config(server.port))  # solo confía en el bundle del sistema
            with pytest.raises(DBTLSError):
                adapter.connect()
        assert server.received == b""

    def test_rechaza_un_certificado_de_otro_hostname(self, driver, tls_certs, tls_ca):
        adapter_cls, preamble = driver
        cert, key = tls_certs.make_server_cert(
            *tls_ca, dns_names=("otro.example.com",), ip_addresses=()
        )
        with tls_certs.FakeTLSServer(cert, key, preamble) as server:
            adapter = adapter_cls(_config(server.port, tls_ca_pem=tls_ca[0]))
            with pytest.raises(DBTLSError):
                adapter.connect()
        assert server.received == b""

    def test_rechaza_un_certificado_caducado(self, driver, tls_certs, tls_ca):
        adapter_cls, preamble = driver
        cert, key = tls_certs.make_server_cert(*tls_ca, expired=True)
        with tls_certs.FakeTLSServer(cert, key, preamble) as server:
            adapter = adapter_cls(_config(server.port, tls_ca_pem=tls_ca[0]))
            with pytest.raises(DBTLSError):
                adapter.connect()
        assert server.received == b""

    def test_rechaza_un_certificado_de_otra_ca(self, driver, tls_certs, tls_ca):
        adapter_cls, preamble = driver
        otra_ca = tls_certs.make_ca("Otra CA")
        cert, key = tls_certs.make_server_cert(*otra_ca)
        with tls_certs.FakeTLSServer(cert, key, preamble) as server:
            adapter = adapter_cls(_config(server.port, tls_ca_pem=tls_ca[0]))
            with pytest.raises(DBTLSError):
                adapter.connect()
        assert server.received == b""

    def test_opt_out_acepta_un_certificado_no_confiable_pero_cifra(self, driver, tls_certs, tls_ca):
        adapter_cls, preamble = driver
        cert, key = tls_certs.make_server_cert(*tls_ca)
        with tls_certs.FakeTLSServer(cert, key, preamble) as server:
            adapter = adapter_cls(_config(server.port, tls_verify=False, confirm_hostname=HOST))
            with pytest.raises(DBConnectionError) as excinfo:
                adapter.connect()
        assert server.received  # habló, y por un canal TLS
        assert not isinstance(excinfo.value, DBTLSError)

    def test_opt_out_acepta_incluso_un_hostname_ajeno(self, driver, tls_certs, tls_ca):
        """El opt-out salta toda la verificación, y es lo que queda marcado como no verificado."""
        adapter_cls, preamble = driver
        cert, key = tls_certs.make_server_cert(
            *tls_ca, dns_names=("otro.example.com",), ip_addresses=()
        )
        with tls_certs.FakeTLSServer(cert, key, preamble) as server:
            adapter = adapter_cls(_config(server.port, tls_verify=False, confirm_hostname=HOST))
            with pytest.raises(DBConnectionError):
                adapter.connect()
        assert server.received


class TestServidorSinTLS:
    def test_postgres_no_envia_nada_en_claro(self, tls_certs):
        """Si el servidor responde 'N' al SSLRequest, libpq aborta sin enviar el arranque."""
        visto = {}

        def preamble(connection):
            connection.recv(8)
            connection.sendall(b"N")
            connection.settimeout(2)
            try:
                visto["despues"] = connection.recv(4096)
            except OSError:
                visto["despues"] = b""
            return False

        cert, key = tls_certs.make_server_cert(*tls_certs.make_ca())
        with tls_certs.FakeTLSServer(cert, key, preamble) as server:
            adapter = PostgreSQLAdapter(
                _config(server.port, tls_verify=False, confirm_hostname=HOST)
            )
            with pytest.raises(DBTLSError):
                adapter.connect()
            server._thread.join(timeout=10)
        assert visto["despues"] == b""

    def test_postgres_sin_tls_tambien_falla_con_verificacion(self, tls_certs):
        cert, key = tls_certs.make_server_cert(*tls_certs.make_ca())
        with tls_certs.FakeTLSServer(
            cert, key, tls_certs.postgres_ssl_preamble(accept=False)
        ) as server:
            with pytest.raises(DBTLSError):
                PostgreSQLAdapter(_config(server.port)).connect()
