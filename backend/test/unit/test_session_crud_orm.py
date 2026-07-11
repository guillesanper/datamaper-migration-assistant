"""
Unit tests for app.crud.session_crud module (ORM versions)

Tests for session CRUD ORM functions:
- Create session
- Get session by token
- Update session activity
- Revoke session
- Get user sessions
- Cleanup expired sessions
- Revoke user session by ID
- Revoke all user sessions
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import session_crud, user_crud
from app.models.orm import UserSession

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def test_user(db_session: Session):
    """Create a verified test user"""
    unique_id = str(uuid.uuid4())[:8]
    user_data = user_crud.create_user_orm(
        db_session,
        username=f"session_user_{unique_id}",
        email=f"session_user_{unique_id}@example.com",
        password="TestPassword123!",
    )
    # Verify user
    user_crud.verify_user_email_orm(db_session, user_data["id"])
    return user_crud.get_user_by_id_orm(db_session, user_data["id"])


@pytest.fixture
def test_session(db_session: Session, test_user):
    """Create a test session"""
    session_data = session_crud.create_session_orm(
        db_session,
        user_id=test_user["id"],
        session_token=f"test_token_{uuid.uuid4().hex}",
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0 Test Browser",
        device_fingerprint="test_fingerprint_123",
        expires_in_hours=24,
    )
    return session_data


@pytest.fixture
def multiple_sessions(db_session: Session, test_user):
    """Create multiple test sessions for a user"""
    sessions = []
    for i in range(3):
        session_data = session_crud.create_session_orm(
            db_session,
            user_id=test_user["id"],
            session_token=f"multi_token_{i}_{uuid.uuid4().hex}",
            ip_address=f"192.168.1.{i+1}",
            user_agent=f"Browser {i}",
            expires_in_hours=24,
        )
        sessions.append(session_data)
    return sessions


# ============================================================================
# TESTS: CREATE SESSION
# ============================================================================


def test_create_session_orm(db_session: Session, test_user):
    """Test creating a new session"""
    session_token = f"new_session_{uuid.uuid4().hex}"

    result = session_crud.create_session_orm(
        db_session,
        user_id=test_user["id"],
        session_token=session_token,
        ip_address="10.0.0.1",
        user_agent="Test User Agent",
        device_fingerprint="fingerprint_456",
        expires_in_hours=48,
    )

    assert result is not None
    assert "id" in result
    assert result["user_id"] == test_user["id"]
    assert result["session_token"] == session_token
    assert result["ip_address"] == "10.0.0.1"
    assert result["user_agent"] == "Test User Agent"
    assert result["device_fingerprint"] == "fingerprint_456"
    assert result["is_revoked"] == False
    assert "created_at" in result
    assert "expires_at" in result


def test_create_session_with_refresh_token(db_session: Session, test_user):
    """Test creating a session with refresh token"""
    session_token = f"session_{uuid.uuid4().hex}"
    refresh_token = f"refresh_{uuid.uuid4().hex}"

    result = session_crud.create_session_orm(
        db_session,
        user_id=test_user["id"],
        session_token=session_token,
        refresh_token=refresh_token,
        expires_in_hours=24,
    )

    assert result is not None
    assert result["refresh_token"] == refresh_token


def test_create_duplicate_session_token(db_session: Session, test_user, test_session):
    """Test that duplicate session tokens raise IntegrityError"""
    with pytest.raises(IntegrityError):
        session_crud.create_session_orm(
            db_session,
            user_id=test_user["id"],
            session_token=test_session["session_token"],  # Duplicate
            expires_in_hours=24,
        )


# ============================================================================
# TESTS: GET SESSION BY TOKEN
# ============================================================================


def test_get_session_by_token_orm(db_session: Session, test_session):
    """Test retrieving a session by token"""
    result = session_crud.get_session_by_token_orm(db_session, test_session["session_token"])

    assert result is not None
    assert result["id"] == test_session["id"]
    assert result["session_token"] == test_session["session_token"]
    assert result["is_revoked"] == False


def test_get_session_by_token_nonexistent(db_session: Session):
    """Test retrieving a nonexistent session"""
    result = session_crud.get_session_by_token_orm(db_session, "nonexistent_token_123")

    assert result is None


def test_get_session_by_token_revoked(db_session: Session, test_session):
    """Test that revoked sessions are not returned"""
    # Revoke session
    session_crud.revoke_session_orm(db_session, test_session["session_token"], reason="test")

    # Try to get revoked session
    result = session_crud.get_session_by_token_orm(db_session, test_session["session_token"])

    assert result is None  # Should not return revoked sessions


def test_get_session_by_token_expired(db_session: Session, test_user):
    """Test that expired sessions are not returned"""
    # Create session that expires immediately
    from app.models.orm import UserSession

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expired_token = f"expired_{uuid.uuid4().hex}"

    expired_session = UserSession(
        id=uuid.uuid4(),
        user_id=test_user["id"],
        session_token=expired_token,
        created_at=now - timedelta(hours=25),
        last_activity=now - timedelta(hours=25),
        expires_at=now - timedelta(hours=1),  # Expired 1 hour ago
        is_revoked=False,
    )
    db_session.add(expired_session)
    db_session.commit()

    # Try to get expired session
    result = session_crud.get_session_by_token_orm(db_session, expired_token)

    assert result is None  # Should not return expired sessions


# ============================================================================
# TESTS: UPDATE SESSION ACTIVITY
# ============================================================================


def test_update_session_activity_orm(db_session: Session, test_session):
    """Test updating session activity timestamp"""
    import time

    time.sleep(0.1)  # Small delay to ensure different timestamp

    result = session_crud.update_session_activity_orm(db_session, test_session["session_token"])

    assert result == True

    # Verify last_activity was updated
    updated_session = session_crud.get_session_by_token_orm(
        db_session, test_session["session_token"]
    )
    assert updated_session["last_activity"] > test_session["last_activity"]


def test_update_session_activity_nonexistent(db_session: Session):
    """Test updating activity for nonexistent session"""
    result = session_crud.update_session_activity_orm(db_session, "nonexistent_token")

    assert result == False


def test_update_session_activity_revoked(db_session: Session, test_session):
    """Test that activity cannot be updated for revoked sessions"""
    # Revoke session
    session_crud.revoke_session_orm(db_session, test_session["session_token"])

    # Try to update activity
    result = session_crud.update_session_activity_orm(db_session, test_session["session_token"])

    assert result == False


# ============================================================================
# TESTS: REVOKE SESSION
# ============================================================================


def test_revoke_session_orm(db_session: Session, test_session):
    """Test revoking a session"""
    result = session_crud.revoke_session_orm(
        db_session, test_session["session_token"], reason="logout"
    )

    assert result == True

    # Verify session is revoked
    revoked_session = (
        db_session.query(UserSession)
        .filter(UserSession.session_token == test_session["session_token"])
        .first()
    )

    assert revoked_session.is_revoked == True
    assert revoked_session.revoked_at is not None
    assert revoked_session.revoked_reason == "logout"


def test_revoke_session_nonexistent(db_session: Session):
    """Test revoking a nonexistent session"""
    result = session_crud.revoke_session_orm(db_session, "nonexistent_token", reason="test")

    assert result == False


def test_revoke_session_already_revoked(db_session: Session, test_session):
    """Test revoking an already revoked session"""
    # Revoke first time
    session_crud.revoke_session_orm(db_session, test_session["session_token"], reason="first")

    # Try to revoke again
    result = session_crud.revoke_session_orm(
        db_session, test_session["session_token"], reason="second"
    )

    assert result == False  # Should fail because already revoked


# ============================================================================
# TESTS: REVOKE USER SESSION BY ID
# ============================================================================


def test_revoke_user_session_by_id_orm(db_session: Session, test_user, test_session):
    """Test revoking a specific session by ID"""
    result = session_crud.revoke_user_session_by_id_orm(
        db_session, user_id=test_user["id"], session_id=test_session["id"], reason="manual_revoke"
    )

    assert result == True

    # Verify session is revoked
    revoked_session = (
        db_session.query(UserSession).filter(UserSession.id == test_session["id"]).first()
    )

    assert revoked_session.is_revoked == True
    assert revoked_session.revoked_reason == "manual_revoke"


def test_revoke_user_session_by_id_wrong_user(db_session: Session, test_session):
    """Test that users cannot revoke sessions they don't own"""
    wrong_user_id = str(uuid.uuid4())

    result = session_crud.revoke_user_session_by_id_orm(
        db_session, user_id=wrong_user_id, session_id=test_session["id"], reason="unauthorized"
    )

    assert result == False  # Should fail


