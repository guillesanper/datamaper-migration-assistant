"""
Tests de integración: POST /api/auth/register responde igual exista o no la cuenta (R3 de los
riesgos abiertos de la deuda de autenticación: riesgos 4 y 5).

- Email nuevo, de una cuenta verificada, de una sin verificar o de una borrada: 201 con las
  mismas claves y el mismo mensaje (no se puede preguntar «¿tiene cuenta X?»).
- Verificada: no se crea nada, no se emite OTP y se encola un correo «ya tienes una cuenta»
  (sin código). Sin verificar: se reemite el código (el anterior deja de valer) sin cambiar la
  contraseña ni el username guardados; así se repara también la cuenta «sin código».
  Borrada: no se crea ni se envía nada.
- Un username ocupado (por una cuenta viva o borrada) da 409 `username_taken` con
  independencia de que el email exista: así tampoco se enumeran emails eligiendo el username.
- Una carrera (IntegrityError en el INSERT) acaba en la misma respuesta que el camino lento.
- El motivo real va al log de seguridad; el user_id aleatorio del 201 uniforme nunca se registra.

Los contadores van a la BD de test sin rollback: cada test borra los de /api/auth al terminar.
"""

import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from app.crud import email_otp_crud
from app.models.orm import EmailOTP, User
from app.models.orm.session import UserSession
from app.services.auth_service import AuthService, pwd_context
from app.utils.security_logger import SecurityLogger

PASSWORD = "Test123!@#"  # contraseña guardada de las cuentas que ya existen
NEW_PASSWORD = "Str0ng!Passw0rd"  # la que envía quien intenta registrarse
OTP_CODE = "ABCD1234"
REGISTER_OK_MESSAGE = "Usuario registrado exitosamente"
# Un solo hash por proceso: bcrypt cuesta ~0,4 s y aquí solo importa que sea reconocible
PASSWORD_HASH = pwd_context.hash(PASSWORD)
SMTP_DELAY_SECONDS = 3.0


# ============================================================================
# Fixtures y helpers
# ============================================================================


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


def _smtp_mock(on_send):
    connection = MagicMock()
    connection.send_message.side_effect = on_send
    smtp = MagicMock()
    smtp.return_value.__enter__.return_value = connection
    smtp.return_value.__exit__.return_value = False
    return smtp


def _smtp_config(smtp):
    module = "app.utils.email_verification"
    return (
        patch(f"{module}.smtplib.SMTP", smtp),
        patch(f"{module}.SMTP_SERVER", "smtp.test.invalid"),
        patch(f"{module}.EMAIL_FROM", "noreply@example.com"),
        patch(f"{module}.SMTP_USER", None),
        patch(f"{module}.SMTP_PASS", None),
        patch(f"{module}.SMTP_USE_STARTTLS", False),
    )


@pytest.fixture
def outbox():
    """SMTP configurado que anota los correos entregados (el envío no espera ni falla)"""
    sent = []
    patches = _smtp_config(_smtp_mock(sent.append))
    for p in patches:
        p.start()
    yield sent
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def slow_smtp():
    """SMTP configurado y lento: send_message tarda SMTP_DELAY_SECONDS"""
    record = {"started": None, "finished": None, "calls": 0}

    def send_message(message):
        record["calls"] += 1
        record["started"] = time.monotonic()
        time.sleep(SMTP_DELAY_SECONDS)
        record["finished"] = time.monotonic()

    patches = _smtp_config(_smtp_mock(send_message))
    for p in patches:
        p.start()
    yield record
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def user_inserts():
    """Sentencias `INSERT INTO users` que llegan a la BD durante el test"""
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO USERS"):
            statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    yield statements
    event.remove(Engine, "before_cursor_execute", record)


def _code_of(message) -> str:
    match = re.search(r"es: (\S+)", message.get_content())
    assert match, message.get_content()
    return match.group(1)


