"""
POST /api/settings/avatar: límites de tamaño, formato real y dimensiones.

Antes se leía el fichero entero a memoria antes de comprobar el tamaño, el formato solo
se comprobaba por el content_type que manda el cliente y no había límite de píxeles: un
PNG de pocos KB podía declarar un lienzo enorme y tumbar el worker al decodificarlo.
"""

import struct
import zlib
from io import BytesIO

import pytest
from PIL import Image

from main import app


@pytest.fixture
def client_with_auth(client, test_user):
    from app.routers.dependencies import get_current_user_orm

    app.dependency_overrides[get_current_user_orm] = lambda: test_user
    yield client
    app.dependency_overrides.pop(get_current_user_orm, None)


def _image_bytes(fmt: str, size=(64, 48)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, format=fmt)
    return buf.getvalue()


def _png_header_only(width: int, height: int) -> bytes:
    """PNG mínimo que declara width x height sin el contenido de los píxeles."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


def _upload(client, content: bytes, content_type: str = "image/png"):
    return client.post("/api/settings/avatar", files={"file": ("avatar", content, content_type)})


@pytest.mark.integration
def test_valid_png_is_accepted(client_with_auth):
    r = _upload(client_with_auth, _image_bytes("PNG"))
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"].startswith("/api/uploads/avatars/")


@pytest.mark.integration
def test_file_over_limit_is_rejected(client_with_auth):
    from app.routers.user_settings import AVATAR_MAX_BYTES

    r = _upload(client_with_auth, b"\x00" * (AVATAR_MAX_BYTES + 1))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "user.image_size"


@pytest.mark.integration
def test_huge_canvas_is_rejected_before_decoding(client_with_auth):
    """Unos pocos bytes que declaran 50000x50000 píxeles (2.500 megapíxeles)"""
    r = _upload(client_with_auth, _png_header_only(50_000, 50_000))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "user.image_size"


@pytest.mark.integration
def test_large_canvas_under_pillow_limit_is_rejected(client_with_auth):
    """5000x5000 no llega al límite de Pillow pero sí al nuestro (4096x4096)"""
    r = _upload(client_with_auth, _png_header_only(5_000, 5_000))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "user.image_size"


@pytest.mark.integration
def test_real_format_must_match_allowed_list(client_with_auth):
    """El cliente dice image/png pero manda un BMP"""
    r = _upload(client_with_auth, _image_bytes("BMP"), content_type="image/png")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "user.image_format"


@pytest.mark.integration
def test_not_an_image_is_rejected(client_with_auth):
    r = _upload(client_with_auth, b"<svg onload=alert(1)>", content_type="image/png")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "user.image_process"
