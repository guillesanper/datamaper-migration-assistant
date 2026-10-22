"""
Tests del rate limiting por base de datos (hallazgo 2 de la deuda de autenticación).

- `check_rate_limit` usa la regla explícita que recibe (antes ignoraba sus argumentos y
  caía en la tabla de rutas cortas o en 20/3600).
- El decorador `@rate_limit(n, s)` honra sus argumentos y responde 429 con `Retry-After`.
- La ventana se reinicia al vencer; los contadores son independientes por IP y por cuenta.
- El contador por IP no se evade falsificando X-Forwarded-For (TRUSTED_PROXY_HOPS=0).
- En desarrollo se conserva la configuración permisiva, también con reglas explícitas.

Los contadores van a la BD de test y no se deshacen con rollback: cada test usa una ruta
única y borra sus filas al terminar.
"""

import asyncio
import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request
from sqlalchemy import text

from app.config.security import security_settings
from app.middleware.rate_limiting import db_rate_limiter
from app.utils.error_codes import ErrorCode, make_error

RULE = {"max_attempts": 3, "window_seconds": 600}


# ============================================================================
# Fixtures y helpers
# ============================================================================


@pytest.fixture
def production_mode(monkeypatch):
    """Los límites reales solo se aplican fuera de desarrollo"""
    monkeypatch.setattr(security_settings, "DEVELOPMENT_MODE", False)


@pytest.fixture
def trusted_hops(monkeypatch):
    def _set(hops):
        monkeypatch.setattr(security_settings, "TRUSTED_PROXY_HOPS", hops)

    _set(0)
    return _set


@pytest.fixture
def path(db_session):
    """Ruta única por test (clave del contador); se borran sus filas al terminar"""
    value = f"/api/test-limits/{uuid.uuid4().hex}"
    yield value

    db_session.rollback()
    db_session.execute(
        text("DELETE FROM security_rate_limits WHERE endpoint LIKE :prefix"),
        {"prefix": value + "%"},
    )
    db_session.commit()


def _ip() -> str:
    raw = uuid.uuid4().bytes
    return f"10.{raw[0]}.{raw[1]}.{raw[2]}"


def _request(ip: str, path: str, headers=None) -> Request:
    """Request real de Starlette (un mock con spec de Request es falsy: es un Mapping vacío)"""
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": raw_headers,
            "client": (ip, 50000),
        }
    )


def _check(request, **kwargs) -> bool:
    return asyncio.run(db_rate_limiter.check_rate_limit(request, **kwargs))


def _exhaust(request, rule=RULE, **kwargs):
    """Gasta todo el cupo de la regla; todas las peticiones están permitidas"""
    for _ in range(rule["max_attempts"]):
        assert _check(request, rule=rule, **kwargs) is True


# ============================================================================
# check_rate_limit con regla explícita
# ============================================================================


def test_explicit_rule_blocks_after_max_attempts(production_mode, path):
    request = _request(_ip(), path)

    _exhaust(request)

    assert _check(request, rule=RULE) is False


def test_rule_is_used_instead_of_the_default_for_the_path(production_mode, path):
    """Sin regla, una ruta cualquiera cae en 20/3600; con regla, en la suya"""
    request = _request(_ip(), path)

    _exhaust(request, {"max_attempts": 1, "window_seconds": 600})

    assert _check(request, rule={"max_attempts": 1, "window_seconds": 600}) is False


def test_counter_is_keyed_by_request_path(production_mode, path):
    ip = _ip()
    first = _request(ip, path)
    other = _request(ip, path + "/other")

    _exhaust(first)

    assert _check(first, rule=RULE) is False
    assert _check(other, rule=RULE) is True