def _new_identity():
    suffix = uuid.uuid4().hex[:10]
    return f"reg_{suffix}", f"reg_{suffix}@example.com"


def _make_user(db_session, created_emails, *, verified, deleted=False, otp=None):
    """Usuario único por test; con `otp` guarda ese código"""
    username, email = _new_identity()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        email=email,
        password_hash=PASSWORD_HASH,
        created_at=now,
        updated_at=now,
        is_verified=verified,
        is_deleted=deleted,
        failed_login_attempts=0,
    )
    db_session.add(user)
    db_session.commit()
    created_emails.append(email)

    if otp is not None:
        email_otp_crud.create_otp_orm(db_session, user_id=user.id, otp_code=otp)
    return {"id": str(user.id), "email": email, "username": username}


def _register(client, username, email, password=NEW_PASSWORD):
    return client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )


def _stored(db_session, email):
    """Fila de users por email (incluidas las borradas), sin caché de la sesión"""
    db_session.expire_all()
    return db_session.query(User).filter(User.email == email).first()


def _count_users(db_session, *, username=None, email=None):
    db_session.expire_all()
    query = db_session.query(User)
    if username is not None:
        query = query.filter(User.username == username)
    if email is not None:
        query = query.filter(User.email == email)
    return query.count()


def _otp_row(db_session, user_id):
    db_session.expire_all()
    return db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()


def _subjects(outbox):
    return [message["Subject"] for message in outbox]


def _recipients(outbox):
    return [message["To"] for message in outbox]


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


# ============================================================================
# Contrato de un alta nueva: no cambia
# ============================================================================


def test_new_account_keeps_the_201_contract(client, db_session, created_emails, outbox):
    username, email = _new_identity()
    created_emails.append(email)

    response = _register(client, username, email)

    assert response.status_code == 201, response.text
    body = response.json()
    stored = _stored(db_session, email)
    assert body == {
        "success": True,
        "message": REGISTER_OK_MESSAGE,
        "data": {"user_id": str(stored.id), "username": username, "email": email},
    }
    assert stored.is_verified is False
    assert pwd_context.verify(NEW_PASSWORD, stored.password_hash)


def test_new_account_gets_exactly_one_code_that_verifies_it(
    client, db_session, created_emails, outbox
):
    username, email = _new_identity()
    created_emails.append(email)

    response = _register(client, username, email)

    assert _subjects(outbox) == ["Tu código de verificación"]
    assert _recipients(outbox) == [email]
    code = _code_of(outbox[0])
    assert code not in response.text
    verified = client.post("/api/auth/verify-code", json={"email": email, "code": code})
    assert verified.status_code == 200, verified.text


# ============================================================================
# Respuesta uniforme: email nuevo, verificado, sin verificar y borrado
# ============================================================================


def _shape(response):
    """Todo lo que un cliente puede observar de la respuesta salvo los valores propios"""
    body = response.json()
    return {
        "status": response.status_code,
        "keys": sorted(body),
        "data_keys": sorted(body["data"]),
        "success": body["success"],
        "message": body["message"],
        "set_cookie": response.headers.get("set-cookie"),
    }


def test_new_verified_unverified_and_deleted_emails_get_the_same_201(
    client, db_session, created_emails, outbox
):
    verified = _make_user(db_session, created_emails, verified=True)
    unverified = _make_user(db_session, created_emails, verified=False)
    deleted = _make_user(db_session, created_emails, verified=False, deleted=True)
    fresh_username, fresh_email = _new_identity()
    created_emails.append(fresh_email)
    cases = {
        "new": fresh_email,
        "verified": verified["email"],
        "unverified": unverified["email"],
        "deleted": deleted["email"],
    }

    responses = {}
    for name, email in cases.items():
        username = fresh_username if name == "new" else _new_identity()[0]
        responses[name] = (username, _register(client, username, email))

    shapes = {name: _shape(response) for name, (_, response) in responses.items()}
    assert shapes["new"]["status"] == 201
    assert shapes["new"]["message"] == REGISTER_OK_MESSAGE
    assert shapes["new"]["set_cookie"] is None
    for name, shape in shapes.items():
        assert shape == shapes["new"], f"{name} se distingue del alta nueva"

    real_ids = {
        "verified": verified["id"],
        "unverified": unverified["id"],
        "deleted": deleted["id"],
    }
    for name, real_id in real_ids.items():
        username, response = responses[name]
        data = response.json()["data"]
        # Los datos son los de la petición y el id no es el de la cuenta real
        assert data["username"] == username
        assert data["email"] == cases[name]
        assert _is_uuid(data["user_id"])
        assert data["user_id"] != real_id
        assert real_id not in response.text


