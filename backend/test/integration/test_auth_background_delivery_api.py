"""
Tests de integración: el envío del código de verificación y el trabajo pesado de los endpoints
de autenticación no bloquean el event loop (hallazgo 1 de la deuda de autenticación).

- register y resend-code responden sin esperar al SMTP: el OTP se crea en la petición y el
  correo se entrega después (BackgroundTasks), sin sesión de BD.
- El cuerpo de la respuesta no contiene nunca el código.
- Los servicios síncronos (bcrypt, consultas) de login, register, verify-code y reset se
  ejecutan en el threadpool, no en el hilo del event loop.

Las peticiones de tiempo se hacen directamente contra la app ASGI (no con TestClient, que
espera a las tareas de fondo antes de devolver la respuesta) para medir cuándo sale la
respuesta y cuándo empieza el envío.
"""

import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app.crud import email_otp_crud
from app.models.orm import EmailOTP, User
from app.models.orm.session import UserSession
from app.services.auth_service import AuthenticationError, AuthService, pwd_context

PASSWORD = "Test123!@#"
# Duración del envío SMTP simulado. El registro hace dos hashes bcrypt (contraseña y OTP, ~0,4 s
# cada uno en el contenedor de tests): la respuesta debe salir antes de que el SMTP termine, no
# en menos de un segundo absoluto (eso se mide en vivo).
SMTP_DELAY_SECONDS = 3.0


# ============================================================================
# Fixtures y helpers
# ============================================================================


@pytest.fixture(autouse=True)
def clean_auth_counters(db_session):
    """
    Contadores de /api/auth fuera antes y después (la BD de test no los deshace).

    Sin esto, los registros de otros ficheros del mismo worker agotan el límite por IP y
    estos tests reciben 429 según cómo reparta xdist los ficheros.
    """

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


def _new_identity():
    suffix = uuid.uuid4().hex[:8]
    return f"bg_{suffix}", f"bg_{suffix}@example.com"