def test_window_resets_when_it_expires(production_mode, path, db_session):
    request = _request(_ip(), path)
    _exhaust(request)
    assert _check(request, rule=RULE) is False

    # Ventana y bloqueo vencidos: el contador vuelve a empezar
    db_session.execute(
        text(
            "UPDATE security_rate_limits "
            "SET window_start = now() - interval '2 hours', blocked_until = now() - interval '1 hour' "
            "WHERE endpoint = :endpoint"
        ),
        {"endpoint": path},
    )
    db_session.commit()

    _exhaust(request)
    assert _check(request, rule=RULE) is False


def test_blocked_identifier_stays_blocked_until_the_block_expires(production_mode, path):
    request = _request(_ip(), path)
    _exhaust(request)
    assert _check(request, rule=RULE) is False

    assert _check(request, rule=RULE) is False


def test_counters_are_isolated_by_ip(production_mode, path):
    attacker = _request(_ip(), path)
    other = _request(_ip(), path)

    _exhaust(attacker)

    assert _check(attacker, rule=RULE) is False
    assert _check(other, rule=RULE) is True


def test_counters_are_isolated_by_account(production_mode, path):
    victim = "victim@example.com"
    bystander = "bystander@example.com"

    # cada petición viene de una IP nueva: solo puede limitar el contador de la cuenta
    for _ in range(RULE["max_attempts"]):
        assert _check(_request(_ip(), path), rule=RULE, account=victim) is True

    assert _check(_request(_ip(), path), rule=RULE, account=victim) is False
    assert _check(_request(_ip(), path), rule=RULE, account=bystander) is True


def test_account_counter_is_normalised(production_mode, path):
    """Mayúsculas y espacios no dan un contador nuevo para la misma cuenta"""
    for variant in ("Victim@Example.com", " victim@example.com", "VICTIM@EXAMPLE.COM"):
        assert _check(_request(_ip(), path), rule=RULE, account=variant) is True

    assert _check(_request(_ip(), path), rule=RULE, account="victim@example.com") is False


def test_account_counter_does_not_depend_on_the_ip_counter(production_mode, path):
    """Un atacante distribuido (una IP por petición) sigue limitado por cuenta"""
    results = [
        _check(_request(_ip(), path), rule=RULE, account="victim@example.com")
        for _ in range(RULE["max_attempts"] + 2)
    ]

    assert results == [True] * RULE["max_attempts"] + [False, False]


def test_ip_and_account_counters_coexist_for_the_same_request(production_mode, path, db_session):
    """
    resend-code cuenta cada petición por IP y por cuenta. (ip_address, endpoint) es único en la
    tabla: el contador de cuenta no puede reutilizar la fila del de IP (el fallo se tragaba en
    silencio por el fail-open y el límite por cuenta no se aplicaba).
    """
    request = _request(_ip(), path)

    for _ in range(RULE["max_attempts"]):
        assert _check(request, rule=RULE) is True
        assert _check(request, rule=RULE, account="victim@example.com") is True

    assert _check(request, rule=RULE) is False
    assert _check(request, rule=RULE, account="victim@example.com") is False

    db_session.rollback()
    rows = db_session.execute(
        text("SELECT count(*) FROM security_rate_limits WHERE endpoint = :endpoint"),
        {"endpoint": path},
    ).scalar()
    assert rows == 2


def test_forged_x_forwarded_for_does_not_change_the_counter(production_mode, trusted_hops, path):
    trusted_hops(0)
    ip = _ip()

    for i in range(RULE["max_attempts"]):
        request = _request(ip, path, {"X-Forwarded-For": f"203.0.113.{i}"})
        assert _check(request, rule=RULE) is True

    forged = _request(ip, path, {"X-Forwarded-For": "203.0.113.250"})
    assert _check(forged, rule=RULE) is False