def test_the_uniform_201_is_not_a_stored_account(client, db_session, created_emails, outbox):
    """El user_id del 201 uniforme es aleatorio: no corresponde a ninguna fila de users"""
    verified = _make_user(db_session, created_emails, verified=True)
    username = _new_identity()[0]

    data = _register(client, username, verified["email"]).json()["data"]

    db_session.expire_all()
    assert db_session.query(User).filter(User.id == data["user_id"]).count() == 0
    assert _count_users(db_session, username=username) == 0
    assert _count_users(db_session, email=verified["email"]) == 1


def test_a_repeated_uniform_request_returns_a_different_user_id(
    client, db_session, created_emails, outbox
):
    verified = _make_user(db_session, created_emails, verified=True)

    first = _register(client, _new_identity()[0], verified["email"]).json()["data"]["user_id"]
    second = _register(client, _new_identity()[0], verified["email"]).json()["data"]["user_id"]

    assert first != second


def test_email_case_and_spaces_do_not_hide_an_existing_account(
    client, db_session, created_emails, outbox
):
    verified = _make_user(db_session, created_emails, verified=True)
    username = _new_identity()[0]

    response = _register(client, username, verified["email"].upper())

    assert response.status_code == 201, response.text
    assert _count_users(db_session, username=username) == 0
    assert _subjects(outbox) == ["Ya tienes una cuenta en DataMap Assistant"]


# ============================================================================
# Email de una cuenta verificada
# ============================================================================


def test_verified_account_gets_a_notice_and_no_code(client, db_session, created_emails, outbox):
    verified = _make_user(db_session, created_emails, verified=True)

    response = _register(client, _new_identity()[0], verified["email"])

    assert response.status_code == 201, response.text
    assert _subjects(outbox) == ["Ya tienes una cuenta en DataMap Assistant"]
    assert _recipients(outbox) == [verified["email"]]
    # El aviso no lleva código, ni enlaces con secretos
    content = outbox[0].get_content()
    assert not re.search(r"\b[A-Z0-9]{8}\b", content)
    assert "http" not in content
    # No se emite ningún OTP para la cuenta ni se toca la cuenta
    assert _otp_row(db_session, verified["id"]) is None
    stored = _stored(db_session, verified["email"])
    assert stored.password_hash == PASSWORD_HASH
    assert stored.username == verified["username"]
    assert stored.is_verified is True


def test_verified_account_is_not_given_a_session_or_cookie(
    client, db_session, created_emails, outbox
):
    verified = _make_user(db_session, created_emails, verified=True)

    response = _register(client, _new_identity()[0], verified["email"])

    assert "set-cookie" not in response.headers
    db_session.expire_all()
    assert db_session.query(UserSession).filter(UserSession.user_id == verified["id"]).count() == 0


# ============================================================================
# Email de una cuenta sin verificar: se reemite el código
# ============================================================================


