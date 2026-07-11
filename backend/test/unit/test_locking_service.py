"""
Unit tests for app.services.locking_service module

Tests for locking service business logic:
- Acquire/release locks with activity logging
- Check lock status
- Renew locks
- Force unlock
- Get active locks
- User edit permissions
- Column-level locking helpers
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services import locking_service

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db():
    """Provide a mock database connection"""
    return MagicMock()


@pytest.fixture
def test_lock_data():
    """Provide test lock data"""
    return {
        "entity_id": "table_users",
        "entity_type": "table",
        "project_id": "proj_123",
        "user_id": "user_123",
    }


@pytest.fixture
def test_lock_record():
    """Provide a test lock record"""
    return {
        "id": "lock_123",
        "entity_id": "table_users",
        "entity_type": "table",
        "user_id": "user_123",
        "project_id": "proj_123",
        "acquired_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(minutes=15),
        "username": "testuser",
        "user_email": "test@example.com",
    }


# ============================================================================
# ACQUIRE LOCK TESTS
# ============================================================================


class TestAcquireLock:
    """Tests for acquire_lock()"""

    @patch("app.services.locking_service.activity_crud.create_activity_log_orm")
    @patch("app.services.locking_service.locks_crud.acquire_lock_orm")
    def test_acquire_lock_success(
        self, mock_acquire, mock_activity, mock_db, test_lock_data, test_lock_record
    ):
        """Test successful lock acquisition"""
        mock_acquire.return_value = test_lock_record

        result = locking_service.acquire_lock(
            mock_db,
            test_lock_data["entity_id"],
            test_lock_data["entity_type"],
            test_lock_data["project_id"],
            test_lock_data["user_id"],
        )

        assert result["success"] is True
        assert result["locked_by_another"] is False
        assert result["lock"] == test_lock_record

        # Verify activity was logged
        mock_activity.assert_called_once()
        call_args = mock_activity.call_args[1]
        assert call_args["activity_type"] == "lock_acquired"

    @patch("app.services.locking_service.locks_crud.get_lock_status_orm")
    @patch("app.services.locking_service.locks_crud.acquire_lock_orm")
    def test_acquire_lock_blocked(
        self, mock_acquire, mock_get_status, mock_db, test_lock_data, test_lock_record
    ):
        """Test lock acquisition blocked by another user"""
        mock_acquire.return_value = None  # Failed to acquire

        other_user_lock = test_lock_record.copy()
        other_user_lock["user_id"] = "other_user"
        mock_get_status.return_value = other_user_lock

        result = locking_service.acquire_lock(
            mock_db,
            test_lock_data["entity_id"],
            test_lock_data["entity_type"],
            test_lock_data["project_id"],
            test_lock_data["user_id"],
        )

        assert result["success"] is False
        assert result["locked_by_another"] is True
        assert result["current_lock"] == other_user_lock

        # Verify current lock status was fetched
        mock_get_status.assert_called_once()


# ============================================================================
# RELEASE LOCK TESTS
# ============================================================================


class TestReleaseLock:
    """Tests for release_lock()"""

    @patch("app.services.locking_service.activity_crud.create_activity_log_orm")
    @patch("app.services.locking_service.locks_crud.release_lock_orm")
    def test_release_lock_success(self, mock_release, mock_activity, mock_db, test_lock_data):
        """Test successful lock release"""
        mock_release.return_value = True

        result = locking_service.release_lock(
            mock_db,
            test_lock_data["entity_id"],
            test_lock_data["entity_type"],
            test_lock_data["project_id"],
            test_lock_data["user_id"],
        )

        assert result is True

        # Verify activity was logged
        mock_activity.assert_called_once()
        call_args = mock_activity.call_args[1]
        assert call_args["activity_type"] == "lock_released"

    @patch("app.services.locking_service.activity_crud.create_activity_log_orm")
    @patch("app.services.locking_service.locks_crud.release_lock_orm")
    def test_release_lock_failed(self, mock_release, mock_activity, mock_db, test_lock_data):
        """Test lock release failure"""
        mock_release.return_value = False

        result = locking_service.release_lock(
            mock_db,
            test_lock_data["entity_id"],
            test_lock_data["entity_type"],
            test_lock_data["project_id"],
            test_lock_data["user_id"],
        )

        assert result is False

        # Verify activity was NOT logged
        mock_activity.assert_not_called()


# ============================================================================
# CHECK LOCK STATUS TESTS
# ============================================================================


class TestCheckLockStatus:
    """Tests for check_lock_status()"""

    @patch("app.services.locking_service.locks_crud.get_lock_status_orm")
    def test_check_lock_status_unlocked(self, mock_get_status, mock_db):
        """Test status check for unlocked entity"""
        mock_get_status.return_value = None

        result = locking_service.check_lock_status(mock_db, "entity_123", "table", "user_123")

        assert result["is_locked"] is False
        assert result["is_locked_by_me"] is False
        assert result["can_edit"] is True
        assert result["lock"] is None

    @patch("app.services.locking_service.locks_crud.get_lock_status_orm")
    def test_check_lock_status_locked_by_me(self, mock_get_status, mock_db, test_lock_record):
        """Test status check when locked by current user"""
        mock_get_status.return_value = test_lock_record

        result = locking_service.check_lock_status(
            mock_db, "entity_123", "table", "user_123"  # Same as lock owner
        )

        assert result["is_locked"] is True
        assert result["is_locked_by_me"] is True
        assert result["can_edit"] is True
        assert result["lock"] == test_lock_record

    @patch("app.services.locking_service.locks_crud.get_lock_status_orm")
    def test_check_lock_status_locked_by_other(self, mock_get_status, mock_db, test_lock_record):
        """Test status check when locked by another user"""
        mock_get_status.return_value = test_lock_record

        result = locking_service.check_lock_status(
            mock_db, "entity_123", "table", "other_user"  # Different from lock owner
        )

        assert result["is_locked"] is True
        assert result["is_locked_by_me"] is False
        assert result["can_edit"] is False


# ============================================================================
# RENEW LOCK TESTS
# ============================================================================


class TestRenewLock:
    """Tests for renew_lock()"""

    @patch("app.services.locking_service.locks_crud.renew_lock_orm")
    def test_renew_lock_success(self, mock_renew, mock_db, test_lock_record):
        """Test successful lock renewal"""
        mock_renew.return_value = test_lock_record

        result = locking_service.renew_lock(mock_db, "lock_123", "user_123", duration_minutes=15)

        assert result == test_lock_record

        mock_renew.assert_called_once_with(mock_db, "lock_123", "user_123", 15)

    @patch("app.services.locking_service.locks_crud.renew_lock_orm")
    def test_renew_lock_failed(self, mock_renew, mock_db):
        """Test lock renewal failure"""
        mock_renew.return_value = None

        result = locking_service.renew_lock(mock_db, "lock_123", "user_123")

        assert result is None


# ============================================================================
# FORCE UNLOCK TESTS
# ============================================================================


class TestForceUnlock:
    """Tests for force_unlock()"""

    @patch("app.services.locking_service.activity_crud.create_activity_log_orm")
    @patch("app.services.locking_service.locks_crud.force_unlock_orm")
    @patch("app.services.locking_service.locks_crud.get_lock_status_orm")
    def test_force_unlock_success(
        self, mock_get_status, mock_force_unlock, mock_activity, mock_db, test_lock_record
    ):
        """Test successful force unlock"""
        mock_get_status.return_value = test_lock_record
        mock_force_unlock.return_value = True

        result = locking_service.force_unlock(
            mock_db, "entity_123", "table", "proj_123", "admin_user"
        )

        assert result is True

        # Verify activity was logged with metadata
        mock_activity.assert_called_once()
        call_args = mock_activity.call_args[1]
        assert call_args["activity_type"] == "lock_force_unlocked"
        assert "original_lock_user" in call_args["metadata"]
        assert "forced_by" in call_args["metadata"]

    @patch("app.services.locking_service.locks_crud.get_lock_status_orm")
    def test_force_unlock_no_lock(self, mock_get_status, mock_db):
        """Test force unlock when no lock exists"""
        mock_get_status.return_value = None

        result = locking_service.force_unlock(
            mock_db, "entity_123", "table", "proj_123", "admin_user"
        )

        assert result is False


# ============================================================================
# GET ACTIVE LOCKS TESTS
# ============================================================================


class TestGetActiveLocks:
    """Tests for get_active_locks()"""

    @patch("app.services.locking_service.locks_crud.get_active_locks_orm")
    def test_get_active_locks(self, mock_get_active, mock_db, test_lock_record):
        """Test getting active locks"""
        mock_get_active.return_value = [test_lock_record]

        result = locking_service.get_active_locks(mock_db, "proj_123")

        assert len(result) == 1
        assert result[0] == test_lock_record

        mock_get_active.assert_called_once_with(mock_db, "proj_123")


# ============================================================================
# CLEANUP EXPIRED LOCKS TESTS
# ============================================================================


class TestCleanupExpiredLocks:
    """Tests for cleanup_expired_locks()"""

    @patch("app.services.locking_service.locks_crud.cleanup_expired_locks_orm")
    def test_cleanup_expired_locks(self, mock_cleanup, mock_db):
        """Test cleanup of expired locks"""
        mock_cleanup.return_value = 5

        result = locking_service.cleanup_expired_locks(mock_db)

        assert result == 5

        mock_cleanup.assert_called_once_with(mock_db)


# ============================================================================
# CHECK USER CAN EDIT TESTS
# ============================================================================


class TestCheckUserCanEdit:
    """Tests for check_user_can_edit()"""

    @patch("app.services.locking_service.locks_crud.get_lock_status_orm")
    def test_check_user_can_edit_unlocked(self, mock_get_status, mock_db):
        """Test user can edit when entity is unlocked"""
        mock_get_status.return_value = None

        result = locking_service.check_user_can_edit(mock_db, "entity_123", "table", "user_123")

        assert result is True

    @patch("app.services.locking_service.locks_crud.get_lock_status_orm")
    def test_check_user_can_edit_locked_by_me(self, mock_get_status, mock_db, test_lock_record):
        """Test user can edit when they own the lock"""
        mock_get_status.return_value = test_lock_record

        result = locking_service.check_user_can_edit(
            mock_db, "entity_123", "table", "user_123"  # Same as lock owner
        )

        assert result is True

    @patch("app.services.locking_service.locks_crud.get_lock_status_orm")
    def test_check_user_cannot_edit_locked_by_other(
        self, mock_get_status, mock_db, test_lock_record
    ):
        """Test user cannot edit when locked by another user"""
        mock_get_status.return_value = test_lock_record

        result = locking_service.check_user_can_edit(
            mock_db, "entity_123", "table", "other_user"  # Different from lock owner
        )

        assert result is False


# ============================================================================
# COLUMN LOCK HELPER TESTS
# ============================================================================


class TestColumnLockHelpers:
    """Tests for column locking helper functions"""

    def test_make_column_entity_id(self):
        """Test creating column entity ID"""
        entity_id = locking_service.make_column_entity_id("users", "email")

        assert entity_id == "users:email"

    def test_parse_column_entity_id_valid(self):
        """Test parsing valid column entity ID"""
        result = locking_service.parse_column_entity_id("users:email")

        assert result == ("users", "email")

    def test_parse_column_entity_id_with_colon_in_column(self):
        """Test parsing column entity ID with colon in column name"""
        result = locking_service.parse_column_entity_id("users:full:name")

        assert result == ("users", "full:name")

    def test_parse_column_entity_id_invalid(self):
        """Test parsing invalid column entity ID"""
        result = locking_service.parse_column_entity_id("invalid_format")

        assert result is None


# ============================================================================
# COLUMN LOCK OPERATIONS TESTS
# ============================================================================


class TestColumnLockOperations:
    """Tests for column-specific lock operations"""

    @patch("app.services.locking_service.acquire_lock")
    def test_acquire_column_lock(self, mock_acquire, mock_db):
        """Test acquiring column lock"""
        mock_acquire.return_value = {"success": True, "lock": {"id": "lock_123"}}

        result = locking_service.acquire_column_lock(
            mock_db, "users", "email", "proj_123", "user_123", duration_minutes=5
        )

        assert result["success"] is True

        # Verify acquire_lock was called with column entity_id
        mock_acquire.assert_called_once()
        # Los argumentos se pasan como kwargs, no como args posicionales
        call_kwargs = mock_acquire.call_args.kwargs
        assert call_kwargs["entity_id"] == "users:email"
        assert call_kwargs["entity_type"] == "column"
        assert call_kwargs["duration_minutes"] == 5

    @patch("app.services.locking_service.release_lock")
    def test_release_column_lock(self, mock_release, mock_db):
        """Test releasing column lock"""
        mock_release.return_value = True

        result = locking_service.release_column_lock(
            mock_db, "users", "email", "proj_123", "user_123"
        )

        assert result is True

        # Verify release_lock was called with column entity_id
        mock_release.assert_called_once()
        # Los argumentos se pasan como kwargs, no como args posicionales
        call_kwargs = mock_release.call_args.kwargs
        assert call_kwargs["entity_id"] == "users:email"
        assert call_kwargs["entity_type"] == "column"

    @patch("app.services.locking_service.check_lock_status")
    def test_get_column_lock_status(self, mock_check, mock_db):
        """Test getting column lock status"""
        mock_check.return_value = {"is_locked": True, "is_locked_by_me": True, "can_edit": True}

        result = locking_service.get_column_lock_status(mock_db, "users", "email", "user_123")

        assert result["is_locked"] is True
        assert result["is_locked_by_me"] is True

        # Verify check_lock_status was called with column entity_id
        mock_check.assert_called_once()
        # Los argumentos se pasan como kwargs, no como args posicionales
        call_kwargs = mock_check.call_args.kwargs
        assert call_kwargs["entity_id"] == "users:email"
        assert call_kwargs["entity_type"] == "column"

    def test_acquire_column_lock_default_duration(self):
        """Test column lock uses shorter default duration"""
        with patch("app.services.locking_service.acquire_lock") as mock_acquire:
            mock_acquire.return_value = {"success": True}

            locking_service.acquire_column_lock(
                MagicMock(),
                "users",
                "email",
                "proj_123",
                "user_123",
                # No duration specified - should use default
            )

            # Verify default duration is 3 minutes for columns
            call_kwargs = mock_acquire.call_args[1]
            assert call_kwargs["duration_minutes"] == 3
