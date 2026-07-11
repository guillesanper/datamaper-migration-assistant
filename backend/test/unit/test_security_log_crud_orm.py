"""
Unit tests for app.crud.security_log_crud module (ORM versions)

Tests for security log CRUD ORM functions:
- Log security events
- Get logs with filters
- Get logs by user
- Cleanup old logs
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.crud import security_log_crud
from app.models.orm import SecurityLog, User

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def test_user(db_session: Session):
    """Create a test user for security logs"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"testuser_security_{unique_id}",
        email=f"testuser_security_{unique_id}@example.com",
        password_hash="dummy_hash",
        is_verified=True,
        is_deleted=False,
        failed_login_attempts=0,
        created_at=now,
        updated_at=now,
        password_changed_at=now,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sample_logs(db_session: Session, test_user: User):
    """Create sample security logs for testing"""
    logs = []
    event_types = ["login_success", "login_failed", "rate_limit_exceeded", "password_changed"]
    severities = ["info", "warning", "error", "critical"]

    for i, (event_type, severity) in enumerate(zip(event_types, severities)):
        log_data = security_log_crud.log_event_orm(
            db_session,
            event_type=event_type,
            ip_address=f"192.168.1.{i}",
            username=test_user.username,
            user_id=str(test_user.id),
            endpoint=f"/api/test/{i}",
            details={"test_key": f"test_value_{i}"},
            severity=severity,
        )
        logs.append(log_data)

    return logs


# ============================================================================
# TESTS: LOG EVENT
# ============================================================================


def test_log_event_orm(db_session: Session):
    """Test logging a security event"""
    result = security_log_crud.log_event_orm(
        db_session,
        event_type="login_success",
        ip_address="192.168.1.100",
        username="testuser",
        endpoint="/api/auth/login",
        details={"browser": "Chrome", "os": "Windows"},
        severity="info",
    )

    assert result is not None
    assert "id" in result
    assert result["event_type"] == "login_success"
    assert result["ip_address"] == "192.168.1.100"
    assert result["username"] == "testuser"
    assert result["endpoint"] == "/api/auth/login"
    assert result["severity"] == "info"
    assert result["details"] == {"browser": "Chrome", "os": "Windows"}
    assert "created_at" in result


def test_log_event_orm_with_user_id(db_session: Session, test_user: User):
    """Test logging a security event with user_id"""
    result = security_log_crud.log_event_orm(
        db_session,
        event_type="password_changed",
        user_id=str(test_user.id),
        username=test_user.username,
        endpoint="/api/user/password",
        severity="warning",
    )

    assert result is not None
    assert result["event_type"] == "password_changed"
    assert result["user_id"] == str(test_user.id)
    assert result["username"] == test_user.username
    assert result["severity"] == "warning"


def test_log_event_orm_minimal(db_session: Session):
    """Test logging a security event with minimal data"""
    result = security_log_crud.log_event_orm(db_session, event_type="system_startup")

    assert result is not None
    assert result["event_type"] == "system_startup"
    assert result["severity"] == "info"  # Default severity


def test_log_event_orm_critical(db_session: Session):
    """Test logging a critical security event"""
    result = security_log_crud.log_event_orm(
        db_session,
        event_type="multiple_failed_logins",
        ip_address="10.0.0.1",
        username="admin",
        endpoint="/api/auth/login",
        details={"attempts": 5, "blocked": True},
        severity="critical",
    )

    assert result is not None
    assert result["severity"] == "critical"
    assert result["details"]["blocked"] == True


# ============================================================================
# TESTS: GET LOGS
# ============================================================================


def test_get_logs_orm_all(db_session: Session, sample_logs):
    """Test getting all logs without filters"""
    result = security_log_crud.get_logs_orm(db_session)

    # At least the 4 sample logs should be present
    assert len(result) >= 4
    # Check that our sample logs are present
    event_types = [log["event_type"] for log in result]
    assert "login_success" in event_types
    assert "login_failed" in event_types
    assert "rate_limit_exceeded" in event_types
    assert "password_changed" in event_types


def test_get_logs_orm_by_event_type(db_session: Session, sample_logs):
    """Test getting logs filtered by event_type"""
    result = security_log_crud.get_logs_orm(db_session, event_type="login_success")

    assert len(result) >= 1
    # All results should have the requested event_type
    for log in result:
        assert log["event_type"] == "login_success"