def test_one_trusted_hop_counts_by_the_proxy_appended_entry(production_mode, trusted_hops, path):
    trusted_hops(1)
    proxy, client_a, client_b = _ip(), _ip(), _ip()

    for i in range(RULE["max_attempts"]):
        request = _request(proxy, path, {"X-Forwarded-For": f"203.0.113.{i}, {client_a}"})
        assert _check(request, rule=RULE) is True

    spoofing_a = _request(proxy, path, {"X-Forwarded-For": f"203.0.113.250, {client_a}"})
    assert _check(spoofing_a, rule=RULE) is False
    # otro cliente detrás del mismo proxy tiene su propio cupo
    through_proxy = _request(proxy, path, {"X-Forwarded-For": client_b})
    assert _check(through_proxy, rule=RULE) is True


def test_development_mode_keeps_the_permissive_config_for_explicit_rules(monkeypatch, path):
    monkeypatch.setattr(security_settings, "DEVELOPMENT_MODE", True)
    request = _request(_ip(), path)
    strict = {"max_attempts": 1, "window_seconds": 600}

    results = [_check(request, rule=strict) for _ in range(10)]

    assert all(results)


def test_database_failure_is_fail_open(production_mode, path):
    request = _request(_ip(), path)

    with patch("app.middleware.rate_limiting.get_db_session", side_effect=RuntimeError("db")):
        assert _check(request, rule=RULE) is True


# ============================================================================
# Decorador @rate_limit y 429 con Retry-After
# ============================================================================


def test_decorator_honours_its_arguments(production_mode, path):
    from app.middleware.rate_limiting import rate_limit

    @rate_limit(2, 600)
    async def endpoint(request: Request):
        return "ok"

    request = _request(_ip(), path)

    assert asyncio.run(endpoint(request)) == "ok"
    assert asyncio.run(endpoint(request)) == "ok"
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint(request))

    assert excinfo.value.status_code == 429


def test_decorator_429_has_retry_after_and_the_usual_body(production_mode, path):
    from app.middleware.rate_limiting import rate_limit

    @rate_limit(1, 600)
    async def endpoint(request: Request):
        return "ok"

    request = _request(_ip(), path)
    asyncio.run(endpoint(request))
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint(request))

    exc = excinfo.value
    assert exc.status_code == 429
    assert exc.detail == make_error(ErrorCode.RATE_LIMIT_EXCEEDED)
    retry_after = int(exc.headers["Retry-After"])
    assert 0 < retry_after <= 600


def test_decorator_forwards_the_arguments_of_the_endpoint(production_mode, path):
    from app.middleware.rate_limiting import rate_limit

    @rate_limit(5, 600)
    async def endpoint(request: Request, data: str, extra: int = 0):
        return (data, extra)

    request = _request(_ip(), path)

    assert asyncio.run(endpoint(request=request, data="x", extra=2)) == ("x", 2)


def test_enforce_rate_limit_rejects_with_429_and_retry_after(production_mode, path):
    from app.middleware.rate_limiting import enforce_rate_limit

    request = _request(_ip(), path)
    asyncio.run(enforce_rate_limit(request, 1, 600, account="victim@example.com"))

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(enforce_rate_limit(request, 1, 600, account="victim@example.com"))

    assert excinfo.value.status_code == 429
    assert int(excinfo.value.headers["Retry-After"]) > 0


def test_enforce_rate_limit_without_account_counts_by_ip(production_mode, path):
    from app.middleware.rate_limiting import enforce_rate_limit

    request = _request(_ip(), path)
    asyncio.run(enforce_rate_limit(request, 1, 600))

    with pytest.raises(HTTPException):
        asyncio.run(enforce_rate_limit(request, 1, 600))


def test_global_rate_limit_middleware_is_gone():
    """El middleware global y su tabla de rutas cortas (que nunca casaban) se retiran"""
    import app.middleware.rate_limiting as module

    assert not hasattr(module, "rate_limit_middleware")
    assert not hasattr(security_settings, "RATE_LIMITS")


def test_main_does_not_register_the_global_middleware():
    from pathlib import Path

    main_source = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")

    assert "rate_limit_middleware" not in main_source
