"""
Integration tests for POST /api/auth/verify-code.

Recorren la ruta real (router + AuthService + CRUDs + BD de test) con un OTP conocido, sin pasar
por el envío de correo. Uses the conftest fixtures: client, db_session.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.crud import email_otp_crud
from app.models.orm import EmailOTP, User
from app.models.orm.session import UserSession

OTP_CODE = "ABCD1234"
TOTP_SEED = "JBSWY3DPEHPK3PXP"

# Mismos campos que devuelve /api/auth/login
LOGIN_USER_FIELDS = {"id", "username", "email", "is_verified", "created_at"}


# ============================================================================
# Fixture: unverified_user
# ============================================================================


@pytest.fixture
def unverified_user(db_session):
    """Usuario sin verificar, con un OTP de código conocido y un secreto TOTP de relleno"""
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = User(
        id=str(uuid.uuid4()),
        username=f"verify_{suffix}",
        email=f"verify_{suffix}@example.com",
        password_hash="not-a-real-hash",
        created_at=now,
        updated_at=now,
        is_verified=False,
        is_deleted=False,
        failed_login_attempts=0,
        totp_secret=TOTP_SEED,
    )
    db_session.add(user)
    db_session.commit()

    email_otp_crud.create_otp_orm(db_session, user_id=user.id, otp_code=OTP_CODE)

    data = {"id": str(user.id), "username": user.username, "email": user.email}
    yield data

    # Limpieza: la BD de test es por worker, pero no dejamos usuarios sueltos para otros tests
    db_session.rollback()
    db_session.query(UserSession).filter(UserSession.user_id == data["id"]).delete()
    db_session.query(EmailOTP).filter(EmailOTP.user_id == data["id"]).delete()
    db_session.query(User).filter(User.id == data["id"]).delete()
    db_session.commit()


def _verify(client, email, code):
    return client.post("/api/auth/verify-code", json={"email": email, "code": code})


def _user_row(db_session, user_id):
    db_session.expire_all()
    return db_session.query(User).filter(User.id == user_id).one()


# ============================================================================
# Tests: código correcto
# ============================================================================


def test_verify_code_returns_200_and_session_cookie(client, unverified_user):
    response = _verify(client, unverified_user["email"], OTP_CODE)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == unverified_user["email"]
    assert "session" in response.cookies


def test_verify_code_marks_user_verified_and_creates_session(client, db_session, unverified_user):
    response = _verify(client, unverified_user["email"], OTP_CODE)
    assert response.status_code == 200, response.text

    assert _user_row(db_session, unverified_user["id"]).is_verified is True
    sessions = (
        db_session.query(UserSession).filter(UserSession.user_id == unverified_user["id"]).all()
    )
    assert len(sessions) == 1
    assert sessions[0].is_revoked is False
    otp = db_session.query(EmailOTP).filter(EmailOTP.user_id == unverified_user["id"]).first()
    assert otp is None


def test_verify_code_response_user_has_only_login_fields(client, unverified_user):
    response = _verify(client, unverified_user["email"], OTP_CODE)
    assert response.status_code == 200, response.text

    user = response.json()["data"]["user"]
    assert set(user) == LOGIN_USER_FIELDS
    assert user["is_verified"] is True
    assert TOTP_SEED not in response.text
    assert "password_hash" not in response.text


def test_verify_code_cookie_authenticates_me(client, unverified_user):
    response = _verify(client, unverified_user["email"], OTP_CODE)
    assert response.status_code == 200, response.text

    me = client.get("/api/auth/me")

    assert me.status_code == 200, me.text
    assert me.json()["data"]["user"]["email"] == unverified_user["email"]


def test_verify_code_cannot_be_replayed(client, unverified_user):
    first = _verify(client, unverified_user["email"], OTP_CODE)
    assert first.status_code == 200, first.text

    second = _verify(client, unverified_user["email"], OTP_CODE)

    assert second.status_code == 400
    assert second.json()["message"] == "Email ya verificado"


# ============================================================================
# Tests: código incorrecto
# ============================================================================


def test_verify_code_wrong_code_returns_400_without_session(client, db_session, unverified_user):
    response = _verify(client, unverified_user["email"], "ZZZZZZZZ")

    assert response.status_code == 400
    assert response.json()["message"] == "Código inválido o expirado"
    assert "session" not in response.cookies
    assert _user_row(db_session, unverified_user["id"]).is_verified is False
    sessions = (
        db_session.query(UserSession).filter(UserSession.user_id == unverified_user["id"]).all()
    )
    assert sessions == []