def test_get_logs_orm_by_severity(db_session: Session, sample_logs):
    """Test getting logs filtered by severity"""
    result = security_log_crud.get_logs_orm(db_session, severity="critical")

    assert len(result) >= 1
    # All results should have the requested severity
    for log in result:
        assert log["severity"] == "critical"


def test_get_logs_orm_by_user_id(db_session: Session, sample_logs, test_user: User):
    """Test getting logs filtered by user_id"""
    result = security_log_crud.get_logs_orm(db_session, user_id=str(test_user.id))

    assert len(result) == 4
    for log in result:
        assert log["user_id"] == str(test_user.id)


def test_get_logs_orm_by_username(db_session: Session, sample_logs, test_user: User):
    """Test getting logs filtered by username"""
    result = security_log_crud.get_logs_orm(db_session, username=test_user.username)

    assert len(result) == 4
    for log in result:
        assert log["username"] == test_user.username


def test_get_logs_orm_by_endpoint(db_session: Session, sample_logs):
    """Test getting logs filtered by endpoint"""
    result = security_log_crud.get_logs_orm(db_session, endpoint="/api/test/0")

    assert len(result) >= 1
    # All results should have the requested endpoint
    for log in result:
        assert log["endpoint"] == "/api/test/0"


def test_get_logs_orm_with_date_range(db_session: Session, test_user: User):
    """Test getting logs with date range filter"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    yesterday = now - timedelta(days=1)
    tomorrow = now + timedelta(days=1)

    # Create a log today
    created_log = security_log_crud.log_event_orm(
        db_session, event_type="test_event_date_range", user_id=str(test_user.id)
    )

    # Get logs from yesterday to tomorrow (filtering by our specific event)
    result = security_log_crud.get_logs_orm(
        db_session, event_type="test_event_date_range", start_date=yesterday, end_date=tomorrow
    )

    assert len(result) > 0
    # Verify our created log is in the results
    assert any(log["id"] == created_log["id"] for log in result)


def test_get_logs_orm_pagination(db_session: Session, sample_logs):
    """Test getting logs with pagination"""
    # Get first 2 logs
    result_page1 = security_log_crud.get_logs_orm(db_session, limit=2, offset=0)

    assert len(result_page1) == 2

    # Get next 2 logs
    result_page2 = security_log_crud.get_logs_orm(db_session, limit=2, offset=2)

    assert len(result_page2) == 2

    # Make sure pages are different
    assert result_page1[0]["id"] != result_page2[0]["id"]


def test_get_logs_orm_multiple_filters(db_session: Session, sample_logs, test_user: User):
    """Test getting logs with multiple filters"""
    result = security_log_crud.get_logs_orm(
        db_session, event_type="login_failed", severity="warning", user_id=str(test_user.id)
    )

    assert len(result) == 1
    assert result[0]["event_type"] == "login_failed"
    assert result[0]["severity"] == "warning"


# ============================================================================
# TESTS: GET BY USER
# ============================================================================


def test_get_by_user_orm(db_session: Session, sample_logs, test_user: User):
    """Test getting logs for a specific user"""
    result = security_log_crud.get_by_user_orm(db_session, user_id=str(test_user.id))

    assert len(result) == 4
    for log in result:
        assert log["user_id"] == str(test_user.id)


def test_get_by_user_orm_with_event_type_filter(db_session: Session, sample_logs, test_user: User):
    """Test getting logs for a specific user filtered by event_type"""
    result = security_log_crud.get_by_user_orm(
        db_session, user_id=str(test_user.id), event_type="login_success"
    )

    assert len(result) == 1
    assert result[0]["event_type"] == "login_success"
    assert result[0]["user_id"] == str(test_user.id)


def test_get_by_user_orm_with_severity_filter(db_session: Session, sample_logs, test_user: User):
    """Test getting logs for a specific user filtered by severity"""
    result = security_log_crud.get_by_user_orm(
        db_session, user_id=str(test_user.id), severity="error"
    )

    assert len(result) == 1
    assert result[0]["severity"] == "error"
    assert result[0]["user_id"] == str(test_user.id)


def test_get_by_user_orm_pagination(db_session: Session, sample_logs, test_user: User):
    """Test getting logs for a specific user with pagination"""
    # Get first 2 logs
    result_page1 = security_log_crud.get_by_user_orm(
        db_session, user_id=str(test_user.id), limit=2, offset=0
    )

    assert len(result_page1) == 2

    # Get next 2 logs
    result_page2 = security_log_crud.get_by_user_orm(
        db_session, user_id=str(test_user.id), limit=2, offset=2
    )

    assert len(result_page2) == 2


def test_get_by_user_orm_no_logs(db_session: Session):
    """Test getting logs for a user with no logs"""
    random_user_id = str(uuid.uuid4())
    result = security_log_crud.get_by_user_orm(db_session, user_id=random_user_id)

    assert len(result) == 0


# ============================================================================
# TESTS: CLEANUP
# ============================================================================


def test_cleanup_orm(db_session: Session, test_user: User):
    """Test cleaning up old logs"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Create old logs (100 days old)
    old_date = now - timedelta(days=100)
    for i in range(3):
        old_log = SecurityLog(
            event_type="old_event", user_id=test_user.id, severity="info", created_at=old_date
        )
        db_session.add(old_log)

    # Create a recent log
    security_log_crud.log_event_orm(
        db_session, event_type="recent_event", user_id=str(test_user.id), severity="info"
    )

    db_session.commit()

    # Clean up logs older than 90 days
    deleted_count = security_log_crud.cleanup_orm(db_session, days_old=90)

    assert deleted_count == 3

    # Verify recent log still exists
    remaining_logs = security_log_crud.get_logs_orm(db_session)
    assert len(remaining_logs) >= 1
    assert any(log["event_type"] == "recent_event" for log in remaining_logs)