@pytest.fixture
def unverified_user(db_session, created_emails):
    """Usuario no verificado y único por test"""
    username, email = _new_identity()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = User(
        id=str(uuid.uuid4()),
        username=username,
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
    return {"id": str(user.id), "username": username, "email": email}


@pytest.fixture
def slow_smtp():
    """
    SMTP configurado y lento: send_message tarda SMTP_DELAY_SECONDS.

    Devuelve un diccionario donde se anota cuándo empezó y terminó el envío y el mensaje.
    """
    record = {"started": None, "finished": None, "message": None, "calls": 0}

    def send_message(message):
        record["calls"] += 1
        record["started"] = time.monotonic()
        record["message"] = message
        time.sleep(SMTP_DELAY_SECONDS)
        record["finished"] = time.monotonic()

    connection = MagicMock()
    connection.send_message.side_effect = send_message
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
        yield record


def _sent_code(record):
    """Código que viajó en el correo simulado"""
    assert record["message"] is not None, "no se envió ningún correo"
    match = re.search(r"es: (\S+)", record["message"].get_content())
    assert match, record["message"].get_content()
    return match.group(1)


async def _call(method, path, payload=None):
    """
    Una petición directa a la app ASGI, con las marcas de tiempo de la respuesta.

    `sent_at` es el instante en que sale el último trozo de la respuesta; `finished`, cuando la
    app termina (después de las tareas de fondo).
    """
    from main import app

    body = json.dumps(payload).encode() if payload is not None else b""
    headers = [(b"host", b"testserver"), (b"user-agent", b"pytest-asgi")]
    if payload is not None:
        headers += [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    complete = asyncio.Event()
    state = {"status": None, "body": b"", "sent_at": None}
    request_sent = False

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await complete.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            state["status"] = message["status"]
        elif message["type"] == "http.response.body":
            state["body"] += message.get("body", b"")
            if not message.get("more_body", False):
                state["sent_at"] = time.monotonic()
                complete.set()

    started = time.monotonic()
    await app(scope, receive, send)
    return SimpleNamespace(
        status=state["status"],
        text=state["body"].decode(),
        json=lambda: json.loads(state["body"]),
        started=started,
        sent_at=state["sent_at"],
        finished=time.monotonic(),
    )


def _register_payload(created_emails):
    username, email = _new_identity()
    created_emails.append(email)
    return {
        "username": username,
        "email": email,
        "password": PASSWORD,
        "confirm_password": PASSWORD,
    }


# ============================================================================
# register: el correo se entrega después de responder
# ============================================================================


def test_register_responds_before_the_slow_smtp_send_starts(client, slow_smtp, created_emails):
    payload = _register_payload(created_emails)

    response = asyncio.run(_call("POST", "/api/auth/register", payload))

    assert response.status == 201, response.text
    # La respuesta no espera al SMTP...
    assert response.sent_at - response.started < SMTP_DELAY_SECONDS
    # ...sale mientras el envío sigue en curso (el correo se entrega después)...
    assert slow_smtp["calls"] == 1
    assert response.sent_at < slow_smtp["finished"] - SMTP_DELAY_SECONDS / 2
    # ...y la app no termina hasta que la tarea de fondo ha acabado
    assert slow_smtp["finished"] <= response.finished


def test_register_response_body_never_contains_the_code(client, slow_smtp, created_emails):
    payload = _register_payload(created_emails)

    response = asyncio.run(_call("POST", "/api/auth/register", payload))

    assert response.status == 201, response.text
    code = _sent_code(slow_smtp)
    assert code not in response.text
    # El contrato de la respuesta no cambia
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Usuario registrado exitosamente"
    assert set(body["data"]) == {"user_id", "username", "email"}
    assert body["data"]["email"] == payload["email"]


def test_register_delivers_the_code_that_was_stored(client, slow_smtp, created_emails):
    payload = _register_payload(created_emails)

    response = asyncio.run(_call("POST", "/api/auth/register", payload))
    assert response.status == 201, response.text

    verified = client.post(
        "/api/auth/verify-code", json={"email": payload["email"], "code": _sent_code(slow_smtp)}
    )
    assert verified.status_code == 200, verified.text


def test_event_loop_stays_responsive_while_register_sends_slowly(client, slow_smtp, created_emails):
    """Equivalente de la puerta en vivo: el loop sigue atendiendo mientras el SMTP está colgado"""
    payload = _register_payload(created_emails)
    gaps = []

    async def heartbeat():
        # Si algo bloquea el loop, el temporizador llega tarde y el hueco crece
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.02)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    async def scenario():
        beat = asyncio.create_task(heartbeat())
        await asyncio.sleep(0.1)
        register = asyncio.create_task(_call("POST", "/api/auth/register", payload))
        health_latencies = []
        while not register.done():
            started = time.monotonic()
            health = await _call("GET", "/health")
            health_latencies.append(time.monotonic() - started)
            assert health.status == 200
            await asyncio.sleep(0.05)
        response = await register
        beat.cancel()
        return response, health_latencies

    response, health_latencies = asyncio.run(scenario())

    assert response.status == 201, response.text
    assert max(gaps) < 1.0
    assert max(health_latencies) < 1.0
    # El latido y el SMTP lento se han ejercido de verdad (la prueba no es vacía)
    assert slow_smtp["calls"] == 1
    assert len(gaps) > 10


# ============================================================================
# resend-code
# ============================================================================


def test_resend_code_responds_before_the_slow_smtp_send_starts(client, slow_smtp, unverified_user):
    response = asyncio.run(
        _call("POST", "/api/auth/resend-code", {"email": unverified_user["email"]})
    )

    assert response.status == 200, response.text
    assert response.sent_at - response.started < SMTP_DELAY_SECONDS
    assert slow_smtp["calls"] == 1
    assert response.sent_at < slow_smtp["finished"] - SMTP_DELAY_SECONDS / 2


def test_resend_code_response_body_never_contains_the_code(client, slow_smtp, unverified_user):
    response = asyncio.run(
        _call("POST", "/api/auth/resend-code", {"email": unverified_user["email"]})
    )

    assert response.status == 200, response.text
    assert _sent_code(slow_smtp) not in response.text
    assert response.json() == {
        "success": True,
        "message": "Código reenviado correctamente",
        "data": None,
    }


# ============================================================================
# AuthService.create_user: el servicio no depende de FastAPI y no devuelve el código
# ============================================================================


def test_create_user_hands_the_code_to_deliver_and_never_returns_it(db_session, created_emails):
    username, email = _new_identity()
    created_emails.append(email)
    delivered = []

    result = AuthService(db_session).create_user(
        username, email, PASSWORD, deliver=lambda to, code: delivered.append((to, code))
    )

    assert len(delivered) == 1
    to_email, code = delivered[0]
    assert to_email == email
    assert len(code) == 8
    assert set(result) == {"user_id", "username", "email"}
    assert code not in json.dumps(result)
    # El código entregado es el que quedó guardado en BD
    assert email_otp_crud.verify_otp_orm(db_session, result["user_id"], code) is True


# ============================================================================
# Servicios síncronos en el threadpool
# ============================================================================


def _on_event_loop() -> bool:
    """True si el código corre en el hilo de un event loop (bloquearía las demás peticiones)"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


_HEAVY_ENDPOINTS = [
    (
        "create_user",
        "/api/auth/register",
        {
            "username": "bg_loop_user",
            "email": "bg_loop_user@example.com",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
        },
    ),
    (
        "authenticate_user",
        "/api/auth/login",
        {"identifier": "bg_loop_user", "password": PASSWORD},
    ),
    (
        "verify_email_code",
        "/api/auth/verify-code",
        {"email": "bg_loop_user@example.com", "code": "ABCDEFGH"},
    ),
    (
        "reset_password",
        "/api/auth/reset",
        {"email": "bg_loop_user@example.com", "code": "ABCDEFGH", "new_password": PASSWORD},
    ),
]


@pytest.mark.parametrize(
    "method_name,path,payload", _HEAVY_ENDPOINTS, ids=[e[0] for e in _HEAVY_ENDPOINTS]
)
def test_heavy_auth_service_calls_run_outside_the_event_loop(
    client, monkeypatch, method_name, path, payload
):
    seen = []

    def spy(self, *args, **kwargs):
        seen.append(_on_event_loop())
        raise AuthenticationError("detenido por el test")

    monkeypatch.setattr(AuthService, method_name, spy)

    client.post(path, json=payload)

    assert seen == [False]
