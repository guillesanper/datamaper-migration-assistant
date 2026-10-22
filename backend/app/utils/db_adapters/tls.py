"""
Política TLS de los adapters.

Este es el ÚNICO módulo donde se decide cómo se verifica (o no) el servidor al conectar.
Los adapters piden aquí sus opciones y no deben contener literales que desactiven la
verificación (sslmode débil, TrustServerCertificate=yes, CERT_NONE...); un test estático
vigila que así sea.

Reglas:
- Se verifica certificado y hostname por defecto.
- El opt-out (tls_verify=False) salta SOLO la verificación: el cifrado sigue siendo
  obligatorio y exige confirmar el hostname.
- Ante cualquier duda (valor no booleano, CA ilegible) se rechaza; nunca se degrada.
"""

import os
import re
import ssl
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

import certifi

from .exceptions import DBValidationError
from .validators import normalize_hostname


@dataclass(frozen=True)
class TLSOptions:
    """Opciones TLS ya validadas de una conexión."""

    verify: bool = True
    ca_pem: Optional[str] = None

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "TLSOptions":
        """
        Extrae y valida las opciones TLS de la configuración de un adapter.

        Aunque DBConnectionConfig ya valida estas reglas, un adapter puede construirse
        con un dict directamente, así que se repiten aquí.

        Raises:
            DBValidationError: Si la configuración TLS no es válida
        """
        verify = config.get("tls_verify", True)
        if not isinstance(verify, bool):
            raise DBValidationError("Invalid tls_verify: must be a boolean")

        ca_pem = config.get("tls_ca_pem")
        if ca_pem is not None:
            if not isinstance(ca_pem, str) or not ca_pem.strip():
                raise DBValidationError("Invalid tls_ca_pem: must be a PEM string")
            if "PRIVATE KEY" in ca_pem:
                raise DBValidationError("Invalid tls_ca_pem: private keys are not accepted")

        if not verify:
            if ca_pem:
                raise DBValidationError("tls_ca_pem cannot be combined with tls_verify=false")
            confirmed = normalize_hostname(str(config.get("confirm_hostname") or ""))
            if confirmed != normalize_hostname(str(config.get("host") or "")):
                raise DBValidationError("confirm_hostname must match host when tls_verify is false")

        return cls(verify=verify, ca_pem=ca_pem)


# Textos con los que los drivers (libpq, PyMySQL, ODBC, oracledb) informan de un fallo TLS
_TLS_ERROR_PATTERN = re.compile(
    r"certificate|ssl error|ssl handshake|ssl connection|ssl provider"
    r"|does not support ssl|ssl is required|\btls\b|sslv3|hostname mismatch",
    re.IGNORECASE,
)


def is_tls_error(message: str) -> bool:
    """
    True si el mensaje de un driver describe un fallo de TLS (certificado, hostname, handshake).

    No cuentan: los rechazos de pg_hba.conf (mencionan SSL pero son de autorización) ni un
    corte de la conexión tras un handshake aceptado ("SSL SYSCALL error: EOF detected").
    """
    if "pg_hba" in message:
        return False
    return _TLS_ERROR_PATTERN.search(message) is not None


def default_ca_bundle() -> str:
    """Ruta del bundle de CAs de confianza: el del sistema si existe, o el de certifi."""
    system_bundle = ssl.get_default_verify_paths().cafile
    if system_bundle and os.path.isfile(system_bundle):
        return system_bundle
    return certifi.where()


@contextmanager
def trust_file(ca_pem: Optional[str]) -> Iterator[str]:
    """
    Entrega la ruta del archivo de CAs con el que verificar al servidor.

    Sin CA propia es el bundle del sistema (no se toca ni se borra). Con CA propia se vuelca
    a un archivo temporal privado, porque psycopg2 y PyMySQL solo aceptan una ruta, y se borra
    siempre al salir, incluso si el driver lanza una excepción.
    """
    if ca_pem is None:
        yield default_ca_bundle()
        return

    fd, path = tempfile.mkstemp(prefix="datamap-ca-", suffix=".pem")
    try:
        try:
            os.write(fd, ca_pem.encode())
        finally:
            os.close(fd)
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def build_ssl_context(options: TLSOptions) -> ssl.SSLContext:
    """
    Construye el SSLContext para los drivers que lo aceptan (oracledb).

    La CA propia se carga desde memoria, sin pasar por disco. Con CA propia solo se confía
    en ella; sin ella, en el bundle del sistema.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    if options.verify:
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        if options.ca_pem:
            context.load_verify_locations(cadata=options.ca_pem)
        else:
            context.load_verify_locations(cafile=default_ca_bundle())
    else:
        # El orden importa: check_hostname debe desactivarse antes que verify_mode
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    return context