def test_unverified_account_gets_a_new_code_and_the_old_one_stops_working(
    client, db_session, created_emails, outbox
):
    account = _make_user(db_session, created_emails, verified=False, otp=OTP_CODE)
    db_session.query(EmailOTP).filter(EmailOTP.user_id == account["id"]).update(
        {"failed_attempts": 3}
    )
    db_session.commit()

    response = _register(client, _new_identity()[0], account["email"])

    assert response.status_code == 201, response.text
    assert _subjects(outbox) == ["Tu código de verificación"]
    assert _recipients(outbox) == [account["email"]]
    new_code = _code_of(outbox[0])
    assert new_code != OTP_CODE
    assert new_code not in response.text
    assert _otp_row(db_session, account["id"]).failed_attempts == 0
    assert email_otp_crud.verify_otp_orm(db_session, account["id"], OTP_CODE) is False
    assert email_otp_crud.verify_otp_orm(db_session, account["id"], new_code) is True


def test_unverified_account_keeps_its_stored_password_and_username(
    client, db_session, created_emails, outbox
):
    """Quien reintenta con otros datos no cambia la contraseña de una cuenta aún sin verificar"""
    account = _make_user(db_session, created_emails, verified=False)

    _register(client, _new_identity()[0], account["email"], password=NEW_PASSWORD)

    stored = _stored(db_session, account["email"])
    assert stored.password_hash == PASSWORD_HASH
    assert stored.username == account["username"]
    assert stored.is_verified is False
    assert _count_users(db_session, email=account["email"]) == 1


def test_the_new_code_verifies_the_unverified_account(client, db_session, created_emails, outbox):
    account = _make_user(db_session, created_emails, verified=False, otp=OTP_CODE)

    _register(client, _new_identity()[0], account["email"])
    verified = client.post(
        "/api/auth/verify-code", json={"email": account["email"], "code": _code_of(outbox[0])}
    )

    assert verified.status_code == 200, verified.text
    assert _stored(db_session, account["email"]).is_verified is True


def test_account_left_without_a_code_is_repaired_by_registering_again(
    client, db_session, created_emails, outbox
):
    """Riesgo 5: si el OTP no llegó a guardarse tras crear la cuenta, el reintento lo crea"""
    account = _make_user(db_session, created_emails, verified=False, otp=None)
    assert _otp_row(db_session, account["id"]) is None

    response = _register(client, _new_identity()[0], account["email"])

    assert response.status_code == 201, response.text
    assert _otp_row(db_session, account["id"]) is not None
    verified = client.post(
        "/api/auth/verify-code", json={"email": account["email"], "code": _code_of(outbox[0])}
    )
    assert verified.status_code == 200, verified.text


def test_same_username_and_email_of_an_unverified_account_reissues_the_code(
    client, db_session, created_emails, outbox
):
    """Reintentar con los mismos datos (lo normal tras perder el correo) reenvía el código"""
    account = _make_user(db_session, created_emails, verified=False)

    response = _register(client, account["username"], account["email"])

    assert response.status_code == 201, response.text
    assert _subjects(outbox) == ["Tu código de verificación"]


def test_same_username_and_email_of_a_verified_account_gets_the_notice(
    client, db_session, created_emails, outbox
):
    account = _make_user(db_session, created_emails, verified=True)

    response = _register(client, account["username"], account["email"])

    assert response.status_code == 201, response.text
    assert _subjects(outbox) == ["Ya tienes una cuenta en DataMap Assistant"]


# ============================================================================
# Email de una cuenta borrada
# ============================================================================


def test_deleted_account_email_creates_and_sends_nothing(
    client, db_session, created_emails, outbox
):
    """
    Los índices únicos cubren las filas borradas: el email no puede volver a registrarse. Se
    responde igual (201) sin intentar el INSERT y sin correo: la cuenta ya no existe.
    """
    deleted = _make_user(db_session, created_emails, verified=False, deleted=True)
    username = _new_identity()[0]

    response = _register(client, username, deleted["email"])

    assert response.status_code == 201, response.text
    assert outbox == []
    assert _count_users(db_session, username=username) == 0
    assert _count_users(db_session, email=deleted["email"]) == 1
    assert _otp_row(db_session, deleted["id"]) is None


