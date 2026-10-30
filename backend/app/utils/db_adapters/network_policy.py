"""
Network Policy for External Database Connections

Impide que los conectores se usen para SSRF: por defecto solo se permite conectar a
hosts que resuelven a direcciones IP públicas (globalmente enrutables).

Configuración (variables de entorno):
- DB_CONNECTOR_ALLOW_PRIVATE_HOSTS: "true" permite cualquier destino (despliegues
  on-premise o desarrollo). Por defecto "true" solo si ENV es development/dev/debug.
- DB_CONNECTOR_ALLOWED_NETWORKS: lista separada por comas de redes CIDR internas
  permitidas explícitamente (ej: "10.20.0.0/16,192.168.5.10/32").

Nota: la validación se repite cada vez que se crea un adapter (no solo al crear la
sesión), lo que reduce la ventana de DNS rebinding entre validación y conexión.
"""

import ipaddress
import os
import socket
from typing import List, Union

from .exceptions import DBHostNotAllowedError

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]

_DEVELOPMENT_ENVS = {"development", "dev", "debug"}


def _private_hosts_allowed() -> bool:
    default = os.getenv("ENV", "production").lower() in _DEVELOPMENT_ENVS
    value = os.getenv("DB_CONNECTOR_ALLOW_PRIVATE_HOSTS")
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes")


def _allowed_networks() -> List[IPNetwork]:
    networks = []
    for item in os.getenv("DB_CONNECTOR_ALLOWED_NETWORKS", "").split(","):
        item = item.strip()
        if item:
            networks.append(ipaddress.ip_network(item, strict=False))
    return networks


def _resolve(host: str, port: int) -> List[IPAddress]:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise DBHostNotAllowedError(f"Cannot resolve host '{host}'")

    addresses = []
    for info in infos:
        address = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        # ::ffff:10.0.0.1 debe evaluarse como 10.0.0.1
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        addresses.append(address)
    return addresses


def validate_connection_host(host: str, port: int) -> None:
    """
    Verifica que el host esté permitido por la política de red.

    Todas las direcciones a las que resuelve el host deben ser públicas o estar en
    DB_CONNECTOR_ALLOWED_NETWORKS.

    Raises:
        DBHostNotAllowedError: Si el host no resuelve o resuelve a una dirección interna
    """
    if _private_hosts_allowed():
        return

    allowed_networks = _allowed_networks()
    for address in _resolve(host, port):
        if any(address in network for network in allowed_networks):
            continue
        if not address.is_global or address.is_multicast:
            raise DBHostNotAllowedError(
                f"Connections to internal or reserved addresses are not allowed (host '{host}')"
            )