# ============================================================================
# TESTS: GET USER SESSIONS
# ============================================================================


def test_get_user_sessions_orm(db_session: Session, test_user, multiple_sessions):
    """Test getting all sessions for a user"""
    result = session_crud.get_user_sessions_orm(db_session, test_user["id"], active_only=True)

    assert len(result) == 3  # Should return all 3 active sessions
    assert all(s["user_id"] == test_user["id"] for s in result)
    assert all(s["is_revoked"] == False for s in result)


def test_get_user_sessions_active_only(db_session: Session, test_user, multiple_sessions):
    """Test getting only active sessions"""
    # Revoke one session
    session_crud.revoke_session_orm(db_session, multiple_sessions[0]["session_token"])

    # Get active sessions only
    result = session_crud.get_user_sessions_orm(db_session, test_user["id"], active_only=True)

    assert len(result) == 2  # Should return only 2 active sessions


def test_get_user_sessions_include_revoked(db_session: Session, test_user, multiple_sessions):
    """Test getting all sessions including revoked"""
    # Revoke one session
    session_crud.revoke_session_orm(db_session, multiple_sessions[0]["session_token"])

    # Get all sessions (including revoked)
    result = session_crud.get_user_sessions_orm(db_session, test_user["id"], active_only=False)

    assert len(result) == 3  # Should return all 3 sessions


