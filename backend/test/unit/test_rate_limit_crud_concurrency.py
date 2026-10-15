"""
Concurrencia del contador de rate limiting (riesgo 6 de los riesgos abiertos, fase R4).

check_limit_orm y record_failure_orm leían la fila, sumaban en Python y escribían: con
peticiones simultáneas se perdían incrementos, el reinicio de ventana lo hacían varias a la
vez y la primera petición de un identificador nuevo chocaba con el índice único. Aquí se
ejercitan con hilos reales (una sesión por hilo, como en producción) contra la BD de test.

Los contadores se confirman con commit y no se deshacen con rollback: cada test usa un
endpoint único y borra sus filas al terminar.
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List, Tuple

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.crud import rate_limit_crud
from app.models.orm import SecurityRateLimit

THREADS = 12
BLOCK_MINUTES = 15


# ============================================================================
# Fixtures y helpers
# ============================================================================


@pytest.fixture
def endpoint(db_session: Session):
    """Endpoint único por test (clave del contador); se borran sus filas al terminar"""
    value = f"/api/test-concurrency/{uuid.uuid4().hex}"
    yield value

    db_session.rollback()
    db_session.execute(
        text("DELETE FROM security_rate_limits WHERE endpoint = :endpoint"),
        {"endpoint": value},
    )
    db_session.commit()


def _identifier() -> str:
    return f"ip_{uuid.uuid4().hex[:12]}"


def _run_concurrently(
    count: int, work: Callable[[int, Session], Any]
) -> Tuple[List[Any], List[BaseException]]:
    """
    Lanza `count` hilos que esperan en una barrera y ejecutan `work(indice, sesion)` a la vez

    Cada hilo abre su propia sesión (el SessionLocal que deja configurado el conftest).
    Devuelve (resultados por índice, excepciones).
    """
    from app.database import session as session_module

    barrier = threading.Barrier(count)
    results: List[Any] = [None] * count
    errors: List[BaseException] = []

    def worker(index: int) -> None:
        db = session_module.SessionLocal()
        try:
            barrier.wait(timeout=30)
            results[index] = work(index, db)
        except BaseException as exc:  # noqa: BLE001 - se devuelve al test
            errors.append(exc)
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results, errors


def _check(db: Session, identifier: str, endpoint: str, max_requests: int = 1000) -> dict:
    return rate_limit_crud.check_limit_orm(
        db,
        identifier=identifier,
        ip_address=identifier,
        endpoint=endpoint,
        max_requests=max_requests,
        window_minutes=60,
        block_duration_minutes=BLOCK_MINUTES,
    )


def _fail(db: Session, identifier: str, endpoint: str, max_failures: int = 1000) -> dict:
    return rate_limit_crud.record_failure_orm(
        db,
        identifier=identifier,
        ip_address=identifier,
        endpoint=endpoint,
        max_failures=max_failures,
        window_minutes=60,
        block_duration_minutes=BLOCK_MINUTES,
    )


def _row(db_session: Session, identifier: str, endpoint: str) -> SecurityRateLimit:
    """La fila tal como está en la BD (la sesión del test no guarda copias obsoletas)"""
    db_session.rollback()
    db_session.expire_all()
    row = (
        db_session.query(SecurityRateLimit)
        .filter(SecurityRateLimit.identifier == identifier, SecurityRateLimit.endpoint == endpoint)
        .one()
    )
    return row


def _expire_window(db_session: Session, identifier: str, endpoint: str) -> None:
    db_session.execute(
        text(
            "UPDATE security_rate_limits SET window_start = :start "
            "WHERE identifier = :identifier AND endpoint = :endpoint"
        ),
        {
            "start": datetime.now(timezone.utc) - timedelta(hours=2),
            "identifier": identifier,
            "endpoint": endpoint,
        },
    )
    db_session.commit()


# ============================================================================
# check_limit_orm
# ============================================================================


def test_check_limit_orm_counts_every_concurrent_request(db_session: Session, endpoint: str):
    """Antes se leía, se sumaba en Python y se escribía: los incrementos se pisaban"""
    identifier = _identifier()
    _check(db_session, identifier, endpoint)  # la fila ya existe: solo hay actualizaciones

    results, errors = _run_concurrently(
        THREADS, lambda _i, db: [_check(db, identifier, endpoint) for _ in range(5)]
    )

    assert errors == []
    assert _row(db_session, identifier, endpoint).request_count == 1 + THREADS * 5
    counts = sorted(r["request_count"] for batch in results for r in batch)
    assert counts == list(range(2, 2 + THREADS * 5)), "cada petición ve un valor distinto"


def test_check_limit_orm_first_concurrent_requests_are_all_counted(
    db_session: Session, endpoint: str
):
    """Todas ven «no existe»: una crea la fila y las demás no deben chocar con el índice único"""
    identifier = _identifier()

    results, errors = _run_concurrently(THREADS, lambda _i, db: _check(db, identifier, endpoint))

    assert errors == []
    assert all(r["is_allowed"] for r in results)
    assert sorted(r["request_count"] for r in results) == list(range(1, THREADS + 1))
    assert _row(db_session, identifier, endpoint).request_count == THREADS


def test_check_limit_orm_concurrent_requests_block_after_exactly_the_maximum(
    db_session: Session, endpoint: str
):
    """Se permiten `max` peticiones y la siguiente bloquea; las demás ya no suman"""
    identifier = _identifier()
    maximum = 5

    results, errors = _run_concurrently(
        THREADS, lambda _i, db: _check(db, identifier, endpoint, max_requests=maximum)
    )

    assert errors == []
    assert sum(1 for r in results if r["is_allowed"]) == maximum
    row = _row(db_session, identifier, endpoint)
    assert row.request_count == maximum + 1
    assert row.blocked_until is not None


def test_check_limit_orm_blocked_identifier_does_not_sum_under_concurrency(
    db_session: Session, endpoint: str
):
    identifier = _identifier()
    for _ in range(4):
        blocked = _check(db_session, identifier, endpoint, max_requests=3)
    assert blocked["is_blocked"] is True
    count_before = _row(db_session, identifier, endpoint).request_count

    results, errors = _run_concurrently(
        THREADS, lambda _i, db: _check(db, identifier, endpoint, max_requests=3)
    )

    assert errors == []
    assert all(r["is_allowed"] is False and r["is_blocked"] is True for r in results)
    assert _row(db_session, identifier, endpoint).request_count == count_before


def test_check_limit_orm_window_reset_happens_once_under_concurrency(
    db_session: Session, endpoint: str
):
    """Con la ventana vencida, un solo reinicio a 1; las demás suman encima (no reinician)"""
    identifier = _identifier()
    for _ in range(5):
        _check(db_session, identifier, endpoint)
    _expire_window(db_session, identifier, endpoint)

    results, errors = _run_concurrently(THREADS, lambda _i, db: _check(db, identifier, endpoint))

    assert errors == []
    assert sorted(r["request_count"] for r in results) == list(range(1, THREADS + 1))
    assert _row(db_session, identifier, endpoint).request_count == THREADS


def test_check_limit_orm_keeps_failing_loudly_when_the_row_cannot_be_created(
    db_session: Session, endpoint: str
):
    """
    (ip_address, endpoint) es único: otro identificador con la misma IP no puede crear su fila.
    Es un error (el limitador lo trata como fail-open y lo registra), no un permiso mudo.
    """
    shared_ip = _identifier()
    _check(db_session, shared_ip, endpoint)

    with pytest.raises(Exception):
        rate_limit_crud.check_limit_orm(
            db_session,
            identifier=_identifier(),
            ip_address=shared_ip,
            endpoint=endpoint,
            max_requests=10,
            window_minutes=60,
        )


# ============================================================================
# record_failure_orm
# ============================================================================


def test_record_failure_orm_counts_every_concurrent_failure(db_session: Session, endpoint: str):
    identifier = _identifier()
    _fail(db_session, identifier, endpoint)

    results, errors = _run_concurrently(
        THREADS, lambda _i, db: [_fail(db, identifier, endpoint) for _ in range(5)]
    )

    assert errors == []
    assert _row(db_session, identifier, endpoint).request_count == 1 + THREADS * 5
    counts = sorted(r["request_count"] for batch in results for r in batch)
    assert counts == list(range(2, 2 + THREADS * 5))


def test_record_failure_orm_first_concurrent_failures_are_all_counted(
    db_session: Session, endpoint: str
):
    identifier = _identifier()

    results, errors = _run_concurrently(THREADS, lambda _i, db: _fail(db, identifier, endpoint))

    assert errors == []
    assert sorted(r["request_count"] for r in results) == list(range(1, THREADS + 1))
    assert _row(db_session, identifier, endpoint).request_count == THREADS


def test_record_failure_orm_concurrent_failures_block_on_reaching_the_maximum(
    db_session: Session, endpoint: str
):
    """El fallo número `max` bloquea; solo `max - 1` quedan permitidos y los demás no suman"""
    identifier = _identifier()
    maximum = 5

    results, errors = _run_concurrently(
        THREADS, lambda _i, db: _fail(db, identifier, endpoint, max_failures=maximum)
    )

    assert errors == []
    assert sum(1 for r in results if r["is_allowed"]) == maximum - 1
    row = _row(db_session, identifier, endpoint)
    assert row.request_count == maximum
    assert row.blocked_until is not None


def test_record_failure_orm_window_reset_happens_once_under_concurrency(
    db_session: Session, endpoint: str
):
    identifier = _identifier()
    for _ in range(5):
        _fail(db_session, identifier, endpoint)
    _expire_window(db_session, identifier, endpoint)

    results, errors = _run_concurrently(THREADS, lambda _i, db: _fail(db, identifier, endpoint))

    assert errors == []
    assert sorted(r["request_count"] for r in results) == list(range(1, THREADS + 1))
    assert _row(db_session, identifier, endpoint).request_count == THREADS
