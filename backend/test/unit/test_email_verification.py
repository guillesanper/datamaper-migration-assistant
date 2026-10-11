"""
Unit tests for app.utils.email_verification module

Tests for email verification utilities:
- OTP code generation
- Verification code sending via email
- Welcome notification creation
"""

import importlib
import logging
import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta
from unittest.mock import ANY, MagicMock, call, patch

import pytest

from app.config.security import security_settings
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


def _configure_smtp_mock(mock_smtp):
    """Configura el mock de smtplib.SMTP como gestor de contexto y devuelve la conexión simulada"""
    mock_smtp_instance = MagicMock()
    mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
    mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
    return mock_smtp_instance


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
# SMTP SIN AUTENTICACIÓN / SIN STARTTLS (servidor de desarrollo, p. ej. Mailpit)
#
# SMTP_USE_STARTTLS y SMTP_TIMEOUT_SECONDS se parchean con create=True porque aún
# no existen en el módulo; sin ello @patch fallaría con AttributeError en lugar de
# fallar por la aserción de comportamiento que se quiere comprobar.
# ============================================================================


class TestSendVerificationCodeSmtpModes:
    """Tests for send_verification_code() with optional credentials and STARTTLS"""

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.smtplib.SMTP")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_USE_STARTTLS", False, create=True)
    @patch("app.utils.email_verification.SMTP_SERVER", "mailpit")
    @patch("app.utils.email_verification.SMTP_USER", None)
    @patch("app.utils.email_verification.SMTP_PASS", None)
    @patch("app.utils.email_verification.EMAIL_FROM", "no-reply@datamap.local")
    def test_no_credentials_no_starttls_sends_without_auth(
        self, mock_generate_code, mock_smtp, mock_create_otp, mock_db, test_email, test_user_id
    ):
        """Sin credenciales y sin STARTTLS: no se llama a starttls ni a login, pero sí se envía"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}
        mock_smtp_instance = _configure_smtp_mock(mock_smtp)

        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        mock_smtp_instance.starttls.assert_not_called()
        mock_smtp_instance.login.assert_not_called()
        mock_smtp_instance.send_message.assert_called_once()

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.smtplib.SMTP")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_USE_STARTTLS", False, create=True)
    @patch("app.utils.email_verification.SMTP_SERVER", "smtp.example.com")
    @patch("app.utils.email_verification.SMTP_USER", "user@example.com")
    @patch("app.utils.email_verification.SMTP_PASS", "password")
    @patch("app.utils.email_verification.EMAIL_FROM", "noreply@example.com")
    def test_credentials_without_starttls_logs_in_only(
        self, mock_generate_code, mock_smtp, mock_create_otp, mock_db, test_email, test_user_id
    ):
        """Con credenciales y sin STARTTLS: se llama a login pero no a starttls"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}
        mock_smtp_instance = _configure_smtp_mock(mock_smtp)

        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        mock_smtp_instance.starttls.assert_not_called()
        mock_smtp_instance.login.assert_called_once_with("user@example.com", "password")
        mock_smtp_instance.send_message.assert_called_once()

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.smtplib.SMTP")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_SERVER", "smtp.example.com")
    @patch("app.utils.email_verification.SMTP_USER", "user@example.com")
    @patch("app.utils.email_verification.SMTP_PASS", "password")
    @patch("app.utils.email_verification.EMAIL_FROM", "noreply@example.com")
    def test_credentials_default_starttls_keeps_current_behavior(
        self, mock_generate_code, mock_smtp, mock_create_otp, mock_db, test_email, test_user_id
    ):
        """Regresión: con credenciales y STARTTLS por defecto se mantiene la secuencia actual"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}
        mock_smtp_instance = _configure_smtp_mock(mock_smtp)

        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        assert mock_smtp_instance.method_calls == [
            call.ehlo(),
            call.starttls(),
            call.ehlo(),
            call.login("user@example.com", "password"),
            call.send_message(ANY),
        ]

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.smtplib.SMTP")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_SERVER", "smtp.example.com")
    @patch("app.utils.email_verification.SMTP_USER", "user@example.com")
    @patch("app.utils.email_verification.SMTP_PASS", None)
    @patch("app.utils.email_verification.EMAIL_FROM", "noreply@example.com")
    def test_only_user_simulates_sending(
        self,
        mock_generate_code,
        mock_smtp,
        mock_create_otp,
        mock_db,
        test_email,
        test_user_id,
        capsys,
    ):
        """Con solo usuario (credenciales a medias) se simula el envío y no se abre conexión"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}

        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        mock_create_otp.assert_called_once()
        mock_smtp.assert_not_called()
        captured = capsys.readouterr()
        assert "simulando envío" in captured.out.lower()
        assert "12345678" in captured.out

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.smtplib.SMTP")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_SERVER", "smtp.example.com")
    @patch("app.utils.email_verification.SMTP_USER", None)
    @patch("app.utils.email_verification.SMTP_PASS", "s3cret-pass")
    @patch("app.utils.email_verification.EMAIL_FROM", "noreply@example.com")
    def test_only_password_simulates_sending(
        self,
        mock_generate_code,
        mock_smtp,
        mock_create_otp,
        mock_db,
        test_email,
        test_user_id,
        capsys,
    ):
        """Con solo contraseña se simula el envío, no se abre conexión y no se imprime la clave"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}

        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        mock_create_otp.assert_called_once()
        mock_smtp.assert_not_called()
        captured = capsys.readouterr()
        assert "simulando envío" in captured.out.lower()
        assert "12345678" in captured.out
        assert "s3cret-pass" not in captured.out

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.smtplib.SMTP")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_SERVER", "smtp.example.com")
    @patch("app.utils.email_verification.SMTP_USER", "user@example.com")
    @patch("app.utils.email_verification.SMTP_PASS", "password")
    @patch("app.utils.email_verification.EMAIL_FROM", "noreply@example.com")
    def test_smtp_connection_uses_default_timeout(
        self, mock_generate_code, mock_smtp, mock_create_otp, mock_db, test_email, test_user_id
    ):
        """smtplib.SMTP recibe timeout=10 (valor por defecto de SMTP_TIMEOUT_SECONDS)"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}
        _configure_smtp_mock(mock_smtp)

        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        mock_smtp.assert_called_once()
        assert mock_smtp.call_args.kwargs.get("timeout") == 10

    @patch("app.crud.email_otp_crud.create_otp_orm")
    @patch("app.utils.email_verification.smtplib.SMTP")
    @patch("app.utils.email_verification.generate_numeric_code")
    @patch("app.utils.email_verification.SMTP_TIMEOUT_SECONDS", 7, create=True)
    @patch("app.utils.email_verification.SMTP_SERVER", "smtp.example.com")
    @patch("app.utils.email_verification.SMTP_USER", "user@example.com")
    @patch("app.utils.email_verification.SMTP_PASS", "password")
    @patch("app.utils.email_verification.EMAIL_FROM", "noreply@example.com")
    def test_smtp_connection_timeout_comes_from_constant(
        self, mock_generate_code, mock_smtp, mock_create_otp, mock_db, test_email, test_user_id
    ):
        """El timeout pasado a smtplib.SMTP se toma de SMTP_TIMEOUT_SECONDS, no está fijado"""
        mock_generate_code.return_value = "12345678"
        mock_create_otp.return_value = {"user_id": test_user_id, "otp_code": "hashed"}
        _configure_smtp_mock(mock_smtp)

        email_verification.send_verification_code(mock_db, test_email, test_user_id)

        mock_smtp.assert_called_once()
        assert mock_smtp.call_args.kwargs.get("timeout") == 7


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