def test_get_user_sessions_empty(db_session: Session):
    """Test getting sessions for user with no sessions"""
    fake_user_id = str(uuid.uuid4())

    result = session_crud.get_user_sessions_orm(db_session, fake_user_id, active_only=True)

    assert len(result) == 0


# ============================================================================
# TESTS: CLEANUP EXPIRED SESSIONS
# ============================================================================


def test_cleanup_expired_sessions_orm(db_session: Session, test_user):
    """Test cleaning up old expired sessions"""
    from app.models.orm import UserSession

    # Create old expired session
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old_expired_token = f"old_expired_{uuid.uuid4().hex}"

    old_session = UserSession(
        id=uuid.uuid4(),
        user_id=test_user["id"],
        session_token=old_expired_token,
        created_at=now - timedelta(days=40),
        last_activity=now - timedelta(days=40),
        expires_at=now - timedelta(days=35),  # Expired 35 days ago
        is_revoked=False,
    )
    db_session.add(old_session)

    # Create recently expired session (should not be deleted)
    recent_expired_token = f"recent_expired_{uuid.uuid4().hex}"

    recent_session = UserSession(
        id=uuid.uuid4(),
        user_id=test_user["id"],
        session_token=recent_expired_token,
        created_at=now - timedelta(days=2),
        last_activity=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),  # Expired 1 day ago
        is_revoked=False,
    )
    db_session.add(recent_session)
    db_session.commit()

    # Cleanup sessions older than 30 days
    deleted_count = session_crud.cleanup_expired_sessions_orm(db_session, days_old=30)

    assert deleted_count >= 1  # At least the old session should be deleted

    # Verify old session is gone
    old_check = (
        db_session.query(UserSession).filter(UserSession.session_token == old_expired_token).first()
    )
    assert old_check is None

    # Verify recent session still exists
    recent_check = (
        db_session.query(UserSession)
        .filter(UserSession.session_token == recent_expired_token)
        .first()
    )
    assert recent_check is not None


def test_cleanup_expired_sessions_revoked(db_session: Session, test_user):
    """Test cleanup also removes old revoked sessions"""
    from app.models.orm import UserSession

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old_revoked_token = f"old_revoked_{uuid.uuid4().hex}"

    old_revoked = UserSession(
        id=uuid.uuid4(),
        user_id=test_user["id"],
        session_token=old_revoked_token,
        created_at=now - timedelta(days=40),
        last_activity=now - timedelta(days=40),
        expires_at=now + timedelta(days=10),  # Still valid
        is_revoked=True,
        revoked_at=now - timedelta(days=35),  # Revoked 35 days ago
    )
    db_session.add(old_revoked)
    db_session.commit()

    # Cleanup
    deleted_count = session_crud.cleanup_expired_sessions_orm(db_session, days_old=30)

    assert deleted_count >= 1

    # Verify old revoked session is gone
    check = (
        db_session.query(UserSession).filter(UserSession.session_token == old_revoked_token).first()
    )
    assert check is None


# ============================================================================
# TESTS: REVOKE ALL USER SESSIONS
# ============================================================================


def test_revoke_all_user_sessions_orm(db_session: Session, test_user, multiple_sessions):
    """Test revoking all sessions for a user"""
    count = session_crud.revoke_all_user_sessions_orm(
        db_session, test_user["id"], reason="security"
    )

    assert count == 3  # All 3 sessions should be revoked

    # Verify all are revoked
    sessions = session_crud.get_user_sessions_orm(db_session, test_user["id"], active_only=True)
    assert len(sessions) == 0  # No active sessions


def test_revoke_all_user_sessions_except_current(db_session: Session, test_user, multiple_sessions):
    """Test revoking all sessions except current one"""
    current_token = multiple_sessions[0]["session_token"]

    count = session_crud.revoke_all_user_sessions_orm(
        db_session, test_user["id"], except_token=current_token, reason="logout_other_devices"
    )

    assert count == 2  # Only 2 should be revoked (excluding current)

    # Verify current session is still active
    current_session = session_crud.get_session_by_token_orm(db_session, current_token)
    assert current_session is not None
    assert current_session["is_revoked"] == False

    # Verify others are revoked
    sessions = session_crud.get_user_sessions_orm(db_session, test_user["id"], active_only=True)
    assert len(sessions) == 1


def test_revoke_all_user_sessions_no_sessions(db_session: Session):
    """Test revoking all sessions for user with no sessions"""
    fake_user_id = str(uuid.uuid4())

    count = session_crud.revoke_all_user_sessions_orm(db_session, fake_user_id, reason="test")

    assert count == 0
