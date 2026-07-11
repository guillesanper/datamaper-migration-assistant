"""
Integration tests for /api/settings/* endpoints.

Authentication is mocked via app.dependency_overrides[get_current_user_orm].
Uses the conftest fixtures: client, test_user, db_session.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app

# ============================================================================
# Fixture: client_with_auth
# ============================================================================


@pytest.fixture
def client_with_auth(client, test_user, db_session):
    from app.routers.dependencies import get_current_user_orm

    def mock_get_current_user_orm():
        return test_user  # {"id": str, "username": str, "email": str, "password": str}

    app.dependency_overrides[get_current_user_orm] = mock_get_current_user_orm
    yield client
    app.dependency_overrides.pop(get_current_user_orm, None)


# ============================================================================
# Tests: Perfil
# ============================================================================


def test_get_profile_returns_200(client_with_auth):
    response = client_with_auth.get("/api/settings/profile")

    assert response.status_code == 200
    data = response.json()
    assert "username" in data
    assert "email" in data
    assert "avatar_url" in data
    assert "created_at" in data
    assert "is_verified" in data
    assert "totp_enabled" in data


def test_update_profile_username(client_with_auth):
    new_username = f"nuevo_{str(uuid.uuid4())[:8]}"

    response = client_with_auth.put("/api/settings/profile", json={"username": new_username})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["user"]["username"] == new_username


def test_change_password_success(client_with_auth, test_user):
    response = client_with_auth.put(
        "/api/settings/password",
        json={
            "current_password": test_user["password"],
            "new_password": "NewSecure123!@#",
            "confirm_password": "NewSecure123!@#",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_change_password_wrong_current(client_with_auth):
    response = client_with_auth.put(
        "/api/settings/password",
        json={
            "current_password": "WrongPassword999!",
            "new_password": "NewSecure123!@#",
            "confirm_password": "NewSecure123!@#",
        },
    )

    assert response.status_code == 400


def test_change_password_mismatch(client_with_auth, test_user):
    response = client_with_auth.put(
        "/api/settings/password",
        json={
            "current_password": test_user["password"],
            "new_password": "NewSecure123!@#",
            "confirm_password": "DifferentPassword999!",
        },
    )

    assert response.status_code == 400


# ============================================================================
# Tests: Notificaciones
# ============================================================================


def test_get_notifications_returns_structure(client_with_auth):
    response = client_with_auth.get("/api/settings/notifications")

    assert response.status_code == 200
    data = response.json()
    assert "email_notifications" in data
    assert "in_app_notifications" in data
    assert isinstance(data["email_notifications"], dict)
    assert isinstance(data["in_app_notifications"], dict)


def test_update_notifications(client_with_auth):
    response = client_with_auth.put(
        "/api/settings/notifications",
        json={
            "email_notifications": {
                "invitations": True,
                "comments": False,
                "version_updates": True,
                "security_alerts": True,
            },
            "in_app_notifications": {
                "invitations": True,
                "comments": True,
                "version_updates": False,
                "security_alerts": True,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


# ============================================================================
# Tests: Preferencias
# ============================================================================


def test_get_preferences_returns_fields(client_with_auth):
    response = client_with_auth.get("/api/settings/preferences")

    assert response.status_code == 200
    data = response.json()
    assert "language" in data
    assert "timezone" in data
    assert "default_db_type" in data
    assert "default_export_format" in data


def test_update_preferences_language(client_with_auth):
    response = client_with_auth.put("/api/settings/preferences", json={"language": "en"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["preferences"]["language"] == "en"


# ============================================================================
# Tests: Sesiones
# ============================================================================


def test_get_sessions_returns_list(client_with_auth):
    response = client_with_auth.get("/api/settings/sessions")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_revoke_session_not_found(client_with_auth):
    fake_session_id = str(uuid.uuid4())

    response = client_with_auth.delete(f"/api/settings/sessions/{fake_session_id}")

    assert response.status_code == 404


# ============================================================================
# Tests: Historial de accesos
# ============================================================================


def test_get_access_history_returns_list(client_with_auth):
    response = client_with_auth.get("/api/settings/access-history")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_access_history_with_params(client_with_auth):
    response = client_with_auth.get("/api/settings/access-history?limit=5&offset=0")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ============================================================================
# Tests: 2FA
# ============================================================================


def test_setup_2fa_returns_secret_and_qr(client_with_auth):
    response = client_with_auth.post("/api/settings/2fa/setup")

    assert response.status_code == 200
    data = response.json()
    assert "secret" in data
    assert "otpauth_url" in data
    assert "qr_code_base64" in data


def test_verify_2fa_invalid_code(client_with_auth):
    # Setup first
    setup_resp = client_with_auth.post("/api/settings/2fa/setup")
    assert setup_resp.status_code == 200

    response = client_with_auth.post("/api/settings/2fa/verify", json={"code": "000000"})

    assert response.status_code == 400


def test_verify_2fa_valid_code(client_with_auth):
    import pyotp

    setup_resp = client_with_auth.post("/api/settings/2fa/setup")
    assert setup_resp.status_code == 200
    secret = setup_resp.json()["secret"]

    code = pyotp.TOTP(secret).now()

    response = client_with_auth.post("/api/settings/2fa/verify", json={"code": code})

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_disable_2fa_not_enabled(client_with_auth, test_user, db_session):
    """Intentar deshabilitar 2FA sin haberlo activado → 400."""
    # Reset 2FA state — previous tests may have enabled it (test_verify_2fa_valid_code commits totp_enabled=True)
    from app.models.orm import User

    user = db_session.query(User).filter(User.id == test_user["id"]).first()
    if user:
        user.totp_enabled = False  # type: ignore[assignment]
        user.totp_secret = None  # type: ignore[assignment]
        db_session.commit()

    response = client_with_auth.request(
        "DELETE",
        "/api/settings/2fa",
        json={"code": "123456", "password": test_user["password"]},
    )

    assert response.status_code == 400


# ============================================================================
# Tests: API Keys
# ============================================================================


def test_get_api_keys_empty(client_with_auth):
    response = client_with_auth.get("/api/settings/api-keys")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_api_key(client_with_auth):
    response = client_with_auth.post("/api/settings/api-keys", json={"name": "Test Key"})

    assert response.status_code == 200
    data = response.json()
    assert "key_id" in data
    assert "name" in data
    assert "raw_key" in data
    assert "key_prefix" in data
    assert "created_at" in data
    assert data["raw_key"].startswith("rlk_")
    assert data["name"] == "Test Key"


def test_create_api_key_with_expiration(client_with_auth):
    response = client_with_auth.post(
        "/api/settings/api-keys", json={"name": "Expiring Key", "expires_in_days": 30}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["raw_key"].startswith("rlk_")


def test_api_key_appears_in_list(client_with_auth):
    create_resp = client_with_auth.post("/api/settings/api-keys", json={"name": "Listed Key"})
    assert create_resp.status_code == 200
    created_prefix = create_resp.json()["key_prefix"]

    list_resp = client_with_auth.get("/api/settings/api-keys")
    assert list_resp.status_code == 200

    keys = list_resp.json()
    prefixes = [k.get("key_prefix") for k in keys]
    assert created_prefix in prefixes


def test_revoke_api_key(client_with_auth):
    create_resp = client_with_auth.post("/api/settings/api-keys", json={"name": "To Revoke"})
    assert create_resp.status_code == 200
    key_id = create_resp.json()["key_id"]

    revoke_resp = client_with_auth.delete(f"/api/settings/api-keys/{key_id}")

    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["success"] is True


def test_revoke_nonexistent_key(client_with_auth):
    fake_id = str(uuid.uuid4())

    response = client_with_auth.delete(f"/api/settings/api-keys/{fake_id}")

    assert response.status_code == 404


def test_revoke_invalid_uuid(client_with_auth):
    response = client_with_auth.delete("/api/settings/api-keys/not-a-uuid")

    assert response.status_code == 400


def test_raw_key_not_in_list(client_with_auth):
    """raw_key nunca aparece en el listado de keys."""
    client_with_auth.post("/api/settings/api-keys", json={"name": "Secret Key"})

    list_resp = client_with_auth.get("/api/settings/api-keys")
    assert list_resp.status_code == 200

    for item in list_resp.json():
        assert "raw_key" not in item
        assert "key_hash" not in item