class TestSmtpUseStarttlsEnvironment:
    """Tests for SMTP_USE_STARTTLS parsing (valor no reconocido o vacío = STARTTLS activo)"""

    @staticmethod
    def _reload_with_env(env):
        """Recarga el módulo con el entorno dado y lo deja recargado con el entorno real"""
        try:
            with patch.dict("os.environ", env, clear=True):
                importlib.reload(email_verification)
                return email_verification.SMTP_USE_STARTTLS
        finally:
            importlib.reload(email_verification)

    def test_smtp_use_starttls_default(self):
        """Sin la variable definida, STARTTLS está activo (comportamiento histórico)"""
        assert self._reload_with_env({}) is True

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
    def test_smtp_use_starttls_enabled_values(self, value):
        """Valores que activan STARTTLS"""
        assert self._reload_with_env({"SMTP_USE_STARTTLS": value}) is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", "off"])
    def test_smtp_use_starttls_disabled_values(self, value):
        """Valores que desactivan STARTTLS"""
        assert self._reload_with_env({"SMTP_USE_STARTTLS": value}) is False

    @pytest.mark.parametrize("value", ["", "   ", "talvez", "2"])
    def test_smtp_use_starttls_empty_or_invalid_keeps_default(self, value):
        """Un valor vacío o no reconocido no desactiva STARTTLS (fallo hacia el lado seguro)"""
        assert self._reload_with_env({"SMTP_USE_STARTTLS": value}) is True


