"""
Unit tests for app.services.auth_service module

Tests for AuthService:
- User creation
- User authentication
- Email verification
- Password reset
- Password strength validation
- Failed login handling
- Account lockout
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from app.services.auth_service import AuthenticationError, AuthService, DatabaseError

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db():
    """Provide a mock SQLAlchemy session"""
    db = MagicMock()
    db.query = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.refresh = MagicMock()
    return db


@pytest.fixture
def auth_service(mock_db):
    """Provide an AuthService instance"""
    return AuthService(mock_db)


@pytest.fixture
def test_user_data():
    """Provide test user data"""
    return {"username": "testuser", "email": "test@example.com", "password": "SecurePass123!"}


@pytest.fixture
def test_user_db_record():
    """Provide a test user database record"""
    return {
        "id": "user_12345",
        "username": "testuser",
        "email": "test@example.com",
        "password_hash": "$2b$12$hashedpassword",
        "is_verified": True,
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }


@pytest.fixture
def strong_password():
    """Provide a strong password"""
    return "MyVerySecurePass123!"


@pytest.fixture
def weak_password_short():
    """Provide a weak password (too short)"""
    return "Short1!"


@pytest.fixture
def weak_password_no_upper():
    """Provide a weak password (no uppercase)"""
    return "lowercasepass123!"


# ============================================================================
# PASSWORD STRENGTH VALIDATION TESTS
# ============================================================================


class TestPasswordStrengthValidation:
    """Tests for validate_password_strength()"""

    @patch("app.services.auth_service.SecurityUtils.validate_password_strength")
    def test_strong_password_valid(self, mock_validate, auth_service, strong_password):
        """Test that strong password passes validation"""
        mock_validate.return_value = {"is_valid": True, "errors": []}

        # Should not raise
        auth_service.validate_password_strength(strong_password)

        mock_validate.assert_called_once_with(strong_password)

    @patch("app.services.auth_service.SecurityUtils.validate_password_strength")
    def test_weak_password_invalid(self, mock_validate, auth_service, weak_password_short):
        """Test that weak password raises ValueError"""
        mock_validate.return_value = {
            "is_valid": False,
            "errors": ["Password too short", "Missing special characters"],
        }

        with pytest.raises(ValueError, match="Password too short"):
            auth_service.validate_password_strength(weak_password_short)


# ============================================================================
# USER CREATION TESTS
# ============================================================================


class TestCreateUser:
    """Tests for create_user() - SQLAlchemy ORM"""

    @patch("app.services.auth_service.send_verification_code")
    @patch("app.services.auth_service.SecurityUtils")
    @patch("app.services.auth_service.pwd_context.hash")
    @patch("app.services.auth_service.uuid.uuid4")
    def test_create_user_success(
        self,
        mock_uuid,
        mock_hash,
        mock_security_utils,
        mock_send_code,
        auth_service,
        mock_db,
        test_user_data,
    ):
        """Test successful user creation"""
        # Setup mocks
        mock_uuid.return_value = uuid.UUID("12345678-1234-5678-1234-567812345678")
        mock_hash.return_value = "hashed_password"
        mock_security_utils.validate_password_strength.return_value = {
            "is_valid": True,
            "errors": [],
        }
        mock_security_utils.sanitize_input.side_effect = lambda x: x
        mock_security_utils.sanitize_email.side_effect = lambda x: x

        # Mock refresh to set the attributes on the user
        def mock_refresh_side_effect(user):
            user.id = "12345678-1234-5678-1234-567812345678"
            user.username = "testuser"
            user.email = "test@example.com"

        mock_db.refresh.side_effect = mock_refresh_side_effect

        result = auth_service.create_user(
            test_user_data["username"], test_user_data["email"], test_user_data["password"]
        )

        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"
        assert "user_id" in result

        # Verify db.add and db.commit were called
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify verification code was sent
        mock_send_code.assert_called_once()

    @patch("app.services.auth_service.SecurityUtils")
    def test_create_user_weak_password(
        self, mock_security_utils, auth_service, test_user_data, weak_password_short
    ):
        """Test user creation fails with weak password"""
        mock_security_utils.validate_password_strength.return_value = {
            "is_valid": False,
            "errors": ["Password too short"],
        }

        with pytest.raises(ValueError):
            auth_service.create_user(
                test_user_data["username"], test_user_data["email"], weak_password_short
            )

    @patch("app.services.auth_service.SecurityUtils")
    @patch("app.services.auth_service.pwd_context.hash")
    @patch("app.services.auth_service.uuid.uuid4")
    def test_create_user_duplicate_email(
        self, mock_uuid, mock_hash, mock_security_utils, auth_service, mock_db, test_user_data
    ):
        """Test user creation fails with duplicate email"""
        from sqlalchemy.exc import IntegrityError

        mock_security_utils.validate_password_strength.return_value = {
            "is_valid": True,
            "errors": [],
        }
        mock_security_utils.sanitize_input.side_effect = lambda x: x
        mock_security_utils.sanitize_email.side_effect = lambda x: x
        mock_hash.return_value = "hashed_password"
        mock_uuid.return_value = uuid.UUID("12345678-1234-5678-1234-567812345678")

        # Setup commit to raise IntegrityError (SQLAlchemy)
        mock_db.commit.side_effect = IntegrityError("statement", {}, Exception("Duplicate key"))

        with pytest.raises(AuthenticationError, match="ya existe"):
            auth_service.create_user(
                test_user_data["username"], test_user_data["email"], test_user_data["password"]
            )


# ============================================================================
# USER AUTHENTICATION TESTS
# ============================================================================


class TestAuthenticateUser:
    """Tests for authenticate_user() - SQLAlchemy ORM"""

    @patch("app.services.auth_service.SecurityUtils.sanitize_input")
    @patch("app.services.auth_service.pwd_context.verify")
    def test_authenticate_user_success(
        self, mock_verify, mock_sanitize, auth_service, mock_db, test_user_db_record
    ):
        """Test successful user authentication"""
        mock_sanitize.side_effect = lambda x: x
        mock_verify.return_value = True

        # Create mock user object
        mock_user = MagicMock()
        mock_user.id = test_user_db_record["id"]
        mock_user.username = test_user_db_record["username"]
        mock_user.email = test_user_db_record["email"]
        mock_user.password_hash = test_user_db_record["password_hash"]
        mock_user.is_verified = test_user_db_record["is_verified"]
        mock_user.failed_login_attempts = test_user_db_record["failed_login_attempts"]
        mock_user.locked_until = test_user_db_record["locked_until"]
        mock_user.created_at = test_user_db_record["created_at"]

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        result = auth_service.authenticate_user("testuser", "SecurePass123!", "192.168.1.1")

        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"
        assert result["is_verified"] is True

        # Verify commit was called for successful login
        mock_db.commit.assert_called()

    @patch("app.services.auth_service.SecurityUtils.sanitize_input")
    def test_authenticate_user_not_found(self, mock_sanitize, auth_service, mock_db):
        """Test authentication fails when user not found"""
        mock_sanitize.side_effect = lambda x: x
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(AuthenticationError, match="Credenciales inválidas"):
            auth_service.authenticate_user("nonexistent", "password", "192.168.1.1")

    @patch("app.services.auth_service.SecurityUtils.sanitize_input")
    @patch("app.services.auth_service.pwd_context.verify")
    def test_authenticate_user_wrong_password(
        self, mock_verify, mock_sanitize, auth_service, mock_db, test_user_db_record
    ):
        """Test authentication fails with wrong password"""
        mock_sanitize.side_effect = lambda x: x
        mock_verify.return_value = False

        mock_user = MagicMock()
        mock_user.id = test_user_db_record["id"]
        mock_user.username = test_user_db_record["username"]
        mock_user.email = test_user_db_record["email"]
        mock_user.password_hash = test_user_db_record["password_hash"]
        mock_user.is_verified = test_user_db_record["is_verified"]
        mock_user.failed_login_attempts = test_user_db_record["failed_login_attempts"]
        mock_user.locked_until = test_user_db_record["locked_until"]

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with pytest.raises(AuthenticationError, match="Credenciales inválidas"):
            auth_service.authenticate_user("testuser", "WrongPassword", "192.168.1.1")

        # Verify commit was called for failed login handling
        mock_db.commit.assert_called()

    @patch("app.services.auth_service.SecurityUtils.sanitize_input")
    @patch("app.services.auth_service.pwd_context.verify")
    def test_authenticate_user_not_verified(
        self, mock_verify, mock_sanitize, auth_service, mock_db, test_user_db_record
    ):
        """Test authentication fails when email not verified"""
        mock_sanitize.side_effect = lambda x: x
        mock_verify.return_value = True

        mock_user = MagicMock()
        mock_user.id = test_user_db_record["id"]
        mock_user.username = test_user_db_record["username"]
        mock_user.password_hash = test_user_db_record["password_hash"]
        mock_user.is_verified = False  # Not verified
        mock_user.failed_login_attempts = 0
        mock_user.locked_until = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with pytest.raises(AuthenticationError, match="verificar tu email"):
            auth_service.authenticate_user("testuser", "SecurePass123!", "192.168.1.1")

    @patch("app.services.auth_service.SecurityUtils.sanitize_input")
    def test_authenticate_user_account_locked(
        self, mock_sanitize, auth_service, mock_db, test_user_db_record
    ):
        """Test authentication fails when account is locked"""
        mock_sanitize.side_effect = lambda x: x

        mock_user = MagicMock()
        mock_user.id = test_user_db_record["id"]
        mock_user.username = test_user_db_record["username"]
        mock_user.locked_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            minutes=30
        )

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with pytest.raises(AuthenticationError, match="bloqueada temporalmente"):
            auth_service.authenticate_user("testuser", "SecurePass123!", "192.168.1.1")


# ============================================================================
# FAILED LOGIN HANDLING TESTS
# ============================================================================


class TestFailedLoginHandling:
    """Tests for _handle_failed_login() - SQLAlchemy ORM"""

    @patch("app.config.security.security_settings")
    def test_handle_failed_login_increment(self, mock_security_settings, auth_service, mock_db):
        """Test failed login increments attempt counter"""
        mock_security_settings.MAX_FAILED_LOGIN_ATTEMPTS = 5

        # Create mock user object
        mock_user = MagicMock()
        mock_user.failed_login_attempts = 2

        auth_service._handle_failed_login(mock_user)

        # Verify failed_login_attempts was incremented
        assert mock_user.failed_login_attempts == 3
        mock_db.commit.assert_called_once()

    @patch("app.config.security.security_settings")
    def test_handle_failed_login_lockout(self, mock_security_settings, auth_service, mock_db):
        """Test account gets locked after max failed attempts"""
        mock_security_settings.MAX_FAILED_LOGIN_ATTEMPTS = 5
        mock_security_settings.ACCOUNT_LOCKOUT_DURATION = 1800  # 30 minutes

        # Create mock user object - one more attempt will trigger lockout
        mock_user = MagicMock()
        mock_user.failed_login_attempts = 4

        auth_service._handle_failed_login(mock_user)

        # Verify locked_until was set
        assert mock_user.locked_until is not None
        assert mock_user.failed_login_attempts == 5
        mock_db.commit.assert_called_once()


# ============================================================================
# SUCCESSFUL LOGIN HANDLING TESTS
# ============================================================================


class TestSuccessfulLoginHandling:
    """Tests for _handle_successful_login() - SQLAlchemy ORM"""

    def test_handle_successful_login(self, auth_service, mock_db):
        """Test successful login updates user record"""
        client_ip = "192.168.1.1"

        # Create mock user object
        mock_user = MagicMock()
        mock_user.failed_login_attempts = 3
        mock_user.locked_until = datetime.now(timezone.utc).replace(tzinfo=None)

        auth_service._handle_successful_login(mock_user, client_ip)

        # Verify user attributes were updated
        assert mock_user.failed_login_attempts == 0
        assert mock_user.locked_until is None
        assert mock_user.last_login_ip == client_ip
        mock_db.commit.assert_called_once()


# ============================================================================
# EMAIL VERIFICATION TESTS
# ============================================================================


class TestVerifyEmailCode:
    """Tests for verify_email_code() - SQLAlchemy ORM"""

    @patch("app.crud.email_otp_crud.verify_otp_orm")
    @patch("app.services.auth_service.SecurityUtils")
    def test_verify_email_code_success(
        self, mock_security_utils, mock_verify_otp, auth_service, mock_db
    ):
        """Test successful email verification"""
        mock_security_utils.sanitize_email.side_effect = lambda x: x
        mock_security_utils.sanitize_input.side_effect = lambda x: x
        mock_verify_otp.return_value = True

        # Create mock user
        mock_user = MagicMock()
        mock_user.id = "user_12345"
        mock_user.username = "testuser"
        mock_user.is_verified = False

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        result = auth_service.verify_email_code("test@example.com", "123456")

        assert result["user_id"] == "user_12345"
        assert result["username"] == "testuser"
        assert mock_user.is_verified is True
        mock_db.commit.assert_called()

    @patch("app.crud.email_otp_crud.verify_otp_orm")
    @patch("app.services.auth_service.SecurityUtils")
    def test_verify_email_code_invalid(
        self, mock_security_utils, mock_verify_otp, auth_service, mock_db
    ):
        """Test email verification fails with invalid code"""
        mock_security_utils.sanitize_email.side_effect = lambda x: x
        mock_security_utils.sanitize_input.side_effect = lambda x: x
        mock_verify_otp.return_value = False  # Invalid OTP

        mock_user = MagicMock()
        mock_user.id = "user_12345"
        mock_user.username = "testuser"
        mock_user.is_verified = False

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with pytest.raises(AuthenticationError, match="inválido o expirado"):
            auth_service.verify_email_code("test@example.com", "wrong_code")

    @patch("app.services.auth_service.SecurityUtils")
    def test_verify_email_code_already_verified(self, mock_security_utils, auth_service, mock_db):
        """Test email verification fails if already verified"""
        mock_security_utils.sanitize_email.side_effect = lambda x: x
        mock_security_utils.sanitize_input.side_effect = lambda x: x

        mock_user = MagicMock()
        mock_user.id = "user_12345"
        mock_user.username = "testuser"
        mock_user.is_verified = True  # Already verified

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with pytest.raises(AuthenticationError, match="Código inválido o expirado"):
            auth_service.verify_email_code("test@example.com", "123456")


# ============================================================================
# PASSWORD RESET TESTS
# ============================================================================


class TestResetPassword:
    """Tests for reset_password() - SQLAlchemy ORM"""

    @patch("app.crud.email_otp_crud.verify_otp_orm")
    @patch("app.services.auth_service.SecurityUtils")
    @patch("app.services.auth_service.pwd_context.hash")
    def test_reset_password_success(
        self,
        mock_hash,
        mock_security_utils,
        mock_verify_otp,
        auth_service,
        mock_db,
        strong_password,
    ):
        """Test successful password reset"""
        mock_security_utils.validate_password_strength.return_value = {
            "is_valid": True,
            "errors": [],
        }
        mock_security_utils.sanitize_email.side_effect = lambda x: x
        mock_security_utils.sanitize_input.side_effect = lambda x: x
        mock_hash.return_value = "new_hashed_password"
        mock_verify_otp.return_value = True

        mock_user = MagicMock()
        mock_user.id = "user_12345"
        mock_user.password_hash = "old_hash"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        # Should not raise
        auth_service.reset_password("test@example.com", "123456", strong_password)

        # Verify password was updated
        assert mock_user.password_hash == "new_hashed_password"
        mock_db.commit.assert_called()

    @patch("app.services.auth_service.SecurityUtils")
    def test_reset_password_user_not_found(
        self, mock_security_utils, auth_service, mock_db, strong_password
    ):
        """Test password reset fails when user not found"""
        mock_security_utils.validate_password_strength.return_value = {
            "is_valid": True,
            "errors": [],
        }
        mock_security_utils.sanitize_email.side_effect = lambda x: x
        mock_security_utils.sanitize_input.side_effect = lambda x: x

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(AuthenticationError, match="Código inválido o expirado"):
            auth_service.reset_password("nonexistent@example.com", "123456", strong_password)

    @patch("app.crud.email_otp_crud.verify_otp_orm")
    @patch("app.services.auth_service.SecurityUtils")
    def test_reset_password_invalid_code(
        self, mock_security_utils, mock_verify_otp, auth_service, mock_db, strong_password
    ):
        """Test password reset fails with invalid OTP"""
        mock_security_utils.validate_password_strength.return_value = {
            "is_valid": True,
            "errors": [],
        }
        mock_security_utils.sanitize_email.side_effect = lambda x: x
        mock_security_utils.sanitize_input.side_effect = lambda x: x
        mock_verify_otp.return_value = False  # Invalid OTP

        mock_user = MagicMock()
        mock_user.id = "user_12345"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with pytest.raises(AuthenticationError, match="inválido o expirado"):
            auth_service.reset_password("test@example.com", "wrong_code", strong_password)


# ============================================================================
# EXCEPTION TESTS
# ============================================================================


class TestExceptions:
    """Tests for custom exceptions"""

    def test_database_error_inheritance(self):
        """Test DatabaseError is an Exception"""
        error = DatabaseError("test")
        assert isinstance(error, Exception)

    def test_authentication_error_inheritance(self):
        """Test AuthenticationError is an Exception"""
        error = AuthenticationError("test")
        assert isinstance(error, Exception)
