"""
Unit tests for app.crud.rate_limit_crud module (ORM versions)

Tests for rate limit CRUD ORM functions:
- Check rate limit (create, verify, block)
- Update rate limit counters
- Get rate limit info
- Reset rate limit
- Cleanup old records
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.crud import rate_limit_crud
from app.models.orm import SecurityRateLimit

# ============================================================================
# TESTS: CHECK LIMIT
# ============================================================================


def test_check_limit_orm_first_request(db_session: Session):
    """Test checking rate limit for the first request"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    result = rate_limit_crud.check_limit_orm(
        db_session,
        identifier=identifier,
        ip_address=ip_address,
        endpoint=endpoint,
        max_requests=10,
        window_minutes=60,
    )

    assert result is not None
    assert result["is_allowed"] == True
    assert result["is_blocked"] == False
    assert result["remaining"] == 9
    assert result["request_count"] == 1
    assert result["blocked_until"] is None
    assert result["reset_at"] is not None


def test_check_limit_orm_within_limit(db_session: Session):
    """Test multiple requests within the limit"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Make 5 requests
    for i in range(5):
        result = rate_limit_crud.check_limit_orm(
            db_session,
            identifier=identifier,
            ip_address=ip_address,
            endpoint=endpoint,
            max_requests=10,
            window_minutes=60,
        )

        assert result["is_allowed"] == True
        assert result["is_blocked"] == False
        assert result["request_count"] == i + 1
        assert result["remaining"] == 10 - (i + 1)


def test_check_limit_orm_exceed_limit(db_session: Session):
    """Test exceeding the rate limit and getting blocked"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Make requests up to the limit
    for i in range(10):
        rate_limit_crud.check_limit_orm(
            db_session,
            identifier=identifier,
            ip_address=ip_address,
            endpoint=endpoint,
            max_requests=10,
            window_minutes=60,
            block_duration_minutes=15,
        )

    # The 11th request should exceed the limit and block
    result = rate_limit_crud.check_limit_orm(
        db_session,
        identifier=identifier,
        ip_address=ip_address,
        endpoint=endpoint,
        max_requests=10,
        window_minutes=60,
        block_duration_minutes=15,
    )

    assert result["is_allowed"] == False
    assert result["is_blocked"] == True
    assert result["remaining"] == 0
    assert result["blocked_until"] is not None


def test_check_limit_orm_blocked_request(db_session: Session):
    """Test that blocked identifier cannot make requests"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Exceed limit to get blocked
    for i in range(11):
        rate_limit_crud.check_limit_orm(
            db_session,
            identifier=identifier,
            ip_address=ip_address,
            endpoint=endpoint,
            max_requests=10,
            window_minutes=60,
            block_duration_minutes=15,
        )

    # Try another request while blocked
    result = rate_limit_crud.check_limit_orm(
        db_session,
        identifier=identifier,
        ip_address=ip_address,
        endpoint=endpoint,
        max_requests=10,
        window_minutes=60,
    )

    assert result["is_allowed"] == False
    assert result["is_blocked"] == True


def test_check_limit_orm_window_expired(db_session: Session):
    """Test that counter resets when window expires"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Make some requests
    for i in range(5):
        rate_limit_crud.check_limit_orm(
            db_session,
            identifier=identifier,
            ip_address=ip_address,
            endpoint=endpoint,
            max_requests=10,
            window_minutes=60,
        )

    # Manually expire the window
    rate_limit = (
        db_session.query(SecurityRateLimit)
        .filter(SecurityRateLimit.identifier == identifier, SecurityRateLimit.endpoint == endpoint)
        .first()
    )

    now = datetime.now(timezone.utc)
    rate_limit.window_start = now - timedelta(minutes=61)
    db_session.commit()

    # Next request should reset the counter
    result = rate_limit_crud.check_limit_orm(
        db_session,
        identifier=identifier,
        ip_address=ip_address,
        endpoint=endpoint,
        max_requests=10,
        window_minutes=60,
    )

    assert result["is_allowed"] == True
    assert result["request_count"] == 1
    assert result["remaining"] == 9


