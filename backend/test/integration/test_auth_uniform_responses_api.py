"""
Tests de integración: respuestas uniformes y POST /api/auth/forgot (hallazgo 4 y defecto B de
la deuda de autenticación).

- verify-code y reset: cuenta inexistente, borrada, ya verificada, OTP ausente, caducado o
  erróneo responden lo mismo (400 «Código inválido o expirado»). El motivo real va al log de
  seguridad, no al cliente.
- resend-code y forgot: 200 con el mismo cuerpo exista o no la cuenta; solo actúan sobre las
  cuentas que toca (resend: no verificadas; forgot: verificadas y no borradas) y nunca
  entregan correo a las demás.
- forgot existe (el frontend ya lo llamaba) y el 429 por cuenta no depende de que la cuenta exista.
- El camino «sin cuenta» gasta el mismo hash bcrypt que el real (mitigación de tiempo de mejor
  esfuerzo; las mediciones se hacen en vivo, aquí solo se comprueba que está cableada).

Los contadores van a la BD de test sin rollback: cada test usa IPs únicas y borra los
contadores de /api/auth al terminar.
"""

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from starlette.requests import Request
from starlette.testclient import TestClient

from app.config.security import security_settings
from app.crud import email_otp_crud
from app.models.orm import EmailOTP, User
from app.models.orm.session import UserSession
from app.services.auth_service import pwd_context
from app.utils.security_logger import SecurityLogger

PASSWORD = "Test123!@#"
NEW_PASSWORD = "Str0ng!Passw0rd"
OTP_CODE = "ABCD1234"
WRONG_CODE = "ZZZZZZZZ"
# Un solo hash por proceso: bcrypt cuesta ~0,4 s y aquí no importa la contraseña salvo en el flujo
PASSWORD_HASH = pwd_context.hash(PASSWORD)

INVALID_CODE = "Código inválido o expirado"
VERIFY_FAILED = {"success": False, "error": "verification_failed", "message": INVALID_CODE}
RESET_FAILED = {"success": False, "error": "reset_failed", "message": INVALID_CODE}
RESEND_OK = {"success": True, "message": "Código reenviado correctamente", "data": None}
FORGOT_OK = {
    "success": True,
    "message": "Si la cuenta existe y está verificada, recibirás un código en tu correo",
    "data": None,
}


# ============================================================================
# Fixtures y helpers
# ============================================================================


@pytest.fixture
def production_mode(monkeypatch):
    monkeypatch.setattr(security_settings, "DEVELOPMENT_MODE", False)


@pytest.fixture
def trusted_hops(monkeypatch):
    monkeypatch.setattr(security_settings, "TRUSTED_PROXY_HOPS", 1)


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
    """Lista de emails de los usuarios que crea el test; se borran al terminar"""
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


@pytest.fixture
def outbox():
    """SMTP configurado que anota los correos entregados (el envío no espera ni falla)"""
    sent = []
    connection = MagicMock()
    connection.send_message.side_effect = sent.append
    smtp = MagicMock()
    smtp.return_value.__enter__.return_value = connection
    smtp.return_value.__exit__.return_value = False

    module = "app.utils.email_verification"
    with (
        patch(f"{module}.smtplib.SMTP", smtp),
        patch(f"{module}.SMTP_SERVER", "smtp.test.invalid"),
        patch(f"{module}.EMAIL_FROM", "noreply@example.com"),
        patch(f"{module}.SMTP_USER", None),
        patch(f"{module}.SMTP_PASS", None),
        patch(f"{module}.SMTP_USE_STARTTLS", False),
    ):
        yield sent


def _code_of(message) -> str:
    match = re.search(r"es: (\S+)", message.get_content())
    assert match, message.get_content()
    return match.group(1)


def _ip() -> str:
    raw = uuid.uuid4().bytes
    return f"10.{raw[0]}.{raw[1]}.{raw[2]}"


def _http(ip: str) -> TestClient:
    from main import app

    return TestClient(app, client=(ip, 50000))


def _unknown_email() -> str:
    return f"nobody_{uuid.uuid4().hex[:10]}@example.com"