@pytest.mark.parametrize("kind", ["verified", "unverified", "deleted"])
def test_existing_email_never_reaches_the_insert(
    kind, client, db_session, created_emails, outbox, user_inserts
):
    """La consulta previa evita el INSERT (no se apoya en que la restricción única lo rechace)"""
    account = _make_user(
        db_session, created_emails, verified=(kind == "verified"), deleted=(kind == "deleted")
    )
    user_inserts.clear()  # _make_user inserta con la misma conexión

    response = _register(client, _new_identity()[0], account["email"])

    assert response.status_code == 201, response.text
    assert user_inserts == []


def test_a_taken_username_never_reaches_the_insert(
    client, db_session, created_emails, outbox, user_inserts
):
    owner = _make_user(db_session, created_emails, verified=True, deleted=True)
    user_inserts.clear()

    response = _register(client, owner["username"], _new_identity()[1])

    assert response.status_code == 409, response.text
    assert user_inserts == []


# ============================================================================
# Username ocupado: 409 con independencia del email
# ============================================================================


def test_taken_username_with_a_new_email_answers_409(client, db_session, created_emails, outbox):
    owner = _make_user(db_session, created_emails, verified=True)
    email = _new_identity()[1]
    created_emails.append(email)

    response = _register(client, owner["username"], email)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "username_taken"
    assert owner["email"] not in response.text
    assert outbox == []
    assert _count_users(db_session, email=email) == 0


@pytest.mark.parametrize("other", ["verified", "unverified", "deleted"])
@pytest.mark.parametrize("owner_deleted", [False, True], ids=["live_owner", "deleted_owner"])
def test_taken_username_answers_the_same_409_whether_or_not_the_email_exists(
    other, owner_deleted, client, db_session, created_emails, outbox
):
    """
    Trampa A: con el username de OTRA cuenta, el email no puede decidir entre 409 y 201, o
    quien conozca un username enumeraría emails.
    """
    owner = _make_user(db_session, created_emails, verified=True, deleted=owner_deleted)
    existing = _make_user(
        db_session,
        created_emails,
        verified=(other == "verified"),
        deleted=(other == "deleted"),
        otp=OTP_CODE if other == "unverified" else None,
    )
    unknown_email = _new_identity()[1]
    created_emails.append(unknown_email)
    otp_before = _otp_row(db_session, existing["id"])
    otp_hash_before = otp_before.otp_code if otp_before else None

    with_unknown = _register(client, owner["username"], unknown_email)
    with_existing = _register(client, owner["username"], existing["email"])

    assert with_unknown.status_code == 409, with_unknown.text
    assert with_existing.status_code == 409, with_existing.text
    assert with_existing.json() == with_unknown.json()
    # Y no se hace nada con la cuenta del email: ni aviso ni código nuevo
    assert outbox == []
    otp_after = _otp_row(db_session, existing["id"])
    assert (otp_after.otp_code if otp_after else None) == otp_hash_before


def test_free_username_with_an_existing_email_is_always_201(
    client, db_session, created_emails, outbox
):
    """El otro lado de la trampa A: con un username libre, el email existente da 201 uniforme"""
    verified = _make_user(db_session, created_emails, verified=True)
    fresh_username, fresh_email = _new_identity()
    created_emails.append(fresh_email)

    with_existing = _register(client, fresh_username, verified["email"])
    with_new = _register(client, _new_identity()[0], fresh_email)

    assert with_existing.status_code == with_new.status_code == 201
    assert _shape(with_existing) == _shape(with_new)


# ============================================================================
# Carreras: el INSERT salta una restricción única
# ============================================================================


