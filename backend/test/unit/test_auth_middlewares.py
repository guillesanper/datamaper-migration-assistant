"""
Rate limiting y CSRF montados como middleware HTTP (como en producción).

- Las claves de RATE_LIMITS no coincidían con las rutas reales: el login nunca se limitaba.
- HTTPException lanzada dentro de un middleware HTTP se convertía en un 500.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.security import security_settings
from app.middleware import csrf_protection, rate_limiting


@pytest.fixture
def production_mode(monkeypatch):
    monkeypatch.setattr(type(security_settings), "DEVELOPMENT_MODE", False)


def make_client(middleware, *paths):
    app = FastAPI()
    for path in paths:
        app.add_api_route(path, lambda: {"ok": True}, methods=["POST"])
    app.middleware("http")(middleware)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def counting_rate_limit_store():
    calls = []

    def check_limit(db, **kwargs):
        calls.append(kwargs["endpoint"])
        return {"is_allowed": calls.count(kwargs["endpoint"]) <= kwargs["max_requests"]}

    class _Db:
        def close(self):
            pass

    with (
        patch.object(rate_limiting.rate_limit_crud, "check_limit_orm", side_effect=check_limit),
        patch.object(rate_limiting.rate_limit_crud, "get_info_orm", return_value=None),
        patch.object(rate_limiting, "get_db_session", side_effect=lambda: iter([_Db()])),
    ):
        yield calls


@pytest.mark.parametrize(
    "path", ["/api/auth/login", "/api/auth/verify-code", "/api/auth/reset", "/api/auth/login/"]
)
def test_auth_endpoints_are_rate_limited(production_mode, counting_rate_limit_store, path):
    client = make_client(rate_limiting.rate_limit_middleware, path)
    limit = security_settings.get_rate_limit_config(path)["max_attempts"]

    codes = [client.post(path).status_code for _ in range(limit + 2)]

    assert codes[:limit] == [200] * limit
    assert codes[limit:] == [429, 429]


def test_rate_limited_response_is_429_with_retry_after(production_mode, counting_rate_limit_store):
    client = make_client(rate_limiting.rate_limit_middleware, "/api/auth/login")
    for _ in range(security_settings.RATE_LIMIT_LOGIN_ATTEMPTS):
        client.post("/api/auth/login")

    response = client.post("/api/auth/login")

    assert response.status_code == 429
    assert response.headers["Retry-After"]
    assert response.json()["detail"]


def test_decorator_does_not_count_middleware_endpoints_twice(
    production_mode, counting_rate_limit_store
):
    app = FastAPI()

    @app.post("/api/auth/reset")
    @rate_limiting.rate_limit(5, 600)
    async def reset(request: rate_limiting.Request):
        return {"ok": True}

    app.middleware("http")(rate_limiting.rate_limit_middleware)
    TestClient(app).post("/api/auth/reset")

    assert counting_rate_limit_store == ["/api/auth/reset"]


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
