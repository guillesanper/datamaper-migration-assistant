"""
Integration tests: revocación de sesiones en POST /api/auth/logout y POST /api/auth/reset.

Recorren la ruta real (router + dependencia + AuthService + CRUDs + BD de test). Cada test usa su
propio usuario verificado porque reset cambia la contraseña y no debe afectar al fixture
compartido `test_user`. Uses the conftest fixtures: client, db_session.
"""

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

from app.crud import email_otp_crud
from app.models.orm import EmailOTP, User
from app.models.orm.session import UserSession
from app.services.auth_service import pwd_context
from app.utils.cookies import verify_signed_cookie

PASSWORD = "Test123!@#"
NEW_PASSWORD = "Nueva123!@#"
OTP_CODE = "RESET123"


# ============================================================================
# Fixture: verified_user
# ============================================================================


@pytest.fixture
def verified_user(db_session):
    """Usuario verificado y único por test, con contraseña conocida"""
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = User(
        id=str(uuid.uuid4()),
        username=f"revoke_{suffix}",
        email=f"revoke_{suffix}@example.com",
        password_hash=pwd_context.hash(PASSWORD),
        created_at=now,
        updated_at=now,
        is_verified=True,
        is_deleted=False,
        failed_login_attempts=0,
    )
    db_session.add(user)
    db_session.commit()

    data = {"id": str(user.id), "username": user.username, "email": user.email}
    yield data

    # Limpieza: no dejamos usuarios sueltos para otros tests
    db_session.rollback()
    db_session.query(UserSession).filter(UserSession.user_id == data["id"]).delete()
    db_session.query(EmailOTP).filter(EmailOTP.user_id == data["id"]).delete()
    db_session.query(User).filter(User.id == data["id"]).delete()
    db_session.commit()


# ============================================================================
# Helpers
# ============================================================================


def _login(client, user, password=PASSWORD):
    """Hace login y devuelve (response, valor firmado de la cookie de sesión)"""
    response = client.post(
        "/api/auth/login", json={"identifier": user["email"], "password": password}
    )
    assert response.status_code == 200, response.text
    return response, response.cookies["session"]


def _me(client, cookie_value):
    """GET /api/auth/me con una cookie concreta (independiente del jar del cliente)"""
    return client.get("/api/auth/me", headers={"Cookie": f"session={cookie_value}"})


def _session_row(db_session, cookie_value):
    """Fila de user_sessions que corresponde a una cookie firmada"""
    raw_token = verify_signed_cookie(cookie_value)
    hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    db_session.expire_all()
    return db_session.query(UserSession).filter(UserSession.session_token == hashed).one()


# ============================================================================
# Tests: logout
# ============================================================================


def test_logout_revokes_session_in_db(client, db_session, verified_user):
    _, cookie = _login(client, verified_user)

    response = client.post("/api/auth/logout")

    assert response.status_code == 200, response.text
    row = _session_row(db_session, cookie)
    assert row.is_revoked is True
    assert row.revoked_reason == "user_logout"
    assert row.revoked_at is not None


def test_logout_makes_the_same_cookie_unusable(client, verified_user):
    _, cookie = _login(client, verified_user)
    assert _me(client, cookie).status_code == 200

    client.post("/api/auth/logout")

    replay = _me(client, cookie)
    assert replay.status_code == 401
    assert replay.json()["detail"]["code"] == "auth.session_revoked"


def test_logout_only_revokes_the_current_session(client, db_session, verified_user):
    _, first_cookie = _login(client, verified_user)
    _, second_cookie = _login(client, verified_user)  # el jar del cliente queda con la segunda

    client.post("/api/auth/logout")

    assert _session_row(db_session, second_cookie).is_revoked is True
    assert _session_row(db_session, first_cookie).is_revoked is False
    assert _me(client, first_cookie).status_code == 200
    assert _me(client, second_cookie).status_code == 401


def test_me_does_not_expose_session_identifiers(client, verified_user):
    _, cookie = _login(client, verified_user)

    response = _me(client, cookie)

    assert response.status_code == 200, response.text
    user = response.json()["data"]["user"]
    assert not any("token" in key for key in user)
    raw_token = verify_signed_cookie(cookie)
    assert raw_token not in response.text
    assert hashlib.sha256(raw_token.encode()).hexdigest() not in response.text


# ============================================================================
# Tests: reset de contraseña
# ============================================================================


def _reset(client, user, code=OTP_CODE, new_password=NEW_PASSWORD):
    return client.post(
        "/api/auth/reset",
        json={"email": user["email"], "code": code, "new_password": new_password},
    )


def test_reset_password_revokes_previous_sessions(client, db_session, verified_user):
    _, first_cookie = _login(client, verified_user)
    _, second_cookie = _login(client, verified_user)
    email_otp_crud.create_otp_orm(db_session, user_id=verified_user["id"], otp_code=OTP_CODE)

    response = _reset(client, verified_user)

    assert response.status_code == 200, response.text
    for cookie in (first_cookie, second_cookie):
        row = _session_row(db_session, cookie)
        assert row.is_revoked is True
        assert row.revoked_reason == "password_reset"
        assert _me(client, cookie).status_code == 401


def test_reset_password_allows_login_with_new_password(client, db_session, verified_user):
    _login(client, verified_user)
    email_otp_crud.create_otp_orm(db_session, user_id=verified_user["id"], otp_code=OTP_CODE)
    assert _reset(client, verified_user).status_code == 200

    _, new_cookie = _login(client, verified_user, password=NEW_PASSWORD)

    assert _me(client, new_cookie).status_code == 200


def test_reset_password_with_wrong_code_keeps_sessions(client, db_session, verified_user):
    _, cookie = _login(client, verified_user)
    email_otp_crud.create_otp_orm(db_session, user_id=verified_user["id"], otp_code=OTP_CODE)

    response = _reset(client, verified_user, code="ZZZZZZZZ")

    assert response.status_code == 400
    assert _session_row(db_session, cookie).is_revoked is False
    assert _me(client, cookie).status_code == 200
