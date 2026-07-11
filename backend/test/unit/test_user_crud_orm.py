"""
Unit tests for app.crud.user_crud module (ORM versions)

Tests for user CRUD ORM functions:
- Create user
- Get user by ID, email, username
- Update user
- Password verification and update
- User authentication
- Email verification
- Activate/deactivate user
- Search and pagination
- User statistics
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import user_crud
from app.models.orm import Project, Subscription, User

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def test_user(db_session: Session):
    """Create a test user"""
    unique_id = str(uuid.uuid4())[:8]
    user_data = user_crud.create_user_orm(
        db_session,
        username=f"testuser_{unique_id}",
        email=f"testuser_{unique_id}@example.com",
        password="TestPassword123!",
    )
    return user_data


@pytest.fixture
def verified_user(db_session: Session):
    """Create a verified test user"""
    unique_id = str(uuid.uuid4())[:8]
    user_data = user_crud.create_user_orm(
        db_session,
        username=f"verified_{unique_id}",
        email=f"verified_{unique_id}@example.com",
        password="TestPassword123!",
    )
    # Verify the user
    user_crud.verify_user_email_orm(db_session, user_data["id"])
    # Refresh user data
    return user_crud.get_user_by_id_orm(db_session, user_data["id"])


@pytest.fixture
def multiple_users(db_session: Session):
    """Create multiple test users for search/pagination tests"""
    users = []
    for i in range(5):
        unique_id = str(uuid.uuid4())[:8]
        user_data = user_crud.create_user_orm(
            db_session,
            username=f"user_{i}_{unique_id}",
            email=f"user_{i}_{unique_id}@example.com",
            password="TestPassword123!",
        )
        users.append(user_data)
    return users


# ============================================================================
# TESTS: BASIC USER MANAGEMENT
# ============================================================================


def test_create_user_orm(db_session: Session):
    """Test creating a new user with password hashing"""
    unique_id = str(uuid.uuid4())[:8]
    username = f"newuser_{unique_id}"
    email = f"newuser_{unique_id}@example.com"
    password = "SecurePassword123!"

    result = user_crud.create_user_orm(
        db_session, username=username, email=email, password=password
    )

    assert result is not None
    assert "id" in result
    assert result["username"] == username
    assert result["email"] == email
    assert result["is_verified"] == False
    assert result["is_deleted"] == False
    assert "password_hash" not in result  # Should NOT return password_hash
    assert "created_at" in result
    assert "updated_at" in result


def test_create_duplicate_email(db_session: Session, test_user):
    """Test that creating a user with duplicate email raises IntegrityError"""
    unique_id = str(uuid.uuid4())[:8]

    with pytest.raises(IntegrityError):
        user_crud.create_user_orm(
            db_session,
            username=f"different_username_{unique_id}",
            email=test_user["email"],  # Duplicate email
            password="TestPassword123!",
        )


def test_create_duplicate_username(db_session: Session, test_user):
    """Test that creating a user with duplicate username raises IntegrityError"""
    unique_id = str(uuid.uuid4())[:8]

    with pytest.raises(IntegrityError):
        user_crud.create_user_orm(
            db_session,
            username=test_user["username"],  # Duplicate username
            email=f"different_email_{unique_id}@example.com",
            password="TestPassword123!",
        )


def test_get_user_by_id_orm(db_session: Session, test_user):
    """Test retrieving a user by ID"""
    result = user_crud.get_user_by_id_orm(db_session, test_user["id"])

    assert result is not None
    assert result["id"] == test_user["id"]
    assert result["username"] == test_user["username"]
    assert result["email"] == test_user["email"]
    assert "password_hash" not in result


def test_get_user_by_id_nonexistent(db_session: Session):
    """Test retrieving a nonexistent user by ID"""
    fake_id = str(uuid.uuid4())
    result = user_crud.get_user_by_id_orm(db_session, fake_id)

    assert result is None


def test_get_user_by_email_orm(db_session: Session, test_user):
    """Test retrieving a user by email"""
    result = user_crud.get_user_by_email_orm(db_session, test_user["email"])

    assert result is not None
    assert result["id"] == test_user["id"]
    assert result["email"] == test_user["email"]
    assert "password_hash" not in result


def test_get_user_by_email_nonexistent(db_session: Session):
    """Test retrieving a nonexistent user by email"""
    result = user_crud.get_user_by_email_orm(db_session, "nonexistent@example.com")

    assert result is None


def test_get_user_by_username_orm(db_session: Session, test_user):
    """Test retrieving a user by username"""
    result = user_crud.get_user_by_username_orm(db_session, test_user["username"])

    assert result is not None
    assert result["id"] == test_user["id"]
    assert result["username"] == test_user["username"]
    assert "password_hash" not in result


def test_get_user_by_username_nonexistent(db_session: Session):
    """Test retrieving a nonexistent user by username"""
    result = user_crud.get_user_by_username_orm(db_session, "nonexistent_user")

    assert result is None


def test_update_user_orm(db_session: Session, test_user):
    """Test updating user data"""
    new_username = f"updated_{test_user['username']}"

    result = user_crud.update_user_orm(db_session, test_user["id"], {"username": new_username})

    assert result == True

    # Verify update
    updated_user = user_crud.get_user_by_id_orm(db_session, test_user["id"])
    assert updated_user["username"] == new_username


def test_update_user_prevents_password_hash_update(db_session: Session, test_user):
    """Test that update_user_orm prevents direct password_hash updates"""
    # Try to update password_hash directly (should be ignored)
    result = user_crud.update_user_orm(
        db_session, test_user["id"], {"password_hash": "malicious_hash"}
    )

    assert result == True

    # Verify password_hash was NOT updated by checking authentication still works
    user_crud.verify_user_email_orm(db_session, test_user["id"])
    auth_result = user_crud.authenticate_user_orm(
        db_session, test_user["email"], "TestPassword123!"  # Original password
    )
    assert auth_result is not None  # Should still work with original password


# ============================================================================
# TESTS: PASSWORD MANAGEMENT
# ============================================================================


def test_verify_user_password_orm_correct(db_session: Session, test_user):
    """Test verifying correct password"""
    result = user_crud.verify_user_password_orm(db_session, test_user["id"], "TestPassword123!")

    assert result == True


def test_verify_user_password_orm_incorrect(db_session: Session, test_user):
    """Test verifying incorrect password"""
    result = user_crud.verify_user_password_orm(db_session, test_user["id"], "WrongPassword!")

    assert result == False


def test_verify_user_password_orm_nonexistent(db_session: Session):
    """Test verifying password for nonexistent user"""
    fake_id = str(uuid.uuid4())
    result = user_crud.verify_user_password_orm(db_session, fake_id, "AnyPassword")

    assert result == False


def test_update_user_password_orm(db_session: Session, test_user):
    """Test updating user password"""
    new_password = "NewSecurePassword456!"

    result = user_crud.update_user_password_orm(
        db_session, test_user["id"], new_password, old_password="TestPassword123!"
    )

    assert result == True

    # Verify new password works
    verify_result = user_crud.verify_user_password_orm(db_session, test_user["id"], new_password)
    assert verify_result == True

    # Verify old password doesn't work
    old_verify = user_crud.verify_user_password_orm(db_session, test_user["id"], "TestPassword123!")
    assert old_verify == False


def test_update_user_password_wrong_old_password(db_session: Session, test_user):
    """Test updating password with wrong old password"""
    result = user_crud.update_user_password_orm(
        db_session, test_user["id"], "NewPassword123!", old_password="WrongOldPassword!"
    )

    assert result == False

    # Verify original password still works
    verify_result = user_crud.verify_user_password_orm(
        db_session, test_user["id"], "TestPassword123!"
    )
    assert verify_result == True


def test_update_user_password_without_old_password(db_session: Session, test_user):
    """Test updating password without providing old password (admin reset)"""
    new_password = "AdminResetPassword789!"

    result = user_crud.update_user_password_orm(
        db_session, test_user["id"], new_password, old_password=None  # No validation
    )

    assert result == True

    # Verify new password works
    verify_result = user_crud.verify_user_password_orm(db_session, test_user["id"], new_password)
    assert verify_result == True


# ============================================================================
# TESTS: AUTHENTICATION
# ============================================================================


def test_authenticate_user_success(db_session: Session, verified_user):
    """Test successful user authentication"""
    result = user_crud.authenticate_user_orm(db_session, verified_user["email"], "TestPassword123!")

    assert result is not None
    assert result["id"] == verified_user["id"]
    assert result["email"] == verified_user["email"]
    assert result["is_verified"] == True
    assert "password_hash" not in result


def test_authenticate_user_with_username(db_session: Session, verified_user):
    """Test authentication using username instead of email"""
    result = user_crud.authenticate_user_orm(
        db_session, verified_user["username"], "TestPassword123!"
    )

    assert result is not None
    assert result["id"] == verified_user["id"]


def test_authenticate_user_wrong_password(db_session: Session, verified_user):
    """Test authentication with wrong password"""
    result = user_crud.authenticate_user_orm(db_session, verified_user["email"], "WrongPassword!")

    assert result is None


def test_authenticate_user_nonexistent(db_session: Session):
    """Test authentication with nonexistent user"""
    result = user_crud.authenticate_user_orm(db_session, "nonexistent@example.com", "AnyPassword")

    assert result is None


def test_authenticate_user_not_verified(db_session: Session, test_user):
    """Test that unverified users cannot authenticate"""
    result = user_crud.authenticate_user_orm(db_session, test_user["email"], "TestPassword123!")

    assert result is None  # Should fail because email not verified


def test_authenticate_user_failed_attempts_lockout(db_session: Session, verified_user):
    """Test that multiple failed login attempts lock the account"""
    # Import security settings to get lockout threshold
    from app.config.security import security_settings

    # Make multiple failed attempts
    for _ in range(security_settings.MAX_FAILED_LOGIN_ATTEMPTS):
        user_crud.authenticate_user_orm(db_session, verified_user["email"], "WrongPassword!")

    # Next attempt should be locked
    result = user_crud.authenticate_user_orm(
        db_session, verified_user["email"], "TestPassword123!"  # Even with correct password
    )

    assert result is None  # Should be locked


# ============================================================================
# TESTS: EMAIL VERIFICATION
# ============================================================================


def test_verify_user_email_orm(db_session: Session, test_user):
    """Test verifying user email"""
    result = user_crud.verify_user_email_orm(db_session, test_user["id"])

    assert result == True

    # Verify user is now verified
    updated_user = user_crud.get_user_by_id_orm(db_session, test_user["id"])
    assert updated_user["is_verified"] == True


def test_verify_user_email_nonexistent(db_session: Session):
    """Test verifying email for nonexistent user"""
    fake_id = str(uuid.uuid4())
    result = user_crud.verify_user_email_orm(db_session, fake_id)

    assert result == False


def test_request_email_verification_orm(db_session: Session, test_user):
    """Test requesting email verification for unverified user"""
    result = user_crud.request_email_verification_orm(db_session, test_user["id"])

    assert result == True


def test_request_email_verification_already_verified(db_session: Session, verified_user):
    """Test requesting verification for already verified user"""
    result = user_crud.request_email_verification_orm(db_session, verified_user["id"])

    assert result == False  # Should fail because already verified


# ============================================================================
# TESTS: ACTIVATE/DEACTIVATE USER
# ============================================================================


def test_deactivate_user_orm(db_session: Session, test_user):
    """Test deactivating a user (soft delete)"""
    result = user_crud.deactivate_user_orm(db_session, test_user["id"])

    assert result == True

    # Verify user cannot be retrieved (is_deleted = True)
    deactivated_user = user_crud.get_user_by_id_orm(db_session, test_user["id"])
    assert deactivated_user is None  # Should not return deleted users


def test_deactivate_user_nonexistent(db_session: Session):
    """Test deactivating a nonexistent user"""
    fake_id = str(uuid.uuid4())
    result = user_crud.deactivate_user_orm(db_session, fake_id)

    assert result == False


def test_activate_user_orm(db_session: Session, test_user):
    """Test reactivating a deactivated user"""
    # First deactivate
    user_crud.deactivate_user_orm(db_session, test_user["id"])

    # Then reactivate
    result = user_crud.activate_user_orm(db_session, test_user["id"])

    assert result == True

    # Verify user can be retrieved again
    reactivated_user = user_crud.get_user_by_id_orm(db_session, test_user["id"])
    assert reactivated_user is not None
    assert reactivated_user["id"] == test_user["id"]


def test_activate_user_nonexistent(db_session: Session):
    """Test reactivating a nonexistent user"""
    fake_id = str(uuid.uuid4())
    result = user_crud.activate_user_orm(db_session, fake_id)

    assert result == False


# ============================================================================
# TESTS: SEARCH AND PAGINATION
# ============================================================================


def test_search_users_orm(db_session: Session, multiple_users):
    """Test searching users by username or email"""
    # Search by partial username
    search_term = "user_0"
    results = user_crud.search_users_orm(db_session, search_term)

    assert len(results) >= 1
    assert all("password_hash" not in user for user in results)
    # At least one result should match the search term
    assert any(search_term in user["username"] or search_term in user["email"] for user in results)


def test_search_users_with_pagination(db_session: Session, multiple_users):
    """Test searching users with pagination"""
    results_page1 = user_crud.search_users_orm(db_session, "user_", limit=2, offset=0)
    results_page2 = user_crud.search_users_orm(db_session, "user_", limit=2, offset=2)

    assert len(results_page1) <= 2
    assert len(results_page2) <= 2

    # Page 1 and page 2 should have different users
    if len(results_page1) > 0 and len(results_page2) > 0:
        assert results_page1[0]["id"] != results_page2[0]["id"]


def test_search_users_include_deleted(db_session: Session, test_user):
    """Test searching users including deleted ones"""
    # Deactivate a user
    user_crud.deactivate_user_orm(db_session, test_user["id"])

    # Search without include_deleted
    results_active = user_crud.search_users_orm(
        db_session, test_user["username"], include_deleted=False
    )
    assert len(results_active) == 0

    # Search with include_deleted
    results_all = user_crud.search_users_orm(
        db_session, test_user["username"], include_deleted=True
    )
    assert len(results_all) >= 1


def test_get_all_users_paginated_orm(db_session: Session, multiple_users):
    """Test getting paginated list of all users"""
    result = user_crud.get_all_users_paginated_orm(db_session, limit=3, offset=0)

    assert "users" in result
    assert "total" in result
    assert "limit" in result
    assert "offset" in result
    assert len(result["users"]) <= 3
    assert result["total"] >= len(multiple_users)
    assert all("password_hash" not in user for user in result["users"])


def test_get_all_users_paginated_include_deleted(db_session: Session, test_user):
    """Test getting paginated users including deleted"""
    # Deactivate a user
    user_crud.deactivate_user_orm(db_session, test_user["id"])

    # Get without deleted
    result_active = user_crud.get_all_users_paginated_orm(db_session, include_deleted=False)

    # Get with deleted
    result_all = user_crud.get_all_users_paginated_orm(db_session, include_deleted=True)

    assert result_all["total"] > result_active["total"]


# ============================================================================
# TESTS: USER STATISTICS
# ============================================================================


def test_get_user_stats_orm(db_session: Session, verified_user):
    """Test getting user statistics"""
    result = user_crud.get_user_stats_orm(db_session, verified_user["id"])

    assert result is not None
    assert result["user_id"] == verified_user["id"]
    assert result["username"] == verified_user["username"]
    assert result["email"] == verified_user["email"]
    assert result["is_verified"] == True
    assert "projects_count" in result
    assert "active_subscriptions" in result
    assert "failed_login_attempts" in result
    assert "is_locked" in result
    assert result["is_locked"] == False  # Should not be locked initially


def test_get_user_stats_nonexistent(db_session: Session):
    """Test getting stats for nonexistent user"""
    fake_id = str(uuid.uuid4())
    result = user_crud.get_user_stats_orm(db_session, fake_id)

    assert result is None


def test_get_user_stats_with_projects(db_session: Session, verified_user):
    """Test user stats includes project count"""
    # Create a project for the user
    project = Project(
        id=uuid.uuid4(),
        name="Test Project",
        description="Test",
        origin_db="postgres",
        destination_db="mysql",
        owner_id=verified_user["id"],
        status="active",
    )
    db_session.add(project)
    db_session.commit()

    result = user_crud.get_user_stats_orm(db_session, verified_user["id"])

    assert result is not None
    assert result["projects_count"] >= 1


# ============================================================================
# EDGE CASES AND SECURITY
# ============================================================================


def test_create_user_password_not_stored_plaintext(db_session: Session):
    """Test that passwords are hashed and never stored in plaintext"""
    unique_id = str(uuid.uuid4())[:8]
    password = "PlaintextPassword123!"

    user_data = user_crud.create_user_orm(
        db_session,
        username=f"security_test_{unique_id}",
        email=f"security_{unique_id}@example.com",
        password=password,
    )

    # Check that the returned data doesn't include password
    assert "password" not in user_data
    assert "password_hash" not in user_data

    # Verify in database that password is hashed
    from app.models.orm import User

    user_db = db_session.query(User).filter(User.id == user_data["id"]).first()
    assert user_db.password_hash != password  # Should be hashed, not plaintext
    assert user_db.password_hash.startswith("$2b$")  # bcrypt hash format


def test_get_user_never_returns_password_hash(db_session: Session, test_user):
    """Test that all get functions never return password_hash"""
    user_by_id = user_crud.get_user_by_id_orm(db_session, test_user["id"])
    user_by_email = user_crud.get_user_by_email_orm(db_session, test_user["email"])
    user_by_username = user_crud.get_user_by_username_orm(db_session, test_user["username"])

    assert "password_hash" not in user_by_id
    assert "password_hash" not in user_by_email
    assert "password_hash" not in user_by_username
