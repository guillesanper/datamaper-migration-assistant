"""
Robustez del limitador de base de datos (riesgo 6 de los riesgos abiertos, fase R4).

- La E/S de BD del limitador (comprobar, contar, anotar fallos) corre en el threadpool:
  la sesión se abre, se usa y se cierra en el mismo hilo y el event loop no se bloquea
  mientras la BD tarda.
- Si la BD falla, el limitador sigue permitiendo la petición (fail-open) pero deja un
  logger.error con traza y una cadena estable (rate_limit_backend_unavailable), sin
  el identificador entero y sin imprimir en stdout.

Los tests de este fichero parchean el CRUD y la sesión: no escriben en la BD.
"""

import asyncio
import logging
import threading
import time
import uuid
from unittest.mock import patch

import pytest
from fastapi import Request

from app.config.security import security_settings
from app.middleware.rate_limiting import DatabaseRateLimiter

RULE = {"max_attempts": 3, "window_seconds": 600}
ALLOWED = {"is_allowed": True, "is_blocked": False, "blocked_until": None}

# Operación del limitador -> (función del CRUD que corre en el hilo, cómo se invoca)
OPERATIONS = {
    "count": (
        "check_limit_orm",
        lambda request: DatabaseRateLimiter.count_request(request, rule=RULE),
    ),
    "peek": (
        "peek_limit_orm",
        lambda request: DatabaseRateLimiter.peek_request(request, rule=RULE),
    ),
    "failure": (
        "record_failure_orm",
        lambda request: DatabaseRateLimiter.count_failure(request, rule=RULE),
    ),
}


# ============================================================================
# Fixtures y helpers
# ============================================================================


@pytest.fixture(autouse=True)
def production_mode(monkeypatch):
    """Los límites reales solo se aplican fuera de desarrollo"""
    monkeypatch.setattr(security_settings, "DEVELOPMENT_MODE", False)
    monkeypatch.setattr(security_settings, "TRUSTED_PROXY_HOPS", 0)


def _request(path: str = "/api/test-robustness") -> Request:
    """Request real de Starlette (un mock con spec de Request es falsy: es un Mapping vacío)"""
    raw = uuid.uuid4().bytes
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": (f"10.{raw[0]}.{raw[1]}.{raw[2]}", 50000),
        }
    )


class _FakeSession:
    """Sesión sin BD que anota en qué hilo se abre y en cuál se cierra"""

    def __init__(self):
        self.opened_in = None
        self.closed_in = None

    def close(self):
        self.closed_in = threading.get_ident()


@pytest.fixture
def fake_session():
    """Sustituye get_db_session por un generador que entrega una _FakeSession"""
    session = _FakeSession()

    def _get_db_session():
        session.opened_in = threading.get_ident()
        yield session

    with patch("app.middleware.rate_limiting.get_db_session", _get_db_session):
        yield session


# ============================================================================
# La E/S de BD corre en el threadpool
# ============================================================================


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_counter_io_runs_in_a_worker_thread_and_the_session_stays_in_it(operation, fake_session):
    crud_name, invoke = OPERATIONS[operation]
    crud_thread = []

    def fake_crud(*args, **kwargs):
        crud_thread.append(threading.get_ident())
        return dict(ALLOWED)

    with patch(f"app.crud.rate_limit_crud.{crud_name}", side_effect=fake_crud):
        result = asyncio.run(invoke(_request()))

    main = threading.get_ident()
    assert result["is_allowed"] is True
    assert crud_thread and crud_thread[0] != main
    # Una sesión por hilo: se abre, se usa y se cierra en el mismo hilo, no en el del loop
    assert fake_session.opened_in == crud_thread[0]
    assert fake_session.closed_in == crud_thread[0]


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_session_is_closed_in_its_thread_when_the_crud_fails(operation, fake_session):
    crud_name, invoke = OPERATIONS[operation]

    with patch(f"app.crud.rate_limit_crud.{crud_name}", side_effect=RuntimeError("db caída")):
        result = asyncio.run(invoke(_request()))

    # Fail-open: la petición pasa, y la sesión no queda abierta ni se cierra en el loop
    assert result["is_allowed"] is True
    assert fake_session.opened_in is not None
    assert fake_session.opened_in != threading.get_ident()
    assert fake_session.closed_in == fake_session.opened_in


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_event_loop_stays_responsive_while_the_database_is_slow(operation, fake_session):
    """Equivalente de la puerta en vivo: el loop sigue atendiendo mientras la BD tarda"""
    crud_name, invoke = OPERATIONS[operation]
    gaps = []
    slow_calls = []

    def slow_crud(*args, **kwargs):
        slow_calls.append(1)
        time.sleep(0.4)
        return dict(ALLOWED)

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
        result = await invoke(_request())
        await asyncio.sleep(0.05)
        beat.cancel()
        return result

    with patch(f"app.crud.rate_limit_crud.{crud_name}", side_effect=slow_crud):
        result = asyncio.run(scenario())

    assert result["is_allowed"] is True
    assert slow_calls == [1]
    assert max(gaps) < 0.25
    # El latido se ha ejercido de verdad (la prueba no es vacía)
    assert len(gaps) > 10