@pytest.fixture
def stale_first_lookup():
    """
    La primera consulta previa no ve nada (otra petición aún no había confirmado su alta); las
    siguientes son las reales. El INSERT salta entonces la restricción única de verdad.
    """
    original = AuthService._find_existing_account
    calls = {"count": 0}

    def lookup(self, username, email):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return original(self, username, email)

    with patch.object(AuthService, "_find_existing_account", lookup):
        yield calls


def test_race_on_the_email_of_a_verified_account_gets_the_uniform_201(
    client, db_session, created_emails, outbox, stale_first_lookup
):
    verified = _make_user(db_session, created_emails, verified=True)
    username = _new_identity()[0]

    response = _register(client, username, verified["email"])

    assert response.status_code == 201, response.text
    assert response.json()["data"]["user_id"] != verified["id"]
    assert stale_first_lookup["count"] == 2
    assert _subjects(outbox) == ["Ya tienes una cuenta en DataMap Assistant"]
    assert _count_users(db_session, username=username) == 0


def test_race_on_the_email_of_an_unverified_account_reissues_the_code(
    client, db_session, created_emails, outbox, stale_first_lookup
):
    account = _make_user(db_session, created_emails, verified=False)

    response = _register(client, _new_identity()[0], account["email"])

    assert response.status_code == 201, response.text
    assert _subjects(outbox) == ["Tu código de verificación"]
    assert _otp_row(db_session, account["id"]) is not None


def test_race_on_the_email_of_a_deleted_account_gets_the_uniform_201(
    client, db_session, created_emails, outbox, stale_first_lookup
):
    deleted = _make_user(db_session, created_emails, verified=True, deleted=True)

    response = _register(client, _new_identity()[0], deleted["email"])

    assert response.status_code == 201, response.text
    assert outbox == []


@pytest.mark.parametrize("owner_deleted", [False, True], ids=["live_owner", "deleted_owner"])
def test_race_on_the_username_answers_409(
    owner_deleted, client, db_session, created_emails, outbox, stale_first_lookup
):
    owner = _make_user(db_session, created_emails, verified=True, deleted=owner_deleted)
    email = _new_identity()[1]
    created_emails.append(email)

    response = _register(client, owner["username"], email)

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "username_taken"
    assert _count_users(db_session, email=email) == 0
    assert outbox == []


def test_race_that_leaves_no_conflict_still_answers_409(client, db_session, created_emails, outbox):
    """Si tras el rollback no se encuentra el motivo (p. ej. otra restricción), 409 de siempre"""
    owner = _make_user(db_session, created_emails, verified=True)

    with patch.object(AuthService, "_find_existing_account", return_value=None):
        response = _register(client, owner["username"], _new_identity()[1])

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "registration_failed"
    assert outbox == []


# ============================================================================
# Coste: el camino «existente» gasta el bcrypt del OTP
# ============================================================================


@pytest.mark.parametrize(
    "kind, expected_calls",
    [("verified", 1), ("deleted", 1), ("unverified", 0), ("new", 0)],
)
def test_existing_account_paths_spend_the_simulated_otp_check(
    kind, expected_calls, client, db_session, created_emails, outbox
):
    """Verificada y borrada no emiten OTP: gastan el bcrypt simulado; las demás, el real"""
    if kind == "new":
        username, email = _new_identity()
        created_emails.append(email)
    else:
        account = _make_user(
            db_session,
            created_emails,
            verified=(kind == "verified"),
            deleted=(kind == "deleted"),
        )
        username, email = _new_identity()[0], account["email"]

    with patch.object(email_otp_crud, "simulate_otp_check") as spent:
        response = _register(client, username, email)

    assert response.status_code == 201, response.text
    assert spent.call_count == expected_calls


def test_username_taken_does_not_spend_an_otp_check(client, db_session, created_emails, outbox):
    owner = _make_user(db_session, created_emails, verified=True)

    with patch.object(email_otp_crud, "simulate_otp_check") as spent:
        response = _register(client, owner["username"], _new_identity()[1])

    assert response.status_code == 409
    assert spent.call_count == 0