def test_check_limit_orm_different_endpoints(db_session: Session):
    """Test that rate limits are separate per endpoint"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"

    # Make requests to endpoint 1
    result1 = rate_limit_crud.check_limit_orm(
        db_session,
        identifier=identifier,
        ip_address=ip_address,
        endpoint="/api/endpoint1",
        max_requests=10,
        window_minutes=60,
    )

    # Make requests to endpoint 2
    result2 = rate_limit_crud.check_limit_orm(
        db_session,
        identifier=identifier,
        ip_address=ip_address,
        endpoint="/api/endpoint2",
        max_requests=10,
        window_minutes=60,
    )

    # Both should be allowed and have separate counters
    assert result1["is_allowed"] == True
    assert result1["request_count"] == 1
    assert result2["is_allowed"] == True
    assert result2["request_count"] == 1


# ============================================================================
# TESTS: UPDATE
# ============================================================================


def test_update_orm(db_session: Session):
    """Test updating rate limit counter"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Create initial rate limit record
    rate_limit_crud.check_limit_orm(
        db_session, identifier=identifier, ip_address=ip_address, endpoint=endpoint
    )

    # Update the counter
    success = rate_limit_crud.update_orm(
        db_session, identifier=identifier, endpoint=endpoint, increment=5
    )

    assert success == True

    # Verify the counter was updated
    info = rate_limit_crud.get_info_orm(db_session, identifier, endpoint)
    assert info is not None
    assert info["request_count"] == 6  # Initial 1 + increment 5


def test_update_orm_non_existent(db_session: Session):
    """Test updating non-existent rate limit record"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    endpoint = "/api/test"

    success = rate_limit_crud.update_orm(
        db_session, identifier=identifier, endpoint=endpoint, increment=1
    )

    assert success == False


def test_update_orm_multiple_increments(db_session: Session):
    """Test multiple incremental updates"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Create initial rate limit record
    rate_limit_crud.check_limit_orm(
        db_session, identifier=identifier, ip_address=ip_address, endpoint=endpoint
    )

    # Update multiple times
    for i in range(3):
        rate_limit_crud.update_orm(
            db_session, identifier=identifier, endpoint=endpoint, increment=2
        )

    # Verify the total count
    info = rate_limit_crud.get_info_orm(db_session, identifier, endpoint)
    assert info["request_count"] == 7  # Initial 1 + (3 * 2)


# ============================================================================
# TESTS: GET INFO
# ============================================================================


def test_get_info_orm(db_session: Session):
    """Test getting rate limit information"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Create rate limit record
    rate_limit_crud.check_limit_orm(
        db_session, identifier=identifier, ip_address=ip_address, endpoint=endpoint
    )

    # Get info
    info = rate_limit_crud.get_info_orm(db_session, identifier, endpoint)

    assert info is not None
    assert info["identifier"] == identifier
    assert info["ip_address"] == ip_address
    assert info["endpoint"] == endpoint
    assert info["request_count"] == 1
    assert "window_start" in info
    assert "last_attempt" in info


def test_get_info_orm_non_existent(db_session: Session):
    """Test getting info for non-existent rate limit"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    endpoint = "/api/test"

    info = rate_limit_crud.get_info_orm(db_session, identifier, endpoint)

    assert info is None


def test_get_info_orm_after_updates(db_session: Session):
    """Test getting info after multiple updates"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Create and update
    rate_limit_crud.check_limit_orm(
        db_session, identifier=identifier, ip_address=ip_address, endpoint=endpoint
    )

    for i in range(3):
        rate_limit_crud.check_limit_orm(
            db_session, identifier=identifier, ip_address=ip_address, endpoint=endpoint
        )

    # Get info
    info = rate_limit_crud.get_info_orm(db_session, identifier, endpoint)

    assert info is not None
    assert info["request_count"] == 4


# ============================================================================
# TESTS: RESET
# ============================================================================


def test_reset_orm(db_session: Session):
    """Test resetting rate limit counter"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Create rate limit with multiple requests
    for i in range(5):
        rate_limit_crud.check_limit_orm(
            db_session, identifier=identifier, ip_address=ip_address, endpoint=endpoint
        )

    # Reset
    success = rate_limit_crud.reset_orm(db_session, identifier, endpoint)

    assert success == True

    # Verify reset
    info = rate_limit_crud.get_info_orm(db_session, identifier, endpoint)
    assert info["request_count"] == 0
    assert info["attempt_count"] == 0
    assert info["blocked_until"] is None


