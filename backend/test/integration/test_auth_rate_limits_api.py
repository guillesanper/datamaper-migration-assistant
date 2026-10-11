"""
Tests de integración: límites de las rutas de autenticación e intentos por código OTP
(hallazgos 2 y 3 de la deuda de autenticación).

- login, register, verify-code, resend-code y reset responden 429 con `Retry-After` al
  superar su regla por IP (hoy solo resend-code y reset llevan decorador, y lo ignoran).
- resend-code además cuenta por email: varias IPs no pueden mandar correos a una víctima.
- Falsificar X-Forwarded-For no cambia el contador (TRUSTED_PROXY_HOPS=0); con un salto de
  confianza decide la última entrada.
- Un OTP admite OTP_MAX_ATTEMPTS fallos: después el código correcto tampoco vale; el
  reenvío da otra tanda.

Los contadores van a la BD de test sin rollback: cada test usa IPs únicas y borra los
contadores de /api/auth al terminar.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from app.config.security import security_settings
from app.crud import email_otp_crud
from app.models.orm import EmailOTP, User
from app.models.orm.session import UserSession
from app.services.auth_service import AuthenticationError, AuthService, pwd_context
from app.utils.error_codes import ErrorCode, make_error

PASSWORD = "Test123!@#"
OTP_CODE = "ABCD1234"


# ============================================================================
# Fixtures y helpers
# ============================================================================


@pytest.fixture
def production_mode(monkeypatch):
    monkeypatch.setattr(security_settings, "DEVELOPMENT_MODE", False)


@pytest.fixture
def trusted_hops(monkeypatch):
    def _set(hops):
        monkeypatch.setattr(security_settings, "TRUSTED_PROXY_HOPS", hops)

    _set(0)
    return _set


@pytest.fixture(autouse=True)
def clean_auth_counters(db_session):
    """Contadores de /api/auth fuera antes y después (la BD de test no los deshace)"""

    def _clean():
        db_session.rollback()
        db_session.execute(
            text("DELETE FROM security_rate_limits WHERE endpoint LIKE '/api/auth/%'")
        )
        db_session.commit()

    _clean()
    yield
    _clean()


@pytest.fixture
def created_emails(db_session):
    emails = []
    yield emails

    db_session.rollback()
    for email in emails:
        user = db_session.query(User).filter(User.email == email).first()
        if user is None:
            continue
        db_session.query(UserSession).filter(UserSession.user_id == user.id).delete()
        db_session.query(EmailOTP).filter(EmailOTP.user_id == user.id).delete()
        db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


def _ip() -> str:
    raw = uuid.uuid4().bytes
    return f"10.{raw[0]}.{raw[1]}.{raw[2]}"


def _http(ip: str) -> TestClient:
    """Cliente cuya IP de socket es `ip` (la fixture `client` fija la de todos los tests)"""
    from main import app

    return TestClient(app, client=(ip, 50000))


def _tag() -> str:
    return uuid.uuid4().hex[:10]


def _login_body():
    return {"identifier": f"nobody_{_tag()}", "password": "WrongPass1!"}


def _register_body():
    tag = _tag()
    return {
        "username": f"rl_{tag}",
        "email": f"rl_{tag}@example.com",
        "password": "Str0ng!Passw0rd",
        "confirm_password": "Str0ng!Passw0rd",
    }


def _verify_body():
    return {"email": f"nobody_{_tag()}@example.com", "code": OTP_CODE}


def _resend_body():
    return {"email": f"nobody_{_tag()}@example.com"}


def _reset_body():
    return {
        "email": f"nobody_{_tag()}@example.com",
        "code": OTP_CODE,
        "new_password": "Str0ng!Passw0rd",
    }


# (ruta, constructor del cuerpo, límite configurado por IP)
ROUTES = {
    "login": ("/api/auth/login", _login_body, lambda: security_settings.RATE_LIMIT_LOGIN_ATTEMPTS),
    "register": (
        "/api/auth/register",
        _register_body,
        lambda: security_settings.RATE_LIMIT_REGISTER_ATTEMPTS,
    ),
    "verify-code": (
        "/api/auth/verify-code",
        _verify_body,
        lambda: security_settings.RATE_LIMIT_VERIFY_ATTEMPTS,
    ),
    "resend-code": (
        "/api/auth/resend-code",
        _resend_body,
        lambda: security_settings.RATE_LIMIT_RESEND_ATTEMPTS,
    ),
    "reset": ("/api/auth/reset", _reset_body, lambda: security_settings.RATE_LIMIT_RESET_ATTEMPTS),
}


@pytest.fixture
def register_fails_fast():
    """register no crea usuarios ni calcula bcrypt: responde 409 en el acto"""
    with patch.object(AuthService, "create_user", side_effect=AuthenticationError("duplicado")):
        yield


# ============================================================================
# Límite por IP en cada ruta
# ============================================================================


@pytest.mark.parametrize("route", list(ROUTES))
def test_route_returns_429_with_retry_after_when_the_ip_limit_is_exceeded(
    route, client, production_mode, trusted_hops, register_fails_fast
):
    path, body, limit = ROUTES[route]
    http = _http(_ip())

    for attempt in range(limit()):
        response = http.post(path, json=body())
        assert response.status_code != 429, f"{route}: 429 prematuro en el intento {attempt + 1}"

    response = http.post(path, json=body())

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert response.json()["detail"] == make_error(ErrorCode.RATE_LIMIT_EXCEEDED)


@pytest.mark.parametrize("route", list(ROUTES))
def test_route_limit_is_isolated_by_ip(
    route, client, production_mode, trusted_hops, register_fails_fast
):
    path, body, limit = ROUTES[route]
    attacker, bystander = _http(_ip()), _http(_ip())
    for _ in range(limit() + 1):
        attacker.post(path, json=body())

    response = bystander.post(path, json=body())

    assert response.status_code != 429


def test_response_within_the_limit_is_unchanged(client, production_mode, trusted_hops):
    """Dentro del cupo, el endpoint responde lo de siempre (cuerpo y código)"""
    response = _http(_ip()).post("/api/auth/login", json=_login_body())

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_credentials"


def test_limits_stay_permissive_in_development(client, monkeypatch, trusted_hops):
    monkeypatch.setattr(security_settings, "DEVELOPMENT_MODE", True)
    http = _http(_ip())

    statuses = [http.post("/api/auth/login", json=_login_body()).status_code for _ in range(30)]

    assert 429 not in statuses


# ============================================================================
# IP del cliente: X-Forwarded-For
# ============================================================================


def test_forged_x_forwarded_for_cannot_evade_the_login_limit(client, production_mode, trusted_hops):
    trusted_hops(0)
    http = _http(_ip())
    limit = security_settings.RATE_LIMIT_LOGIN_ATTEMPTS

    for i in range(limit):
        http.post(
            "/api/auth/login", json=_login_body(), headers={"X-Forwarded-For": f"203.0.113.{i}"}
        )
    response = http.post(
        "/api/auth/login", json=_login_body(), headers={"X-Forwarded-For": "203.0.113.250"}
    )

    assert response.status_code == 429


def test_with_one_trusted_hop_the_proxy_appended_entry_decides(
    client, production_mode, trusted_hops
):
    trusted_hops(1)
    proxy = _http(_ip())
    real_a, real_b = _ip(), _ip()
    limit = security_settings.RATE_LIMIT_LOGIN_ATTEMPTS

    for i in range(limit):
        proxy.post(
            "/api/auth/login",
            json=_login_body(),
            headers={"X-Forwarded-For": f"203.0.113.{i}, {real_a}"},
        )

    spoofing = proxy.post(
        "/api/auth/login",
        json=_login_body(),
        headers={"X-Forwarded-For": f"203.0.113.250, {real_a}"},
    )
    other_user = proxy.post(
        "/api/auth/login", json=_login_body(), headers={"X-Forwarded-For": real_b}
    )

    assert spoofing.status_code == 429
    assert other_user.status_code != 429


# ============================================================================
# Límite por cuenta (resend-code)
# ============================================================================


def test_resend_code_is_limited_per_email_across_ips(client, production_mode, trusted_hops):
    """Un atacante distribuido (una IP por petición) no puede mandar correos a una víctima"""
    trusted_hops(1)
    proxy = _http(_ip())
    victim = f"victim_{_tag()}@example.com"
    limit = security_settings.RATE_LIMIT_RESEND_ATTEMPTS

    for _ in range(limit):
        response = proxy.post(
            "/api/auth/resend-code", json={"email": victim}, headers={"X-Forwarded-For": _ip()}
        )
        assert response.status_code != 429

    blocked = proxy.post(
        "/api/auth/resend-code", json={"email": victim}, headers={"X-Forwarded-For": _ip()}
    )
    bystander = proxy.post(
        "/api/auth/resend-code",
        json={"email": f"bystander_{_tag()}@example.com"},
        headers={"X-Forwarded-For": _ip()},
    )

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert bystander.status_code != 429


def test_resend_code_email_counter_ignores_case(client, production_mode, trusted_hops):
    trusted_hops(1)
    proxy = _http(_ip())
    local = f"victim_{_tag()}"
    limit = security_settings.RATE_LIMIT_RESEND_ATTEMPTS

    for i in range(limit):
        variant = local.upper() if i % 2 else local
        proxy.post(
            "/api/auth/resend-code",
            json={"email": f"{variant}@example.com"},
            headers={"X-Forwarded-For": _ip()},
        )
    response = proxy.post(
        "/api/auth/resend-code",
        json={"email": f"{local}@Example.com"},
        headers={"X-Forwarded-For": _ip()},
    )

    assert response.status_code == 429


# ============================================================================
# Intentos por OTP en los endpoints
# ============================================================================


@pytest.fixture
def user_with_otp(db_session, created_emails):
    """Usuario no verificado con un OTP conocido (OTP_CODE)"""
    tag = _tag()
    email = f"otp_{tag}@example.com"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = User(
        id=str(uuid.uuid4()),
        username=f"otp_{tag}",
        email=email,
        password_hash=pwd_context.hash(PASSWORD),
        created_at=now,
        updated_at=now,
        is_verified=False,
        is_deleted=False,
        failed_login_attempts=0,
    )
    db_session.add(user)
    db_session.commit()
    created_emails.append(email)
    email_otp_crud.create_otp_orm(db_session, str(user.id), OTP_CODE)
    return {"id": str(user.id), "email": email}


def _wrong_code(attempt: int) -> str:
    return f"WRONG{attempt:03d}"


def _is_verified(db_session, user_id) -> bool:
    db_session.rollback()
    return bool(
        db_session.execute(
            text("SELECT is_verified FROM users WHERE id = :id"), {"id": user_id}
        ).scalar()
    )


def test_verify_code_wrong_attempts_invalidate_the_otp(client, db_session, user_with_otp):
    for attempt in range(security_settings.OTP_MAX_ATTEMPTS):
        response = client.post(
            "/api/auth/verify-code",
            json={"email": user_with_otp["email"], "code": _wrong_code(attempt)},
        )
        assert response.status_code == 400

    response = client.post(
        "/api/auth/verify-code", json={"email": user_with_otp["email"], "code": OTP_CODE}
    )

    assert response.status_code == 400
    assert "session" not in response.cookies
    assert _is_verified(db_session, user_with_otp["id"]) is False


def test_verify_code_correct_code_works_below_the_attempt_limit(client, db_session, user_with_otp):
    for attempt in range(security_settings.OTP_MAX_ATTEMPTS - 1):
        client.post(
            "/api/auth/verify-code",
            json={"email": user_with_otp["email"], "code": _wrong_code(attempt)},
        )

    response = client.post(
        "/api/auth/verify-code", json={"email": user_with_otp["email"], "code": OTP_CODE}
    )

    assert response.status_code == 200
    assert _is_verified(db_session, user_with_otp["id"]) is True


def test_resend_code_gives_a_new_batch_of_attempts(client, db_session, user_with_otp):
    delivered = []

    def capture(to_email, code):
        delivered.append(code)

    for attempt in range(security_settings.OTP_MAX_ATTEMPTS - 1):
        client.post(
            "/api/auth/verify-code",
            json={"email": user_with_otp["email"], "code": _wrong_code(attempt)},
        )

    with patch("app.routers.auth.deliver_verification_email", MagicMock(side_effect=capture)):
        resend = client.post("/api/auth/resend-code", json={"email": user_with_otp["email"]})
    assert resend.status_code == 200
    assert len(delivered) == 1

    # Tras el reenvío caben otra vez OTP_MAX_ATTEMPTS - 1 fallos y el código nuevo vale
    for attempt in range(security_settings.OTP_MAX_ATTEMPTS - 1):
        client.post(
            "/api/auth/verify-code",
            json={"email": user_with_otp["email"], "code": _wrong_code(attempt + 100)},
        )
    response = client.post(
        "/api/auth/verify-code", json={"email": user_with_otp["email"], "code": delivered[0]}
    )

    assert response.status_code == 200
    assert _is_verified(db_session, user_with_otp["id"]) is True


def test_reset_wrong_attempts_invalidate_the_otp(client, db_session, user_with_otp):
    for attempt in range(security_settings.OTP_MAX_ATTEMPTS):
        response = client.post(
            "/api/auth/reset",
            json={
                "email": user_with_otp["email"],
                "code": _wrong_code(attempt),
                "new_password": "Str0ng!Passw0rd",
            },
        )
        assert response.status_code == 400

    response = client.post(
        "/api/auth/reset",
        json={
            "email": user_with_otp["email"],
            "code": OTP_CODE,
            "new_password": "Str0ng!Passw0rd",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == "reset_failed"
