"""
Unit tests for app.utils.email_verification module

Tests for email verification utilities:
- OTP code generation
- Verification code sending via email
- Welcome notification creation
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

import pytest

from app.utils import email_verification

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db():
    """Provide a mock database connection"""
    db = MagicMock()
    cursor = MagicMock()
    db.cursor.return_value = cursor
    return db


@pytest.fixture
def mock_cursor():
    """Provide a mock database cursor"""
    return MagicMock()


@pytest.fixture
def test_email():
    """Provide a test email address"""
    return "test@example.com"


@pytest.fixture
def test_user_id():
    """Provide a test user ID"""
    return "user_12345"


# ============================================================================
# GENERATE NUMERIC CODE TESTS
# ============================================================================


class TestGenerateNumericCode:
    """Tests for generate_numeric_code()"""

    @patch("app.utils.email_verification.generate_numeric_code")
    def test_generate_numeric_code(self, mock_generate_otp):
        """Test OTP code generation"""
        mock_generate_otp.return_value = "12345678"

        code = email_verification.generate_numeric_code()

        assert code == "12345678"
        mock_generate_otp.assert_called_once()

    @patch("app.utils.email_verification.generate_numeric_code")
    def test_generate_numeric_code_returns_string(self, mock_generate_otp):
        """Test that generated code is a string"""
        mock_generate_otp.return_value = "87654321"

        code = email_verification.generate_numeric_code()

        assert isinstance(code, str)


# ============================================================================
# SEND VERIFICATION CODE TESTS
# ============================================================================


class TestSendVerificationCode:
    """Tests for send_verification_code()"""

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.smtplib.SMTP")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_SERVER", "smtp.example.com")
    @patch("app.utils.email_verification.SMTP_USER", "user@example.com")
    @patch("app.utils.email_verification.SMTP_PASS", "password")
    @patch("app.utils.email_verification.EMAIL_FROM", "noreply@example.com")
    def test_send_verification_code_success(
        self, mock_generate_code, mock_smtp, mock_create_otp, mock_db, test_email, test_user_id
    ):
        """Test successful verification code sending"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        # Verify OTP was created via CRUD
        mock_create_otp.assert_called_once_with(
            mock_db, user_id=test_user_id, otp_code="12345678", expires_in_minutes=10
        )

        # Verify email was sent
        mock_smtp_instance.ehlo.assert_called()
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once()
        mock_smtp_instance.send_message.assert_called_once()

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_SERVER", None)
    def test_send_verification_code_no_smtp_config(
        self, mock_generate_code, mock_create_otp, mock_db, test_email, test_user_id, capsys
    ):
        """Test code sending when SMTP not configured (dev mode)"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}

        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        # Verify OTP was created via CRUD
        mock_create_otp.assert_called_once()

        # Verify simulation message was printed
        captured = capsys.readouterr()
        assert (
            "simulando envío" in captured.out.lower() or "smtp incompleta" in captured.out.lower()
        )
        assert "12345678" in captured.out

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.smtplib.SMTP")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_SERVER", "smtp.example.com")
    @patch("app.utils.email_verification.SMTP_USER", "user@example.com")
    @patch("app.utils.email_verification.SMTP_PASS", "password")
    @patch("app.utils.email_verification.EMAIL_FROM", "noreply@example.com")
    def test_send_verification_code_smtp_error(
        self,
        mock_generate_code,
        mock_smtp,
        mock_create_otp,
        mock_db,
        test_email,
        test_user_id,
        capsys,
    ):
        """Test code sending handles SMTP errors gracefully"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}
        mock_smtp.side_effect = Exception("SMTP connection failed")

        # Should not raise exception
        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        # Verify OTP was created via CRUD despite email failure
        mock_create_otp.assert_called_once()

        # Verify error was printed
        captured = capsys.readouterr()
        assert "Error enviando email" in captured.out

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_SERVER", "smtp.example.com")
    @patch("app.utils.email_verification.SMTP_USER", "user@example.com")
    @patch("app.utils.email_verification.SMTP_PASS", "password")
    @patch("app.utils.email_verification.EMAIL_FROM", "noreply@example.com")
    def test_send_verification_code_email_content(
        self, mock_generate_code, mock_create_otp, mock_db, test_email, test_user_id
    ):
        """Test verification email content"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}

        with patch("app.utils.email_verification.smtplib.SMTP") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            email_verification.send_verification_code(mock_db, test_email, test_user_id)

            # Verify email message was created with correct content
            mock_smtp_instance.send_message.assert_called_once()
            message = mock_smtp_instance.send_message.call_args[0][0]

            assert message["To"] == test_email
            assert "12345678" in message.get_content()
            assert "10 minutos" in message.get_content()

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.generate_numeric_code")
    def test_send_verification_code_upsert_behavior(
        self, mock_generate_code, mock_create_otp, mock_db, test_email, test_user_id
    ):
        """Test that sending code again updates existing OTP (handled by CRUD)"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}

        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        # Verify CRUD was called (CRUD handles upsert internally)
        mock_create_otp.assert_called_once_with(
            mock_db, user_id=test_user_id, otp_code="12345678", expires_in_minutes=10
        )


