"""
Tests de is_tls_error y DBTLSError.

Un fallo de verificación TLS se distingue de un fallo de red o de autenticación para que la
API pueda explicarlo (error_type="tls") en vez de devolver el texto crudo del driver.
"""

import pytest

from app.utils.db_adapters import DBTLSError
from app.utils.db_adapters.exceptions import DBConnectionError
from app.utils.db_adapters.tls import is_tls_error


@pytest.mark.parametrize(
    "mensaje",
    [
        "SSL error: certificate verify failed",
        "connection to server failed: server does not support SSL, but SSL was required",
        'root certificate file "/tmp/datamap-ca-x.pem" does not exist',
        "(2026, 'TLS/SSL error: Hostname mismatch, certificate is not valid for host')",
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate",
        "SSL Provider: [error:0A000086:SSL routines::certificate verify failed:unable to get local "
        "issuer certificate]",
        "DPY-6005: cannot connect to database. TLS handshake failed",
        "ssl handshake failure",
        "the certificate chain was issued by an authority that is not trusted",
        "self signed certificate in certificate chain",
    ],
)
def test_detecta_errores_tls(mensaje):
    assert is_tls_error(mensaje) is True


@pytest.mark.parametrize(
    "mensaje",
    [
        "could not connect to server: Connection refused",
        "connection timed out",
        "FATAL: password authentication failed for user",
        "Login failed for user 'sa'. (18456)",
        'FATAL: no pg_hba.conf entry for host "10.0.0.1", user "u", database "d", SSL encryption',
        "Unknown database 'app'",
        "SSL SYSCALL error: EOF detected",  # corte tras un handshake aceptado: no es el certificado
        "",
    ],
)
def test_no_confunde_otros_errores_con_tls(mensaje):
    assert is_tls_error(mensaje) is False


def test_dbtlserror_es_un_error_de_conexion():
    """Quien capture DBConnectionError sigue capturando los fallos TLS."""
    assert issubclass(DBTLSError, DBConnectionError)
