"""
CSRF montado como middleware HTTP (como en producción).

HTTPException lanzada dentro de un middleware HTTP se convertía en un 500.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.security import security_settings
from app.middleware import csrf_protection


@pytest.fixture
def production_mode(monkeypatch):
    # Clase e instancia: un monkeypatch previo sobre la instancia taparía el de la clase
    monkeypatch.setattr(type(security_settings), "DEVELOPMENT_MODE", False)
    monkeypatch.setattr(security_settings, "DEVELOPMENT_MODE", False)


def make_client(middleware, *paths):
    app = FastAPI()
    for path in paths:
        app.add_api_route(path, lambda: {"ok": True}, methods=["POST"])
    app.middleware("http")(middleware)
    return TestClient(app, raise_server_exceptions=False)


def test_csrf_missing_token_is_403_not_500(production_mode):
    client = make_client(csrf_protection.csrf_middleware, "/api/projects")

    response = client.post("/api/projects")

    assert response.status_code == 403
    assert response.json()["detail"]


def test_csrf_invalid_token_is_403(production_mode):
    client = make_client(csrf_protection.csrf_middleware, "/api/projects")

    with patch.object(csrf_protection.CSRFProtection, "validate_csrf_token", return_value=False):
        response = client.post("/api/projects", headers={"X-CSRF-Token": "forged-token"})

    assert response.status_code == 403


def test_csrf_token_is_not_printed(production_mode, capsys):
    client = make_client(csrf_protection.csrf_middleware, "/api/projects")

    client.post("/api/projects", headers={"X-CSRF-Token": "secret-token-value-123"})

    assert "secret-token" not in capsys.readouterr().out
