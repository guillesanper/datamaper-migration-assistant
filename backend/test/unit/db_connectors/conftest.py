"""
Fixtures compartidas de los tests de conectores.

El paquete `test` choca con el de la biblioteca estándar, así que el helper de
certificados se carga por ruta en vez de importarlo por nombre.
"""

import importlib.util
from pathlib import Path

import pytest

_TLS_CERTS_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "tls_certs.py"


def _load_tls_certs():
    spec = importlib.util.spec_from_file_location("tls_certs", _TLS_CERTS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def tls_certs():
    """Módulo con generadores de certificados de prueba (ver fixtures/tls_certs.py)."""
    return _load_tls_certs()


@pytest.fixture(scope="session")
def ca_pem(tls_certs) -> str:
    """Certificado PEM de una CA de prueba."""
    return tls_certs.make_ca()[0]


@pytest.fixture(scope="session")
def ca_key_pem(tls_certs) -> str:
    """Clave privada PEM de una CA de prueba (nunca debe aceptarse como CA)."""
    return tls_certs.make_ca()[1]