def _make_user(db_session, created_emails, *, verified, deleted=False, otp=None, otp_minutes=10):
    """Usuario único por test; con `otp` guarda ese código (otp_minutes < 0: ya caducado)"""
    suffix = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = User(
        id=str(uuid.uuid4()),
        username=f"uni_{suffix}",
        email=f"uni_{suffix}@example.com",
        password_hash=PASSWORD_HASH,
        created_at=now,
        updated_at=now,
        is_verified=verified,
        is_deleted=deleted,
        failed_login_attempts=0,
    )
    db_session.add(user)
    db_session.commit()
    created_emails.append(user.email)

    if otp is not None:
        email_otp_crud.create_otp_orm(
            db_session, user_id=user.id, otp_code=otp, expires_in_minutes=otp_minutes
        )
    return {"id": str(user.id), "email": user.email, "username": user.username}


def _otp_row(db_session, user_id):
    db_session.expire_all()
    return db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()


# Cada caso devuelve (email, código) para verify-code / reset; todos deben fallar igual
def _case_unknown(db_session, created_emails):
    return _unknown_email(), OTP_CODE


def _case_deleted(db_session, created_emails):
    user = _make_user(db_session, created_emails, verified=False, deleted=True, otp=OTP_CODE)
    return user["email"], OTP_CODE


def _case_verified(db_session, created_emails):
    user = _make_user(db_session, created_emails, verified=True)
    return user["email"], OTP_CODE


def _case_wrong_code(db_session, created_emails):
    user = _make_user(db_session, created_emails, verified=False, otp=OTP_CODE)
    return user["email"], WRONG_CODE


def _case_no_otp(db_session, created_emails):
    user = _make_user(db_session, created_emails, verified=False)
    return user["email"], OTP_CODE


def _case_expired_otp(db_session, created_emails):
    user = _make_user(db_session, created_emails, verified=False, otp=OTP_CODE, otp_minutes=-5)
    return user["email"], OTP_CODE


CASES = {
    "unknown_email": _case_unknown,
    "deleted_account": _case_deleted,
    "already_verified": _case_verified,
    "wrong_code": _case_wrong_code,
    "no_otp": _case_no_otp,
    "expired_otp": _case_expired_otp,
}


def _verify(client, email, code):
    return client.post("/api/auth/verify-code", json={"email": email, "code": code})


def _reset(client, email, code):
    return client.post(
        "/api/auth/reset", json={"email": email, "code": code, "new_password": NEW_PASSWORD}
    )


# ============================================================================
# verify-code
# ============================================================================


@pytest.mark.parametrize("case", sorted(CASES))
def test_verify_code_failures_share_one_400(client, db_session, created_emails, case):
    email, code = CASES[case](db_session, created_emails)

    response = _verify(client, email, code)

    assert response.status_code == 400, response.text
    assert response.json() == VERIFY_FAILED
    assert "session" not in response.cookies


def test_verify_code_failures_are_indistinguishable(client, db_session, created_emails):
    seen = {}
    for name, build in CASES.items():
        email, code = build(db_session, created_emails)
        response = _verify(client, email, code)
        seen[name] = (response.status_code, json.dumps(response.json(), sort_keys=True))

    assert len(set(seen.values())) == 1, seen


def test_verify_code_keeps_the_real_reason_in_the_security_log(client, db_session, created_emails):
    reasons = {}
    for name in ("unknown_email", "already_verified", "wrong_code"):
        email, code = CASES[name](db_session, created_emails)
        with patch.object(SecurityLogger, "log_email_verification_attempt", new=AsyncMock()) as log:
            _verify(client, email, code)
        assert log.await_count == 1
        reasons[name] = log.await_args.kwargs["failure_reason"]

    assert reasons == {
        "unknown_email": "Usuario no encontrado",
        "already_verified": "Email ya verificado",
        "wrong_code": INVALID_CODE,
    }


# ============================================================================
# reset
# ============================================================================


@pytest.mark.parametrize("case", sorted(CASES))
def test_reset_failures_share_one_400(client, db_session, created_emails, case):
    email, code = CASES[case](db_session, created_emails)

    response = _reset(client, email, code)

    assert response.status_code == 400, response.text
    assert response.json() == RESET_FAILED