def test_reset_orm_blocked(db_session: Session):
    """Test resetting a blocked rate limit"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Exceed limit to get blocked
    for i in range(11):
        rate_limit_crud.check_limit_orm(
            db_session,
            identifier=identifier,
            ip_address=ip_address,
            endpoint=endpoint,
            max_requests=10,
            window_minutes=60,
        )

    # Verify blocked
    info_before = rate_limit_crud.get_info_orm(db_session, identifier, endpoint)
    assert info_before["blocked_until"] is not None

    # Reset
    rate_limit_crud.reset_orm(db_session, identifier, endpoint)

    # Verify unblocked
    info_after = rate_limit_crud.get_info_orm(db_session, identifier, endpoint)
    assert info_after["request_count"] == 0
    assert info_after["blocked_until"] is None


def test_reset_orm_non_existent(db_session: Session):
    """Test resetting non-existent rate limit"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    endpoint = "/api/test"

    success = rate_limit_crud.reset_orm(db_session, identifier, endpoint)

    assert success == False


def test_reset_orm_and_new_requests(db_session: Session):
    """Test that after reset, new requests work normally"""
    unique_id = str(uuid.uuid4())[:8]
    identifier = f"user_{unique_id}@example.com"
    ip_address = f"192.168.1.{unique_id[:3]}"
    endpoint = "/api/test"

    # Make some requests
    for i in range(5):
        rate_limit_crud.check_limit_orm(
            db_session, identifier=identifier, ip_address=ip_address, endpoint=endpoint
        )

    # Reset
    rate_limit_crud.reset_orm(db_session, identifier, endpoint)

    # Make new request
    result = rate_limit_crud.check_limit_orm(
        db_session, identifier=identifier, ip_address=ip_address, endpoint=endpoint, max_requests=10
    )

    # Should work normally after reset
    assert result["is_allowed"] == True
    # Note: check_limit increments from 0, so it will be 1
    info = rate_limit_crud.get_info_orm(db_session, identifier, endpoint)
    assert info["request_count"] == 1


# ============================================================================
# TESTS: CLEANUP
# ============================================================================


def test_cleanup_orm(db_session: Session):
    """Test cleaning up old rate limit records"""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=40)

    unique_id = str(uuid.uuid4())[:8]

    # Create old rate limit record
    old_record = SecurityRateLimit(
        identifier=f"old_{unique_id}@example.com",
        ip_address=f"192.168.1.{unique_id[:3]}",
        endpoint="/api/old",
        request_count=5,
        attempt_count=5,
        window_start=old_date,
        last_attempt=old_date,
        created_at=old_date,
        updated_at=old_date,
    )
    db_session.add(old_record)

    # Create recent rate limit record
    rate_limit_crud.check_limit_orm(
        db_session,
        identifier=f"recent_{unique_id}@example.com",
        ip_address=f"192.168.2.{unique_id[:3]}",
        endpoint="/api/recent",
    )

    db_session.commit()

    # Cleanup records older than 30 days
    deleted_count = rate_limit_crud.cleanup_orm(db_session, days_old=30)

    assert deleted_count >= 1

    # Verify old record was deleted
    old_info = rate_limit_crud.get_info_orm(db_session, f"old_{unique_id}@example.com", "/api/old")
    assert old_info is None

    # Verify recent record still exists
    recent_info = rate_limit_crud.get_info_orm(
        db_session, f"recent_{unique_id}@example.com", "/api/recent"
    )
    assert recent_info is not None