def test_the_password_is_hashed_before_looking_the_email_up(
    client, db_session, created_emails, outbox
):
    """El bcrypt de la contraseña va antes de la consulta: todas las ramas lo pagan"""
    verified = _make_user(db_session, created_emails, verified=True)
    order = []
    real_hash = pwd_context.hash
    real_find = AuthService._find_existing_account

    def hashed(*args, **kwargs):
        order.append("hash")
        return real_hash(*args, **kwargs)

    def found(self, username, email):
        order.append("lookup")
        return real_find(self, username, email)

    with (
        patch("app.services.auth_service.pwd_context.hash", hashed),
        patch.object(AuthService, "_find_existing_account", found),
    ):
        _register(client, _new_identity()[0], verified["email"])

    assert order == ["hash", "lookup"]


# ============================================================================
# La respuesta no filtra nada
# ============================================================================


def test_uniform_bodies_never_contain_a_code_or_hash(client, db_session, created_emails, outbox):
    verified = _make_user(db_session, created_emails, verified=True)
    unverified = _make_user(db_session, created_emails, verified=False, otp=OTP_CODE)

    for account in (verified, unverified):
        response = _register(client, _new_identity()[0], account["email"])
        assert response.status_code == 201, response.text
        assert PASSWORD_HASH not in response.text
        assert OTP_CODE not in response.text
        for message in outbox:
            if message["Subject"] == "Tu código de verificación":
                assert _code_of(message) not in response.text
        assert account["id"] not in response.text


# ============================================================================
# Log de seguridad
# ============================================================================


def _logged(log):
    return [call.kwargs for call in log.await_args_list]


def test_new_account_logs_registration_success_with_its_real_id(
    client, db_session, created_emails, outbox
):
    username, email = _new_identity()
    created_emails.append(email)

    with patch.object(SecurityLogger, "log_event", new=AsyncMock()) as log:
        response = _register(client, username, email)

    events = _logged(log)
    assert [e["event_type"] for e in events] == ["registration_success"]
    assert events[0]["user_id"] == str(_stored(db_session, email).id)
    assert events[0]["user_id"] == response.json()["data"]["user_id"]


@pytest.mark.parametrize(
    "kind, reason",
    [
        ("verified", "account_already_verified"),
        ("unverified", "account_unverified_reissued"),
        ("deleted", "account_deleted"),
    ],
)
def test_existing_email_logs_the_real_reason_and_no_registration_success(
    kind, reason, client, db_session, created_emails, outbox
):
    account = _make_user(
        db_session, created_emails, verified=(kind == "verified"), deleted=(kind == "deleted")
    )
    username = _new_identity()[0]

    with patch.object(SecurityLogger, "log_event", new=AsyncMock()) as log:
        response = _register(client, username, account["email"])

    events = _logged(log)
    assert [e["event_type"] for e in events] == ["registration_duplicate_email"]
    event = events[0]
    assert event["details"]["reason"] == reason
    assert event["details"]["email_attempted"] == account["email"]
    assert event["username"] == username
    # El id del log es el de la cuenta real, nunca el aleatorio de la respuesta (FK a users)
    assert event["user_id"] == account["id"]
    assert event["user_id"] != response.json()["data"]["user_id"]
    assert "registration_success" not in [e["event_type"] for e in events]


def test_taken_username_logs_registration_failed_with_the_reason(
    client, db_session, created_emails, outbox
):
    owner = _make_user(db_session, created_emails, verified=True)

    with patch.object(SecurityLogger, "log_event", new=AsyncMock()) as log:
        _register(client, owner["username"], _new_identity()[1])

    events = _logged(log)
    assert [e["event_type"] for e in events] == ["registration_failed"]
    assert events[0]["details"]["failure_reason"] == "username_taken"