def test_cleanup_orm_keep_critical(db_session: Session, test_user: User):
    """Test cleaning up old logs but keeping critical ones"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old_date = now - timedelta(days=100)

    # Create old info log
    old_info_log = SecurityLog(
        event_type="old_info_event", user_id=test_user.id, severity="info", created_at=old_date
    )
    db_session.add(old_info_log)

    # Create old critical log
    old_critical_log = SecurityLog(
        event_type="old_critical_event",
        user_id=test_user.id,
        severity="critical",
        created_at=old_date,
    )
    db_session.add(old_critical_log)

    db_session.commit()

    # Clean up logs older than 90 days but keep critical
    deleted_count = security_log_crud.cleanup_orm(db_session, days_old=90, severity_keep="critical")

    assert deleted_count == 1

    # Verify critical log still exists
    remaining_logs = security_log_crud.get_logs_orm(db_session, severity="critical")
    assert len(remaining_logs) >= 1
    assert any(log["event_type"] == "old_critical_event" for log in remaining_logs)


def test_cleanup_orm_all_severities(db_session: Session, test_user: User):
    """Test cleaning up old logs including all severities"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old_date = now - timedelta(days=100)

    # Create old logs with different severities with unique event types
    unique_id = str(uuid.uuid4())[:8]
    for severity in ["info", "warning", "error", "critical"]:
        old_log = SecurityLog(
            event_type=f"old_{severity}_event_{unique_id}",
            user_id=test_user.id,
            severity=severity,
            created_at=old_date,
        )
        db_session.add(old_log)

    db_session.commit()

    # Clean up all logs older than 90 days (no severity_keep)
    deleted_count = security_log_crud.cleanup_orm(db_session, days_old=90, severity_keep=None)

    # At least our 4 logs should be deleted
    assert deleted_count >= 4


def test_cleanup_orm_no_old_logs(db_session: Session):
    """Test cleanup when there are no old logs"""
    # Create a recent log
    security_log_crud.log_event_orm(db_session, event_type="recent_event", severity="info")

    # Try to clean up logs older than 90 days
    deleted_count = security_log_crud.cleanup_orm(db_session, days_old=90)

    assert deleted_count == 0


def test_cleanup_orm_custom_days(db_session: Session, test_user: User):
    """Test cleanup with custom days threshold"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Create log 60 days old
    old_date = now - timedelta(days=60)
    old_log = SecurityLog(
        event_type="old_event", user_id=test_user.id, severity="info", created_at=old_date
    )
    db_session.add(old_log)
    db_session.commit()

    # Clean up logs older than 30 days (should delete the 60-day-old log)
    deleted_count = security_log_crud.cleanup_orm(db_session, days_old=30)

    assert deleted_count == 1

    # Clean up logs older than 90 days (should delete nothing)
    deleted_count = security_log_crud.cleanup_orm(db_session, days_old=90)

    assert deleted_count == 0