def test_cleanup_orm_keep_blocked(db_session: Session):
    """Test that cleanup keeps blocked records"""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=40)

    unique_id = str(uuid.uuid4())[:8]

    # Create old but currently blocked record
    blocked_record = SecurityRateLimit(
        identifier=f"blocked_{unique_id}@example.com",
        ip_address=f"192.168.1.{unique_id[:3]}",
        endpoint="/api/blocked",
        request_count=100,
        attempt_count=100,
        window_start=old_date,
        last_attempt=old_date,
        created_at=old_date,
        updated_at=old_date,
        blocked_until=now + timedelta(hours=1),  # Still blocked
    )
    db_session.add(blocked_record)
    db_session.commit()

    # Cleanup
    deleted_count = rate_limit_crud.cleanup_orm(db_session, days_old=30)

    # Blocked record should NOT be deleted
    blocked_info = rate_limit_crud.get_info_orm(
        db_session, f"blocked_{unique_id}@example.com", "/api/blocked"
    )
    assert blocked_info is not None


def test_cleanup_orm_no_old_records(db_session: Session):
    """Test cleanup when there are no old records"""
    unique_id = str(uuid.uuid4())[:8]

    # Create only recent record
    rate_limit_crud.check_limit_orm(
        db_session,
        identifier=f"recent_{unique_id}@example.com",
        ip_address=f"192.168.1.{unique_id[:3]}",
        endpoint="/api/recent",
    )

    # Cleanup
    deleted_count = rate_limit_crud.cleanup_orm(db_session, days_old=30)

    # Should delete nothing (or only other old test data)
    # We can't assert exact count due to parallel tests
    assert deleted_count >= 0


def test_cleanup_orm_custom_days(db_session: Session):
    """Test cleanup with custom days threshold"""
    now = datetime.now(timezone.utc)

    unique_id = str(uuid.uuid4())[:8]

    # Create record 20 days old
    record_20_days = SecurityRateLimit(
        identifier=f"user20_{unique_id}@example.com",
        ip_address=f"192.168.1.{unique_id[:3]}",
        endpoint="/api/test",
        request_count=5,
        attempt_count=5,
        window_start=now - timedelta(days=20),
        last_attempt=now - timedelta(days=20),
        created_at=now - timedelta(days=20),
        updated_at=now - timedelta(days=20),
    )
    db_session.add(record_20_days)
    db_session.commit()

    # Cleanup with 10 days threshold (should delete 20-day-old record)
    deleted_count = rate_limit_crud.cleanup_orm(db_session, days_old=10)
    assert deleted_count >= 1

    # Verify record was deleted
    info = rate_limit_crud.get_info_orm(db_session, f"user20_{unique_id}@example.com", "/api/test")
    assert info is None


# ============================================================================
# TESTS: PEEK Y REGISTRO DE FALLOS (login: solo cuentan los fallos)
# ============================================================================


def _failure_keys() -> dict:
    """Claves únicas de un contador de fallos (identifier == ip_address, como en el limitador)"""
    unique_id = str(uuid.uuid4())[:8]
    return {
        "identifier": f"ip_{unique_id}",
        "ip_address": f"ip_{unique_id}",
        "endpoint": "/api/test/login",
    }


def _record_failure(db_session: Session, keys: dict, max_failures: int = 5) -> dict:
    return rate_limit_crud.record_failure_orm(
        db_session,
        **keys,
        max_failures=max_failures,
        window_minutes=15,
        block_duration_minutes=15,
    )


def _peek(db_session: Session, keys: dict) -> dict:
    return rate_limit_crud.peek_limit_orm(
        db_session, identifier=keys["identifier"], endpoint=keys["endpoint"]
    )


def test_peek_limit_orm_without_record_is_not_blocked_and_creates_nothing(db_session: Session):
    keys = _failure_keys()

    result = _peek(db_session, keys)

    assert result["is_allowed"] is True
    assert result["is_blocked"] is False
    assert result["blocked_until"] is None
    assert rate_limit_crud.get_info_orm(db_session, keys["identifier"], keys["endpoint"]) is None