def test_reset_failures_are_indistinguishable(client, db_session, created_emails):
    seen = {}
    for name, build in CASES.items():
        email, code = build(db_session, created_emails)
        response = _reset(client, email, code)
        seen[name] = (response.status_code, json.dumps(response.json(), sort_keys=True))

    assert len(set(seen.values())) == 1, seen


def test_reset_keeps_the_real_reason_in_the_security_log(client, db_session, created_emails):
    reasons = {}
    for name in ("unknown_email", "wrong_code"):
        email, code = CASES[name](db_session, created_emails)
        with patch.object(SecurityLogger, "log_password_reset_attempt", new=AsyncMock()) as log:
            _reset(client, email, code)
        assert log.await_count == 1
        assert log.await_args.kwargs["stage"] == "reset"
        reasons[name] = log.await_args.kwargs["failure_reason"]

    assert reasons == {"unknown_email": "Usuario no encontrado", "wrong_code": INVALID_CODE}


def test_reset_success_body_is_unchanged(client, db_session, created_emails):
    user = _make_user(db_session, created_emails, verified=True, otp=OTP_CODE)

    response = _reset(client, user["email"], OTP_CODE)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "success": True,
        "message": "Contraseña actualizada exitosamente",
        "data": None,
    }


def test_log_password_reset_attempt_records_failure_reason_only_when_given():
    request = Request({"type": "http", "method": "POST", "path": "/api/auth/reset", "headers": []})

    async def _run(**kwargs):
        with patch.object(SecurityLogger, "log_event", new=AsyncMock()) as log_event:
            await SecurityLogger.log_password_reset_attempt(
                request, "a@example.com", False, None, stage="reset", **kwargs
            )
        return log_event.await_args.kwargs["details"]

    with_reason = asyncio.run(_run(failure_reason="Usuario no encontrado"))
    without_reason = asyncio.run(_run())

    assert with_reason["failure_reason"] == "Usuario no encontrado"
    assert "failure_reason" not in without_reason


# ============================================================================
# resend-code
# ============================================================================


def _resend(client, email):
    return client.post("/api/auth/resend-code", json={"email": email})


def test_resend_code_is_200_and_identical_whether_or_not_the_account_exists(
    client, db_session, created_emails, outbox
):
    unverified = _make_user(db_session, created_emails, verified=False)
    verified = _make_user(db_session, created_emails, verified=True)
    deleted = _make_user(db_session, created_emails, verified=False, deleted=True)
    emails = {
        "unverified": unverified["email"],
        "verified": verified["email"],
        "deleted": deleted["email"],
        "unknown": _unknown_email(),
    }

    responses = {name: _resend(client, email) for name, email in emails.items()}

    assert {name: r.status_code for name, r in responses.items()} == dict.fromkeys(emails, 200)
    assert {name: r.json() for name, r in responses.items()} == dict.fromkeys(emails, RESEND_OK)


def test_resend_code_only_delivers_to_unverified_accounts(
    client, db_session, created_emails, outbox
):
    unverified = _make_user(db_session, created_emails, verified=False)
    verified = _make_user(db_session, created_emails, verified=True)
    deleted = _make_user(db_session, created_emails, verified=False, deleted=True)

    for email in (verified["email"], deleted["email"], _unknown_email()):
        _resend(client, email)
    assert outbox == []
    assert _otp_row(db_session, verified["id"]) is None
    assert _otp_row(db_session, deleted["id"]) is None

    _resend(client, unverified["email"])

    assert len(outbox) == 1
    assert outbox[0]["To"] == unverified["email"]
    assert _otp_row(db_session, unverified["id"]) is not None


def test_resend_code_is_no_longer_a_shortcut_to_a_reset_code(
    client, db_session, created_emails, outbox
):
    """Con /forgot, el reenvío de un usuario verificado no emite el OTP que serviría al reset"""
    verified = _make_user(db_session, created_emails, verified=True)

    _resend(client, verified["email"])

    assert outbox == []
    assert _otp_row(db_session, verified["id"]) is None