# ============================================================================
# El fail-open deja rastro: logger.error con traza y nada en stdout
# ============================================================================

LOGGER_NAME = "app.middleware.rate_limiting"
STABLE_MARK = "rate_limit_backend_unavailable"


@pytest.fixture
def limiter_log(caplog, monkeypatch):
    """
    Captura el logger del limitador a nivel ERROR

    El conftest ejecuta `alembic upgrade head` en el proceso y fileConfig deja deshabilitados
    los loggers ya creados: sin reactivarlo, los tests de ausencia pasarían en vacío.
    """
    logger = logging.getLogger(LOGGER_NAME)
    monkeypatch.setattr(logger, "disabled", False)
    caplog.set_level(logging.ERROR, logger=LOGGER_NAME)
    return caplog


@pytest.fixture
def database_down():
    with patch(
        "app.middleware.rate_limiting.get_db_session",
        side_effect=RuntimeError("conexion rechazada"),
    ):
        yield


def _errors(caplog) -> list:
    return [r for r in caplog.records if r.name == LOGGER_NAME and r.levelno == logging.ERROR]


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_database_failure_is_logged_at_error_level_with_the_traceback(
    operation, limiter_log, database_down
):
    _crud_name, invoke = OPERATIONS[operation]

    result = asyncio.run(invoke(_request()))

    assert result["is_allowed"] is True  # fail-open: se conserva (disponibilidad)
    records = _errors(limiter_log)
    assert len(records) == 1
    assert STABLE_MARK in records[0].getMessage()
    # La traza viaja con el registro: sin ella, la causa no se puede diagnosticar
    assert records[0].exc_info is not None
    assert "conexion rechazada" in limiter_log.text


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_the_log_line_carries_the_operation_but_not_the_identifier(
    operation, limiter_log, database_down
):
    from app.middleware.rate_limiting import _counter_target

    _crud_name, invoke = OPERATIONS[operation]
    request = _request("/api/auth/login")
    identifier = _counter_target(request, None, RULE)[0]

    asyncio.run(invoke(request))

    message = _errors(limiter_log)[0].getMessage()
    assert f"operation={operation}" in message
    assert "/api/auth/login" in message
    # El identificador es un hash de la IP: no se registra entero
    assert identifier not in limiter_log.text
    assert identifier[:12] not in limiter_log.text


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_database_failure_prints_nothing(operation, limiter_log, database_down, capsys):
    _crud_name, invoke = OPERATIONS[operation]

    asyncio.run(invoke(_request()))

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_every_failed_request_leaves_one_error_line(limiter_log, database_down):
    request = _request()

    for _ in range(3):
        asyncio.run(DatabaseRateLimiter.count_request(request, rule=RULE))

    assert len(_errors(limiter_log)) == 3


def test_a_crud_failure_is_logged_too(limiter_log, fake_session):
    """El fallo puede venir del CRUD (no solo de la conexión): misma línea, misma traza"""
    with patch("app.crud.rate_limit_crud.check_limit_orm", side_effect=RuntimeError("SQL roto")):
        result = asyncio.run(DatabaseRateLimiter.count_request(_request(), rule=RULE))

    assert result["is_allowed"] is True
    records = _errors(limiter_log)
    assert len(records) == 1
    assert STABLE_MARK in records[0].getMessage()
    assert "SQL roto" in limiter_log.text


def test_a_healthy_request_logs_no_error(limiter_log, fake_session):
    with patch("app.crud.rate_limit_crud.check_limit_orm", return_value=dict(ALLOWED)):
        asyncio.run(DatabaseRateLimiter.count_request(_request(), rule=RULE))

    assert _errors(limiter_log) == []