# ============================================================================
# OTP FUERA DEL LOG (hallazgo 8)
# ============================================================================

_OTP = "12345678"
_FULL_SMTP = {
    "SMTP_SERVER": "smtp.example.com",
    "SMTP_USER": "user@example.com",
    "SMTP_PASS": "password",
    "EMAIL_FROM": "noreply@example.com",
}

# Escenarios en los que el código no llega al usuario: configuración SMTP que se simula
# (sin servidor, credenciales a medias) y error real al enviar.
_UNDELIVERED_SCENARIOS = {
    "smtp_not_configured": {**_FULL_SMTP, "SMTP_SERVER": None},
    "only_user": {**_FULL_SMTP, "SMTP_PASS": None},
    "only_password": {**_FULL_SMTP, "SMTP_USER": None},
    "smtp_error": dict(_FULL_SMTP),
    # El servidor devuelve en su error datos del mensaje: ni el destinatario ni el código
    # pueden acabar en el log a través del texto de la excepción.
    "smtp_error_echoes_message": dict(_FULL_SMTP),
}


def _send_code(scenario, development, mock_db, to_email, user_id):
    """Ejecuta send_verification_code en un escenario y entorno; devuelve el mock del OTP"""
    smtp_config = _UNDELIVERED_SCENARIOS.get(scenario, _FULL_SMTP)
    with ExitStack() as stack:
        mock_create_otp = stack.enter_context(patch("app.crud.email_otp_crud.create_otp_orm"))
        stack.enter_context(
            patch("app.utils.email_verification.generate_numeric_code", return_value=_OTP)
        )
        for name, value in smtp_config.items():
            stack.enter_context(patch.object(email_verification, name, value))
        stack.enter_context(patch.object(security_settings, "DEVELOPMENT_MODE", development))
        mock_smtp = stack.enter_context(patch("app.utils.email_verification.smtplib.SMTP"))
        _configure_smtp_mock(mock_smtp)
        if scenario == "smtp_error":
            mock_smtp.side_effect = Exception("SMTP connection failed")
        elif scenario == "smtp_error_echoes_message":
            mock_smtp.side_effect = Exception(f"550 rechazado {to_email} contenido {_OTP}")

        email_verification.send_verification_code(mock_db, to_email, user_id)
    return mock_create_otp