def test_resend_code_keeps_the_real_reason_in_the_security_log(
    client, db_session, created_emails, outbox
):
    verified = _make_user(db_session, created_emails, verified=True)
    unverified = _make_user(db_session, created_emails, verified=False)
    seen = {}

    for name, email in (
        ("unknown", _unknown_email()),
        ("verified", verified["email"]),
        ("unverified", unverified["email"]),
    ):
        with patch.object(SecurityLogger, "log_event", new=AsyncMock()) as log:
            _resend(client, email)
        events = [c.kwargs for c in log.await_args_list]
        seen[name] = [
            (e["event_type"], e["details"]["reason"])
            for e in events
            if e["event_type"] == "resend_code_ignored"
        ]

    assert seen == {
        "unknown": [("resend_code_ignored", "user_not_found")],
        "verified": [("resend_code_ignored", "account_already_verified")],
        "unverified": [],
    }


def test_resend_code_for_an_unverified_account_still_issues_a_working_code(
    client, db_session, created_emails, outbox
):
    unverified = _make_user(db_session, created_emails, verified=False)

    _resend(client, unverified["email"])
    code = _code_of(outbox[0])
    response = _verify(client, unverified["email"], code)

    assert response.status_code == 200, response.text


# ============================================================================
# forgot
# ============================================================================


def _forgot(client, email):
    return client.post("/api/auth/forgot", json={"email": email})


def test_forgot_is_200_and_identical_whether_or_not_the_account_exists(
    client, db_session, created_emails, outbox
):
    verified = _make_user(db_session, created_emails, verified=True)
    unverified = _make_user(db_session, created_emails, verified=False)
    deleted = _make_user(db_session, created_emails, verified=True, deleted=True)
    emails = {
        "verified": verified["email"],
        "unverified": unverified["email"],
        "deleted": deleted["email"],
        "unknown": _unknown_email(),
    }

    responses = {name: _forgot(client, email) for name, email in emails.items()}

    assert {name: r.status_code for name, r in responses.items()} == dict.fromkeys(emails, 200)
    assert {name: r.json() for name, r in responses.items()} == dict.fromkeys(emails, FORGOT_OK)


def test_forgot_only_delivers_to_verified_accounts(client, db_session, created_emails, outbox):
    verified = _make_user(db_session, created_emails, verified=True)
    unverified = _make_user(db_session, created_emails, verified=False)
    deleted = _make_user(db_session, created_emails, verified=True, deleted=True)

    for email in (unverified["email"], deleted["email"], _unknown_email()):
        _forgot(client, email)
    assert outbox == []
    assert _otp_row(db_session, unverified["id"]) is None
    assert _otp_row(db_session, deleted["id"]) is None

    _forgot(client, verified["email"])

    assert len(outbox) == 1
    assert outbox[0]["To"] == verified["email"]
    assert _otp_row(db_session, verified["id"]) is not None


def test_forgot_response_never_contains_the_code(client, db_session, created_emails, outbox):
    verified = _make_user(db_session, created_emails, verified=True)

    response = _forgot(client, verified["email"])

    assert _code_of(outbox[0]) not in response.text


def test_forgot_then_reset_changes_the_password(client, db_session, created_emails, outbox):
    verified = _make_user(db_session, created_emails, verified=True)

    _forgot(client, verified["email"])
    reset = _reset(client, verified["email"], _code_of(outbox[0]))
    login = client.post(
        "/api/auth/login", json={"identifier": verified["email"], "password": NEW_PASSWORD}
    )

    assert reset.status_code == 200, reset.text
    assert login.status_code == 200, login.text


def test_forgot_keeps_the_real_reason_in_the_security_log(client, db_session, created_emails):
    verified = _make_user(db_session, created_emails, verified=True)
    unverified = _make_user(db_session, created_emails, verified=False)
    seen = {}

    for name, email in (
        ("verified", verified["email"]),
        ("unverified", unverified["email"]),
        ("unknown", _unknown_email()),
    ):
        with patch.object(SecurityLogger, "log_password_reset_attempt", new=AsyncMock()) as log:
            _forgot(client, email)
        assert log.await_count == 1
        assert log.await_args.kwargs["stage"] == "request"
        seen[name] = (log.await_args.args[2], log.await_args.kwargs.get("failure_reason"))

    assert seen == {
        "verified": (True, None),
        "unverified": (False, "Cuenta sin verificar"),
        "unknown": (False, "Usuario no encontrado"),
    }