def test_uniform_branch_writes_a_real_security_log_row(client, db_session, created_emails, outbox):
    """Sin parchear el logger: el id real de la cuenta cumple la FK de security_logs.user_id"""
    account = _make_user(db_session, created_emails, verified=True)
    query = text(
        "SELECT user_id, details->>'reason' FROM security_logs "
        "WHERE event_type = 'registration_duplicate_email' "
        "AND details->>'email_attempted' = :email"
    )

    try:
        response = _register(client, _new_identity()[0], account["email"])
        assert response.status_code == 201, response.text
        db_session.rollback()
        rows = db_session.execute(query, {"email": account["email"]}).fetchall()
    finally:
        db_session.rollback()
        db_session.execute(
            text(
                "DELETE FROM security_logs WHERE event_type = 'registration_duplicate_email' "
                "AND details->>'email_attempted' = :email"
            ),
            {"email": account["email"]},
        )
        db_session.commit()

    assert [(str(user_id), reason) for user_id, reason in rows] == [
        (account["id"], "account_already_verified")
    ]


# ============================================================================
# Entrega: el aviso sale después de responder y el servicio no depende de FastAPI
# ============================================================================


def test_service_hands_the_notice_to_notify_existing(db_session, created_emails, outbox):
    verified = _make_user(db_session, created_emails, verified=True)
    delivered, notified = [], []

    result = AuthService(db_session).create_user(
        _new_identity()[0],
        verified["email"],
        NEW_PASSWORD,
        deliver=lambda to, code: delivered.append((to, code)),
        notify_existing=notified.append,
    )

    assert notified == [verified["email"]]
    assert delivered == []
    assert outbox == []
    assert set(result) == {"user_id", "username", "email"}
    assert result.outcome == "account_already_verified"
    assert result.account_id == verified["id"]


def test_service_without_notify_existing_sends_the_notice_itself(
    db_session, created_emails, outbox
):
    """Sin callback (llamadores síncronos) el aviso se envía en el acto, como el código"""
    verified = _make_user(db_session, created_emails, verified=True)

    AuthService(db_session).create_user(_new_identity()[0], verified["email"], NEW_PASSWORD)

    assert _subjects(outbox) == ["Ya tienes una cuenta en DataMap Assistant"]


def test_service_reissues_the_code_through_deliver(db_session, created_emails, outbox):
    account = _make_user(db_session, created_emails, verified=False)
    delivered = []

    result = AuthService(db_session).create_user(
        _new_identity()[0],
        account["email"],
        NEW_PASSWORD,
        deliver=lambda to, code: delivered.append((to, code)),
    )

    assert [to for to, _ in delivered] == [account["email"]]
    assert len(delivered[0][1]) == 8
    assert result.outcome == "account_unverified_reissued"
    assert delivered[0][1] not in json.dumps(result)


def _asgi_post(path, payload):
    """Una petición directa a la app ASGI con las marcas de tiempo de la respuesta"""
    from main import app

    async def run():
        body = json.dumps(payload).encode()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [
                (b"host", b"testserver"),
                (b"user-agent", b"pytest-asgi"),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
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
            started=started,
            sent_at=state["sent_at"],
            finished=time.monotonic(),
        )

    return asyncio.run(run())


def test_the_notice_is_delivered_after_the_response_is_sent(
    client, db_session, created_emails, slow_smtp
):
    verified = _make_user(db_session, created_emails, verified=True)
    payload = {
        "username": _new_identity()[0],
        "email": verified["email"],
        "password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    }

    response = _asgi_post("/api/auth/register", payload)

    assert response.status == 201, response.text
    # La respuesta no espera al SMTP...
    assert response.sent_at - response.started < SMTP_DELAY_SECONDS
    # ...sale mientras el envío sigue en curso...
    assert slow_smtp["calls"] == 1
    assert response.sent_at < slow_smtp["finished"] - SMTP_DELAY_SECONDS / 2
    # ...y la app no termina hasta que la tarea de fondo ha acabado
    assert slow_smtp["finished"] <= response.finished