class TestOtpNotLoggedOutsideDevelopment:
    """El OTP en claro solo puede salir por stdout/log en desarrollo; fuera de él, nunca"""

    @pytest.fixture(autouse=True)
    def _enable_module_logger(self, monkeypatch):
        """
        El conftest ejecuta `alembic upgrade head` en el proceso con alembic.ini y su
        fileConfig deshabilita los loggers ya creados; sin esto caplog no vería nada y los
        tests de ausencia pasarían en vacío. En producción alembic corre en otro proceso.
        """
        monkeypatch.setattr(email_verification.logger, "disabled", False)

    @pytest.mark.parametrize("scenario", list(_UNDELIVERED_SCENARIOS))
    def test_code_absent_from_output_and_logs_in_production(
        self, scenario, mock_db, test_email, test_user_id, capsys, caplog
    ):
        """Fuera de desarrollo el código no aparece ni en stdout, ni en stderr ni en logging"""
        caplog.set_level(logging.DEBUG)

        _send_code(scenario, False, mock_db, test_email, test_user_id)

        captured = capsys.readouterr()
        assert _OTP not in captured.out
        assert _OTP not in captured.err
        assert _OTP not in caplog.text

    @pytest.mark.parametrize("scenario", list(_UNDELIVERED_SCENARIOS))
    def test_failure_is_logged_with_masked_email_in_production(
        self, scenario, mock_db, test_email, test_user_id, capsys, caplog
    ):
        """El fallo se registra (nivel ERROR) con el email enmascarado y el OTP queda guardado"""
        caplog.set_level(logging.DEBUG)

        mock_create_otp = _send_code(scenario, False, mock_db, test_email, test_user_id)

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors, "el fallo de entrega debe quedar registrado"
        logged = "\n".join(r.getMessage() for r in errors)
        assert test_email not in logged
        assert test_email not in capsys.readouterr().out
        assert "@example.com" in logged  # dominio visible para diagnosticar
        mock_create_otp.assert_called_once()

    @pytest.mark.parametrize("scenario", list(_UNDELIVERED_SCENARIOS))
    def test_code_still_printed_in_development(
        self, scenario, mock_db, test_email, test_user_id, capsys
    ):
        """En desarrollo se conserva el fallback: el código sale por stdout (como hasta ahora)"""
        _send_code(scenario, True, mock_db, test_email, test_user_id)

        assert _OTP in capsys.readouterr().out

    @pytest.mark.parametrize("development", [True, False])
    def test_successful_delivery_never_logs_code(
        self, development, mock_db, test_email, test_user_id, capsys, caplog
    ):
        """Con envío correcto el código viaja solo en el correo, en cualquier entorno"""
        caplog.set_level(logging.DEBUG)

        _send_code("delivered", development, mock_db, test_email, test_user_id)

        captured = capsys.readouterr()
        assert _OTP not in captured.out + captured.err + caplog.text

    @pytest.mark.parametrize("development", [True, False])
    def test_fallback_helper_follows_development_mode(self, development):
        """El helper lee DEVELOPMENT_MODE en tiempo de llamada (parcheable en tests)"""
        with patch.object(security_settings, "DEVELOPMENT_MODE", development):
            assert email_verification._log_code_fallback_allowed() is development


class TestSmtpStartupWarning:
    """validate_security_config avisa en producción si los códigos no podrán entregarse"""

    @pytest.fixture
    def production(self, monkeypatch):
        """Producción con secretos válidos: la validación no debe elevar errores críticos"""
        monkeypatch.setattr(security_settings, "DEVELOPMENT_MODE", False)
        monkeypatch.setattr(security_settings, "CSRF_SECRET_KEY", "csrf-secret-de-prueba")
        monkeypatch.setattr(security_settings, "IP_HASH_SALT", "ip-salt-de-prueba")
        return monkeypatch

    @pytest.mark.parametrize(
        "smtp_server,email_from",
        [(None, None), ("smtp.example.com", None), (None, "noreply@example.com")],
    )
    def test_warns_when_smtp_incomplete_in_production(
        self, production, capsys, smtp_server, email_from
    ):
        from app.config.security import validate_security_config

        for name, value in (("SMTP_SERVER", smtp_server), ("EMAIL_FROM", email_from)):
            if value is None:
                production.delenv(name, raising=False)
            else:
                production.setenv(name, value)

        assert validate_security_config() is True  # es un aviso, no un error crítico
        assert "no se entregarán" in capsys.readouterr().out

    def test_no_warning_when_smtp_configured(self, production, capsys):
        from app.config.security import validate_security_config

        production.setenv("SMTP_SERVER", "smtp.example.com")
        production.setenv("EMAIL_FROM", "noreply@example.com")

        validate_security_config()

        assert "no se entregarán" not in capsys.readouterr().out

    def test_no_warning_in_development(self, production, capsys):
        from app.config.security import validate_security_config

        production.setattr(security_settings, "DEVELOPMENT_MODE", True)
        production.delenv("SMTP_SERVER", raising=False)
        production.delenv("EMAIL_FROM", raising=False)

        validate_security_config()

        assert "no se entregarán" not in capsys.readouterr().out


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


# ============================================================================
# EMISIÓN Y ENTREGA SEPARADAS (hallazgo 1)
# ============================================================================


