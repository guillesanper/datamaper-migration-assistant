"""
Integration tests: revocación de sesiones en POST /api/auth/logout, POST /api/auth/reset y
PUT /api/settings/password; vigencia de la cookie de sesión y login de cuentas bloqueadas.

Recorren la ruta real (router + dependencia + AuthService + CRUDs + BD de test). Cada test usa su
propio usuario verificado porque reset y change-password cambian la contraseña y el bloqueo toca
los intentos fallidos: no deben afectar al fixture compartido `test_user`. Uses the conftest
fixtures: client, db_session.
"""

import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.config.security import security_settings
from app.crud import email_otp_crud
from app.crud.api_key_crud import create_api_key_orm
from app.models.orm import EmailOTP, User
from app.models.orm.session import UserSession
from app.services.auth_service import AuthService, DatabaseError, pwd_context
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


def test_reset_password_database_error_returns_standard_500(client, verified_user):
    with patch.object(AuthService, "reset_password", side_effect=DatabaseError("detalle interno")):
        response = _reset(client, verified_user)

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert "detalle interno" not in response.text


def test_reset_password_updates_password_changed_at(client, db_session, verified_user):
    stale = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db_session.query(User).filter(User.id == verified_user["id"]).update(
        {"password_changed_at": stale}
    )
    db_session.commit()
    email_otp_crud.create_otp_orm(db_session, user_id=verified_user["id"], otp_code=OTP_CODE)
    started = datetime.now(timezone.utc)

    response = _reset(client, verified_user)

    assert response.status_code == 200, response.text
    db_session.expire_all()
    user = db_session.query(User).filter(User.id == verified_user["id"]).one()
    assert user.password_changed_at >= started - timedelta(seconds=5)


# ============================================================================
# Tests: cambio de contraseña (PUT /api/settings/password)
# ============================================================================


def _change_password(client, cookie, current=PASSWORD, new=NEW_PASSWORD):
    """PUT /api/settings/password con una cookie concreta (sesión real, sin dependency override)"""
    return client.put(
        "/api/settings/password",
        json={"current_password": current, "new_password": new, "confirm_password": new},
        headers={"Cookie": f"session={cookie}"},
    )


def test_change_password_revokes_other_sessions_and_keeps_current(
    client, db_session, verified_user
):
    _, first_cookie = _login(client, verified_user)
    _, second_cookie = _login(client, verified_user)

    response = _change_password(client, second_cookie)

    assert response.status_code == 200, response.text
    assert response.json() == {"success": True, "message": "Contraseña actualizada"}
    first_row = _session_row(db_session, first_cookie)
    assert first_row.is_revoked is True
    assert first_row.revoked_reason == "password_change"
    assert _me(client, first_cookie).status_code == 401
    assert _session_row(db_session, second_cookie).is_revoked is False
    assert _me(client, second_cookie).status_code == 200


def test_change_password_allows_login_with_new_password(client, verified_user):
    _, cookie = _login(client, verified_user)
    assert _change_password(client, cookie).status_code == 200

    _, new_cookie = _login(client, verified_user, password=NEW_PASSWORD)

    assert _me(client, new_cookie).status_code == 200


def test_change_password_with_wrong_current_password_keeps_sessions(
    client, db_session, verified_user
):
    _, first_cookie = _login(client, verified_user)
    _, second_cookie = _login(client, verified_user)

    response = _change_password(client, second_cookie, current="Incorrecta123!@#")

    assert response.status_code == 400
    assert _session_row(db_session, first_cookie).is_revoked is False
    assert _session_row(db_session, second_cookie).is_revoked is False


def test_change_password_with_api_key_revokes_all_sessions(client, db_session, verified_user):
    """Con API key no hay cookie de sesión: no hay una sesión «actual» que conservar"""
    _, first_cookie = _login(client, verified_user)
    _, second_cookie = _login(client, verified_user)
    _, raw_key = create_api_key_orm(db_session, uuid.UUID(verified_user["id"]), "deuda_p1", None)
    client.cookies.clear()

    response = client.put(
        "/api/settings/password",
        json={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
        headers={"Authorization": f"Bearer {raw_key}"},
    )

    assert response.status_code == 200, response.text
    for cookie in (first_cookie, second_cookie):
        row = _session_row(db_session, cookie)
        assert row.is_revoked is True
        assert row.revoked_reason == "password_change"


# ============================================================================
# Tests: vigencia de la cookie de sesión
# ============================================================================


def _cookie_max_age(response):
    """Max-Age (segundos) de la cookie `session` emitida en la cabecera Set-Cookie"""
    match = re.search(r"session=[^;]*;.*?Max-Age=(\d+)", response.headers["set-cookie"], re.I)
    assert match, response.headers["set-cookie"]
    return int(match.group(1))


def test_session_cookie_max_age_matches_session_expiry(client, db_session, verified_user):
    response, cookie = _login(client, verified_user)

    row = _session_row(db_session, cookie)
    session_lifetime = int((row.expires_at - row.created_at).total_seconds())

    assert _cookie_max_age(response) == 24 * 3600
    assert _cookie_max_age(response) == session_lifetime


# ============================================================================
# Tests: cuenta bloqueada (login -> 423, no 500)
# ============================================================================


def _login_raw(client, user, password=PASSWORD):
    """Login sin exigir 200: devuelve la respuesta tal cual"""
    return client.post("/api/auth/login", json={"identifier": user["email"], "password": password})


def _set_lock(db_session, user, locked_until, attempts):
    db_session.query(User).filter(User.id == user["id"]).update(
        {"locked_until": locked_until, "failed_login_attempts": attempts}
    )
    db_session.commit()


def _user_row(db_session, user):
    db_session.expire_all()
    return db_session.query(User).filter(User.id == user["id"]).one()


def _session_count(db_session, user):
    return db_session.query(UserSession).filter(UserSession.user_id == user["id"]).count()


def test_login_with_active_lock_returns_423(client, db_session, verified_user):
    locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
    _set_lock(db_session, verified_user, locked_until, security_settings.MAX_FAILED_LOGIN_ATTEMPTS)

    response = _login_raw(client, verified_user)  # contraseña CORRECTA

    assert response.status_code == 423, response.text
    assert response.json()["error"] == "account_locked"
    assert _session_count(db_session, verified_user) == 0


def test_login_locked_by_failed_attempts_returns_423(client, db_session, verified_user):
    """Camino completo: los fallos bloquean y el login posterior (contraseña correcta) da 423"""
    for _ in range(security_settings.MAX_FAILED_LOGIN_ATTEMPTS):
        assert _login_raw(client, verified_user, password="Incorrecta123!@#").status_code == 401

    response = _login_raw(client, verified_user)

    assert response.status_code == 423, response.text
    assert response.json()["error"] == "account_locked"
    # El bloqueo se guarda como instante absoluto correcto (ahora + duración configurada)
    expected = datetime.now(timezone.utc) + timedelta(
        seconds=security_settings.ACCOUNT_LOCKOUT_DURATION
    )
    locked_until = _user_row(db_session, verified_user).locked_until
    assert abs((locked_until - expected).total_seconds()) < 60


def test_login_with_expired_lock_succeeds_and_clears_it(client, db_session, verified_user):
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    _set_lock(db_session, verified_user, expired, security_settings.MAX_FAILED_LOGIN_ATTEMPTS)

    response = _login_raw(client, verified_user)

    assert response.status_code == 200, response.text
    row = _user_row(db_session, verified_user)
    assert row.locked_until is None
    assert row.failed_login_attempts == 0
