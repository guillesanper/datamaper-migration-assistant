"""
Seguridad de cuentas contra la API real:

- Reset y cambio de contraseña revocan las sesiones abiertas.
- /forgot existe (el frontend lo llamaba y devolvía 404).
- /forgot, /resend-code, /verify-code y /reset no revelan si un email tiene cuenta.
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app

PASSWORD = "Str0ng!Passw0rd"
NEW_PASSWORD = "N3w!Str0ngPassw0rd"


@pytest.fixture
def account(db_session):
    from app.models.orm import User
    from app.services.auth_service import AuthService

    suffix = uuid.uuid4().hex[:10]
    email = f"acct_{suffix}@example.com"
    user = AuthService(db_session).create_user(
        username=f"acct_{suffix}", email=email, password=PASSWORD
    )
    db_session.query(User).filter(User.id == user["user_id"]).update({"is_verified": True})
    db_session.commit()
    yield {"id": str(user["user_id"]), "email": email}


def login(password=PASSWORD, email=None):
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"identifier": email, "password": password})
    assert response.status_code == 200, response.text
    return client


def otp_for(db_session, user_id, code="ABCD1234"):
    from app.crud import email_otp_crud

    email_otp_crud.create_otp_orm(db_session, user_id=user_id, otp_code=code)
    db_session.commit()
    return code


class TestSessionsRevokedOnPasswordChange:
    def test_reset_revokes_every_session(self, client, account, db_session):
        browser = login(email=account["email"])
        assert browser.get("/api/auth/me").status_code == 200

        response = client.post(
            "/api/auth/reset",
            json={
                "email": account["email"],
                "code": otp_for(db_session, account["id"]),
                "new_password": NEW_PASSWORD,
            },
        )

        assert response.status_code == 200, response.text
        assert browser.get("/api/auth/me").status_code == 401
        login(NEW_PASSWORD, account["email"])

    def test_change_password_keeps_only_current_session(self, client, account):
        current = login(email=account["email"])
        other_device = login(email=account["email"])

        response = current.put(
            "/api/settings/password",
            json={
                "current_password": PASSWORD,
                "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            },
        )

        assert response.status_code == 200, response.text
        assert current.get("/api/auth/me").status_code == 200
        assert other_device.get("/api/auth/me").status_code == 401


class TestNoUserEnumeration:
    @pytest.mark.parametrize("endpoint", ["/api/auth/forgot", "/api/auth/resend-code"])
    def test_same_answer_for_existing_and_unknown_email(self, client, account, endpoint):
        with patch("app.routers.auth.send_verification_code"):
            known = client.post(endpoint, json={"email": account["email"]})
            unknown = client.post(endpoint, json={"email": f"nobody_{uuid.uuid4().hex}@x.com"})

        assert known.status_code == unknown.status_code == 200
        assert known.json() == unknown.json()

    def test_forgot_sends_code_only_to_existing_accounts(self, client, account):
        with patch("app.routers.auth.send_verification_code") as send:
            client.post("/api/auth/forgot", json={"email": account["email"]})
            client.post("/api/auth/forgot", json={"email": f"nobody_{uuid.uuid4().hex}@x.com"})

        assert send.call_count == 1
        assert send.call_args.args[1] == account["email"]

    def test_resend_code_does_not_email_verified_accounts(self, client, account):
        with patch("app.routers.auth.send_verification_code") as send:
            response = client.post("/api/auth/resend-code", json={"email": account["email"]})

        assert response.status_code == 200
        send.assert_not_called()

    @pytest.mark.parametrize("endpoint", ["/api/auth/verify-code", "/api/auth/reset"])
    def test_code_endpoints_do_not_reveal_accounts(self, client, account, endpoint):
        body = {"code": "ZZZZ9999", "new_password": NEW_PASSWORD}
        known = client.post(endpoint, json={**body, "email": account["email"]})
        unknown = client.post(endpoint, json={**body, "email": f"nobody_{uuid.uuid4().hex}@x.com"})

        assert known.status_code == unknown.status_code == 400
        assert known.json()["message"] == unknown.json()["message"]