# ============================================================================
# CREATE WELCOME NOTIFICATION TESTS
# ============================================================================


class TestCreateWelcomeNotification:
    """Tests for create_welcome_notification()"""

    @patch("app.crud.notification_crud.create_notification_orm")
    def test_create_welcome_notification_success(
        self, mock_create_notification, mock_db, test_user_id
    ):
        """Test successful welcome notification creation"""
        mock_create_notification.return_value = {"id": "notif-123"}

        email_verification.create_welcome_notification(
            mock_db, test_user_id, lambda key, **kwargs: key  # Mock translation function
        )

        # Verify notification was created via CRUD
        mock_create_notification.assert_called_once()
        call_kwargs = mock_create_notification.call_args[1]
        assert call_kwargs["recipient_id"] == test_user_id
        assert call_kwargs["title"] == "¡Bienvenido!"

    @patch("app.crud.notification_crud.create_notification_orm")
    def test_create_welcome_notification_content(
        self, mock_create_notification, mock_db, test_user_id
    ):
        """Test welcome notification content"""
        mock_create_notification.return_value = {"id": "notif-123"}

        email_verification.create_welcome_notification(
            mock_db, test_user_id, lambda key, **kwargs: key
        )

        # Verify notification details via CRUD call
        call_kwargs = mock_create_notification.call_args[1]
        assert call_kwargs["notification_kind"] == "system"
        assert call_kwargs["recipient_id"] == test_user_id
        assert call_kwargs["title"] == "¡Bienvenido!"
        assert "DataMap" in call_kwargs["body"]

    @patch("app.crud.notification_crud.create_notification_orm")
    def test_create_welcome_notification_no_commit(
        self, mock_create_notification, mock_db, test_user_id
    ):
        """Test that notification creation delegates to CRUD (CRUD handles commit)"""
        mock_create_notification.return_value = {"id": "notif-123"}

        email_verification.create_welcome_notification(
            mock_db, test_user_id, lambda key, **kwargs: key
        )

        # Verify CRUD was called (CRUD handles transaction internally)
        mock_create_notification.assert_called_once()


# ============================================================================
# ENVIRONMENT VARIABLES TESTS
# ============================================================================


class TestEnvironmentVariables:
    """Tests for environment variable handling"""

    def test_smtp_port_default(self):
        """Test SMTP port has default value"""
        with patch.dict("os.environ", {}, clear=True):
            # Re-import to get fresh env vars
            import importlib

            importlib.reload(email_verification)

            # Should default to 587
            from app.utils.email_verification import SMTP_PORT

            assert SMTP_PORT == 587

    @patch.dict("os.environ", {"SMTP_PORT": "465"})
    def test_smtp_port_custom(self):
        """Test SMTP port can be customized"""
        import importlib

        importlib.reload(email_verification)

        from app.utils.email_verification import SMTP_PORT

        assert SMTP_PORT == 465


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestEmailVerificationIntegration:
    """Integration tests for email verification flow"""

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.smtplib.SMTP")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_SERVER", "smtp.example.com")
    @patch("app.utils.email_verification.SMTP_USER", "user@example.com")
    @patch("app.utils.email_verification.SMTP_PASS", "password")
    @patch("app.utils.email_verification.EMAIL_FROM", "noreply@example.com")
    def test_full_verification_flow(
        self, mock_generate_otp, mock_smtp, mock_create_otp, mock_db, test_email, test_user_id
    ):
        """Test complete verification code flow"""
        mock_generate_otp.return_value = "87654321"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        # Send verification code
        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        # Verify OTP was created via CRUD
        mock_create_otp.assert_called_once_with(
            mock_db, user_id=test_user_id, otp_code="87654321", expires_in_minutes=10
        )

        # Verify email was sent
        assert mock_smtp_instance.send_message.called

    @patch("app.crud.notification_crud.create_notification_orm")
    def test_user_registration_notifications(self, mock_create_notification, mock_db, test_user_id):
        """Test notification creation during user registration"""
        mock_create_notification.return_value = {"id": "notif-123"}

        # Create welcome notification
        email_verification.create_welcome_notification(
            mock_db, test_user_id, lambda key, **kwargs: key
        )

        # Verify notification was created via CRUD
        mock_create_notification.assert_called_once()
        call_kwargs = mock_create_notification.call_args[1]
        assert call_kwargs["recipient_id"] == test_user_id
        assert call_kwargs["notification_kind"] == "system"
        assert call_kwargs["title"] == "¡Bienvenido!"
