"""
Generación de certificados de prueba en tiempo de ejecución.

Los certificados y claves NO se commitean (los hooks detect-private-key y detect-secrets
del pre-commit lo rechazarían, y no deben existir claves privadas en el repositorio):
se crean al vuelo con `cryptography` para cada test.
"""

import datetime
import ipaddress
import os
import socket
import ssl
import struct
import tempfile
import threading
from typing import Optional, Sequence, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def make_ca(common_name: str = "Datamap Test CA") -> Tuple[str, str]:
    """
    Crea una CA autofirmada.

    Returns:
        (certificado PEM, clave privada PEM)
    """
    key = _new_key()
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(_name(common_name))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem


def make_server_cert(
    ca_cert_pem: str,
    ca_key_pem: str,
    dns_names: Sequence[str] = ("localhost",),
    ip_addresses: Sequence[str] = ("127.0.0.1",),
    expired: bool = False,
) -> Tuple[str, str]:
    """
    Crea un certificado de servidor firmado por la CA indicada.

    Args:
        dns_names: SAN de tipo DNS (el hostname al que se conecta el cliente debe figurar)
        ip_addresses: SAN de tipo IP
        expired: Si es True el certificado ya ha caducado

    Returns:
        (certificado PEM, clave privada PEM)
    """
    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode())
    ca_key = serialization.load_pem_private_key(ca_key_pem.encode(), password=None)
    key = _new_key()
    now = datetime.datetime.now(datetime.timezone.utc)
    if expired:
        not_before, not_after = now - datetime.timedelta(days=3), now - datetime.timedelta(days=1)
    else:
        not_before, not_after = now - datetime.timedelta(minutes=5), now + datetime.timedelta(
            days=1
        )

    names = [x509.DNSName(name) for name in dns_names]
    names += [x509.IPAddress(ipaddress.ip_address(address)) for address in ip_addresses]
    common_name = dns_names[0] if dns_names else ip_addresses[0]
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem


class FakeTLSServer:
    """
    Servidor TCP con TLS para probar qué hace un driver real al conectar.

    Acepta UNA conexión, hace el handshake TLS con el certificado dado y registra:
    - received: primeros bytes que el cliente envió tras el handshake (en Oracle, su
      paquete CONNECT). Vacío si el cliente rechazó el certificado: es la señal fiable
    - handshake_ok / error: resultado del handshake VISTO DESDE EL SERVIDOR. Con TLS 1.3 el
      servidor lo da por completado antes de que el cliente valide el certificado, así que
      un handshake_ok True no implica que el cliente lo aceptara

    `preamble(connection)` permite negociar antes del TLS (el SSLRequest de PostgreSQL, el
    saludo de MySQL). Si devuelve False el servidor cierra sin hacer TLS, como uno que no lo
    soporta.
    """

    def __init__(self, cert_pem: str, key_pem: str, preamble=None):
        self._directory = tempfile.TemporaryDirectory(prefix="datamap-tls-server-")
        cert_path = os.path.join(self._directory.name, "server.crt")
        key_path = os.path.join(self._directory.name, "server.key")
        with open(cert_path, "w") as handle:
            handle.write(cert_pem)
        with open(key_path, "w") as handle:
            handle.write(key_pem)
        self._context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._context.load_cert_chain(cert_path, key_path)
        self._preamble = preamble
        self._socket = socket.socket()
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(1)
        self._socket.settimeout(15)
        self.port = self._socket.getsockname()[1]
        self.handshake_ok: Optional[bool] = None
        self.error: Optional[str] = None
        self.received = b""
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        try:
            connection, _ = self._socket.accept()
        except OSError:
            return
        connection.settimeout(5)
        try:
            if self._preamble is not None and self._preamble(connection) is False:
                connection.close()
                return
            tls = self._context.wrap_socket(connection, server_side=True)
        except (ssl.SSLError, OSError) as error:
            self.handshake_ok = False
            self.error = str(error)
            connection.close()
            return
        self.handshake_ok = True
        try:
            self.received = tls.recv(4096)
        except (ssl.SSLError, OSError):
            pass
        finally:
            tls.close()

    def __enter__(self) -> "FakeTLSServer":
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._socket.close()
        self._thread.join(timeout=10)
        self._directory.cleanup()


def postgres_ssl_preamble(accept: bool = True):
    """
    Preámbulo de PostgreSQL: el cliente envía un SSLRequest de 8 bytes y el servidor
    responde 'S' (continúa con TLS) o 'N' (no admite TLS).
    """

    def preamble(connection) -> bool:
        connection.recv(8)
        connection.sendall(b"S" if accept else b"N")
        return accept

    return preamble


def mysql_greeting(capabilities: int) -> bytes:
    """Paquete Handshake v10 de MySQL con las capacidades indicadas."""
    salt_1 = b"abcdefgh"
    salt_2 = b"ijklmnopqrst\x00"
    payload = (
        b"\x0a"
        + b"5.7.0-fake\x00"
        + struct.pack("<I", 1)
        + salt_1
        + b"\x00"
        + struct.pack("<H", capabilities & 0xFFFF)
        + b"\x21"
        + struct.pack("<H", 2)
        + struct.pack("<H", capabilities >> 16)
        + bytes([21])
        + b"\x00" * 10
        + salt_2
        + b"mysql_native_password\x00"
    )
    return struct.pack("<I", len(payload))[:3] + b"\x00" + payload


# PROTOCOL_41 | SECURE_CONNECTION | PLUGIN_AUTH, con y sin CLIENT.SSL (0x0800)
MYSQL_CAPABILITIES_WITHOUT_TLS = 0x0200 | 0x8000 | 0x80000
MYSQL_CAPABILITIES_WITH_TLS = MYSQL_CAPABILITIES_WITHOUT_TLS | 0x0800


def mysql_ssl_preamble():
    """
    Preámbulo de MySQL: el servidor saluda anunciando TLS y el cliente responde con un
    SSLRequest (cabecera de 4 bytes + 32) antes de iniciar el handshake TLS.
    """

    def preamble(connection) -> bool:
        connection.sendall(mysql_greeting(MYSQL_CAPABILITIES_WITH_TLS))
        connection.recv(36)
        return True

    return preamble