def test_forgot_is_limited_per_email_whether_or_not_the_account_exists(
    client, db_session, created_emails, production_mode, trusted_hops
):
    """El 429 por cuenta es el único cambio observable y no depende de que la cuenta exista"""
    proxy = _http(_ip())
    verified = _make_user(db_session, created_emails, verified=True)
    limit = security_settings.RATE_LIMIT_FORGOT_ATTEMPTS

    for email in (verified["email"], _unknown_email()):
        for _ in range(limit):
            response = proxy.post(
                "/api/auth/forgot", json={"email": email}, headers={"X-Forwarded-For": _ip()}
            )
            assert response.status_code == 200, response.text
        blocked = proxy.post(
            "/api/auth/forgot", json={"email": email}, headers={"X-Forwarded-For": _ip()}
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) > 0


def test_forgot_is_limited_per_ip(client, production_mode):
    http = _http(_ip())
    limit = security_settings.RATE_LIMIT_FORGOT_ATTEMPTS

    for _ in range(limit):
        assert _forgot(http, _unknown_email()).status_code == 200
    blocked = _forgot(http, _unknown_email())

    assert blocked.status_code == 429


# ============================================================================
# Tiempo: el camino «sin cuenta» gasta el mismo hash (mejor esfuerzo)
# ============================================================================


def test_simulate_otp_check_runs_one_bcrypt_comparison():
    with patch.object(email_otp_crud.bcrypt, "checkpw", return_value=False) as checkpw:
        email_otp_crud.simulate_otp_check()

    assert checkpw.call_count == 1


@pytest.mark.parametrize("path", ["/api/auth/verify-code", "/api/auth/reset"])
def test_unknown_account_spends_an_otp_check_in_verify_and_reset(client, path):
    body = {"email": _unknown_email(), "code": OTP_CODE}
    if path.endswith("reset"):
        body["new_password"] = NEW_PASSWORD

    with patch.object(email_otp_crud, "simulate_otp_check") as spent:
        response = client.post(path, json=body)

    assert response.status_code == 400
    assert spent.call_count == 1


@pytest.mark.parametrize("path", ["/api/auth/resend-code", "/api/auth/forgot"])
def test_unknown_account_spends_an_otp_check_in_resend_and_forgot(client, path):
    with patch.object(email_otp_crud, "simulate_otp_check") as spent:
        response = client.post(path, json={"email": _unknown_email()})

    assert response.status_code == 200
    assert spent.call_count == 1


def test_the_real_paths_do_not_add_the_simulated_check(client, db_session, created_emails, outbox):
    unverified = _make_user(db_session, created_emails, verified=False)
    verified = _make_user(db_session, created_emails, verified=True)

    with patch.object(email_otp_crud, "simulate_otp_check") as spent:
        _resend(client, unverified["email"])
        _forgot(client, verified["email"])

    assert spent.call_count == 0


def test_verify_otp_without_a_stored_code_spends_an_otp_check(db_session, created_emails):
    """Sin OTP o con el OTP caducado no hay bcrypt real: se gasta el simulado"""
    no_otp = _make_user(db_session, created_emails, verified=False)
    expired = _make_user(db_session, created_emails, verified=False, otp=OTP_CODE, otp_minutes=-5)

    with patch.object(email_otp_crud, "simulate_otp_check") as spent:
        assert email_otp_crud.verify_otp_orm(db_session, no_otp["id"], OTP_CODE) is False
        assert email_otp_crud.verify_otp_orm(db_session, expired["id"], OTP_CODE) is False

    assert spent.call_count == 2


# ============================================================================
# register no cambia (riesgo residual documentado)
# ============================================================================


def test_register_still_answers_409_for_an_existing_email(client, db_session, created_emails):
    existing = _make_user(db_session, created_emails, verified=True)

    response = client.post(
        "/api/auth/register",
        json={
            "username": f"other_{uuid.uuid4().hex[:8]}",
            "email": existing["email"],
            "password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 409