def test_peek_limit_orm_never_counts(db_session: Session):
    keys = _failure_keys()
    _record_failure(db_session, keys)

    for _ in range(10):
        _peek(db_session, keys)

    info = rate_limit_crud.get_info_orm(db_session, keys["identifier"], keys["endpoint"])
    assert info["request_count"] == 1


def test_record_failure_orm_first_failure_creates_the_record(db_session: Session):
    keys = _failure_keys()

    result = _record_failure(db_session, keys)

    assert result["is_allowed"] is True
    assert result["is_blocked"] is False
    assert result["request_count"] == 1
    assert result["remaining"] == 4
    assert result["blocked_until"] is None


def test_record_failure_orm_failures_below_the_maximum_do_not_block(db_session: Session):
    keys = _failure_keys()

    for failure in range(1, 5):
        result = _record_failure(db_session, keys, max_failures=5)

        assert result["is_blocked"] is False
        assert result["request_count"] == failure

    assert _peek(db_session, keys)["is_blocked"] is False


def test_record_failure_orm_blocks_on_reaching_the_maximum(db_session: Session):
    """El fallo número `max` ya bloquea: la siguiente petición (aunque sea buena) se rechaza"""
    keys = _failure_keys()

    for _ in range(4):
        _record_failure(db_session, keys, max_failures=5)
    result = _record_failure(db_session, keys, max_failures=5)

    assert result["is_blocked"] is True
    assert result["is_allowed"] is False
    assert result["request_count"] == 5
    assert result["blocked_until"] is not None
    peeked = _peek(db_session, keys)
    assert peeked["is_blocked"] is True
    assert peeked["blocked_until"] == result["blocked_until"]


def test_record_failure_orm_with_maximum_one_blocks_on_the_first_failure(db_session: Session):
    keys = _failure_keys()

    result = _record_failure(db_session, keys, max_failures=1)

    assert result["is_blocked"] is True
    assert _peek(db_session, keys)["is_blocked"] is True


def test_record_failure_orm_does_not_count_while_blocked(db_session: Session):
    keys = _failure_keys()
    for _ in range(5):
        blocked = _record_failure(db_session, keys, max_failures=5)

    again = _record_failure(db_session, keys, max_failures=5)

    assert again["is_blocked"] is True
    assert again["request_count"] == 5
    assert again["blocked_until"] == blocked["blocked_until"]


def test_record_failure_orm_restarts_the_count_when_the_window_expires(db_session: Session):
    keys = _failure_keys()
    for _ in range(3):
        _record_failure(db_session, keys, max_failures=5)
    rate_limit = (
        db_session.query(SecurityRateLimit)
        .filter(
            SecurityRateLimit.identifier == keys["identifier"],
            SecurityRateLimit.endpoint == keys["endpoint"],
        )
        .first()
    )
    rate_limit.window_start = datetime.now(timezone.utc) - timedelta(minutes=16)
    db_session.commit()

    result = _record_failure(db_session, keys, max_failures=5)

    assert result["is_blocked"] is False
    assert result["request_count"] == 1


def test_peek_limit_orm_ignores_a_block_that_already_expired(db_session: Session):
    keys = _failure_keys()
    for _ in range(5):
        _record_failure(db_session, keys, max_failures=5)
    rate_limit = (
        db_session.query(SecurityRateLimit)
        .filter(
            SecurityRateLimit.identifier == keys["identifier"],
            SecurityRateLimit.endpoint == keys["endpoint"],
        )
        .first()
    )
    rate_limit.blocked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    result = _peek(db_session, keys)

    assert result["is_allowed"] is True
    assert result["is_blocked"] is False


def test_record_failure_orm_is_separate_per_endpoint(db_session: Session):
    keys = _failure_keys()
    for _ in range(5):
        _record_failure(db_session, keys, max_failures=5)
    other = {**keys, "endpoint": "/api/test/other"}

    assert _peek(db_session, keys)["is_blocked"] is True
    assert _peek(db_session, other)["is_blocked"] is False