class TestIssueAndDeliverSplit:
    """
    issue_verification_code (con BD) y deliver_verification_email (sin BD) por separado, para
    poder entregar el correo en segundo plano; send_verification_code los compone.
    """

    @pytest.fixture(autouse=True)
    def _enable_module_logger(self, monkeypatch):
        """Ver TestOtpNotLoggedOutsideDevelopment: el arnés deshabilita los loggers"""
        monkeypatch.setattr(email_verification.logger, "disabled", False)

    def test_issue_returns_the_code_and_stores_it_without_sending(self, mock_db, test_user_id):
        from app.utils.email_verification import issue_verification_code

        with ExitStack() as stack:
            mock_create_otp = stack.enter_context(patch("app.crud.email_otp_crud.create_otp_orm"))
            stack.enter_context(
                patch("app.utils.email_verification.generate_numeric_code", return_value=_OTP)
            )
            mock_smtp = stack.enter_context(patch("app.utils.email_verification.smtplib.SMTP"))

            code = issue_verification_code(mock_db, test_user_id)

        assert code == _OTP
        mock_create_otp.assert_called_once_with(
            mock_db, user_id=test_user_id, otp_code=_OTP, expires_in_minutes=10
        )
        mock_smtp.assert_not_called()

    def test_deliver_takes_no_database_session(self):
        """La tarea de fondo no puede recibir db: la sesión se cierra al terminar la petición"""
        import inspect

        from app.utils.email_verification import deliver_verification_email

        assert list(inspect.signature(deliver_verification_email).parameters) == [
            "to_email",
            "code",
        ]

    def test_deliver_sends_the_email_with_the_given_code(self, test_email):
        from app.utils.email_verification import deliver_verification_email

        with ExitStack() as stack:
            for name, value in _FULL_SMTP.items():
                stack.enter_context(patch.object(email_verification, name, value))
            mock_smtp = stack.enter_context(patch("app.utils.email_verification.smtplib.SMTP"))
            connection = _configure_smtp_mock(mock_smtp)

            result = deliver_verification_email(test_email, _OTP)

        assert result is None
        connection.send_message.assert_called_once()
        message = connection.send_message.call_args[0][0]
        assert message["To"] == test_email
        assert _OTP in message.get_content()

    @pytest.mark.parametrize("scenario", list(_UNDELIVERED_SCENARIOS))
    @pytest.mark.parametrize("development", [True, False])
    def test_deliver_keeps_the_otp_policy(self, scenario, development, test_email, capsys, caplog):
        """Mismo criterio que send_verification_code: el código solo sale en desarrollo"""
        from app.utils.email_verification import deliver_verification_email

        caplog.set_level(logging.DEBUG)
        smtp_config = _UNDELIVERED_SCENARIOS[scenario]
        with ExitStack() as stack:
            for name, value in smtp_config.items():
                stack.enter_context(patch.object(email_verification, name, value))
            stack.enter_context(patch.object(security_settings, "DEVELOPMENT_MODE", development))
            mock_smtp = stack.enter_context(patch("app.utils.email_verification.smtplib.SMTP"))
            _configure_smtp_mock(mock_smtp)
            if scenario == "smtp_error":
                mock_smtp.side_effect = Exception("SMTP connection failed")
            elif scenario == "smtp_error_echoes_message":
                mock_smtp.side_effect = Exception(f"550 rechazado {test_email} contenido {_OTP}")

            deliver_verification_email(test_email, _OTP)

        captured = capsys.readouterr()
        if development:
            assert _OTP in captured.out
        else:
            assert _OTP not in captured.out
            assert _OTP not in captured.err
            assert _OTP not in caplog.text

    def test_send_verification_code_is_issue_plus_deliver(self, mock_db, test_email, test_user_id):
        """Compatibilidad: misma firma, mismo orden, no devuelve el código"""
        manager = MagicMock()
        with (
            patch.object(
                email_verification, "issue_verification_code", return_value=_OTP
            ) as mock_issue,
            patch.object(email_verification, "deliver_verification_email") as mock_deliver,
        ):
            manager.attach_mock(mock_issue, "issue")
            manager.attach_mock(mock_deliver, "deliver")

            result = email_verification.send_verification_code(mock_db, test_email, test_user_id)

        assert result is None
        assert manager.mock_calls == [
            call.issue(mock_db, test_user_id),
            call.deliver(test_email, _OTP),
        ]

    def test_send_verification_code_uses_the_injected_deliver(
        self, mock_db, test_email, test_user_id
    ):
        deliver = MagicMock()
        with (
            patch.object(email_verification, "issue_verification_code", return_value=_OTP),
            patch.object(email_verification, "deliver_verification_email") as mock_default,
        ):
            email_verification.send_verification_code(
                mock_db, test_email, test_user_id, deliver=deliver
            )

        deliver.assert_called_once_with(test_email, _OTP)
        mock_default.assert_not_called()
