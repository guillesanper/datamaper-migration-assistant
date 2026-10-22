"""
Master key de cifrado (ENCRYPTION_MASTER_KEY).

Sin dependencias de la app: lo usa también la validación de configuración al arrancar.
"""

import base64
import binascii
from typing import Union

MASTER_KEY_BYTES = 32  # AES-256


class InvalidMasterKeyError(ValueError):
    """La master key no es base64 de 32 bytes."""


def parse_master_key(value: Union[str, bytes]) -> bytes:
    """
    Devuelve los 32 bytes de la master key.

    Acepta los bytes en crudo o su codificación base64 (estricta). Antes cualquier texto
    se aceptaba: base64 laxo que descartaba caracteres no válidos o, si fallaba, el texto
    rellenado con \\x00 hasta 32 bytes; "password" daba una clave de 6 bytes.

    Raises:
        InvalidMasterKeyError: Si no son exactamente 32 bytes
    """
    if isinstance(value, bytes):
        key = value
    else:
        try:
            key = base64.b64decode(value.strip(), validate=True)
        except (binascii.Error, ValueError):
            raise InvalidMasterKeyError(
                "ENCRYPTION_MASTER_KEY must be the base64 encoding of 32 random bytes "
                '(e.g. python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())")'
            )

    if len(key) != MASTER_KEY_BYTES:
        raise InvalidMasterKeyError(
            f"ENCRYPTION_MASTER_KEY must decode to {MASTER_KEY_BYTES} bytes, got {len(key)}"
        )
    return key
