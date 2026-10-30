"""
Unit tests for app.utils.security module

Tests for SecurityUtils:
- OTP generation
- CSRF token generation
- Input sanitization
- Email/username sanitization
- Client IP detection
- IP hashing
- User-Agent parsing
- HMAC signatures
- URL validation
- Sensitive data masking
- Password strength validation
"""

import hashlib
import hmac
import logging
from unittest.mock import MagicMock, patch

import pytest

from app.utils.security import SecurityUtils, generate_otp, get_client_ip, sanitize_input

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_request():
    """Provide a mock FastAPI request"""
    request = MagicMock()
    request.headers = {}
    request.client = MagicMock()
    request.client.host = "192.168.1.1"
    return request


@pytest.fixture
def test_password_strong():
    """Provide a strong password"""
    return "MyStr0ng!Pass"


@pytest.fixture
def test_password_weak():
    """Provide a weak password"""
    return "weak"


# ============================================================================
# OTP AND TOKEN GENERATION TESTS
# ============================================================================


class TestTokenGeneration:
    """Tests for token and OTP generation"""

    @patch("app.utils.security.security_settings")
    def test_generate_secure_otp_default_length(self, mock_settings):
        """Test OTP generation with default length"""
        mock_settings.OTP_LENGTH = 6
        mock_settings.OTP_CHARSET = "0123456789"

        otp = SecurityUtils.generate_secure_otp()

        assert isinstance(otp, str)
        assert len(otp) == 6
        assert otp.isdigit()

    @patch("app.utils.security.security_settings")
    def test_generate_secure_otp_custom_length(self, mock_settings):
        """Test OTP generation with custom length"""
        mock_settings.OTP_CHARSET = "0123456789"

        otp = SecurityUtils.generate_secure_otp(length=8)

        assert len(otp) == 8
        assert otp.isdigit()

    @patch("app.utils.security.security_settings")
    def test_generate_secure_otp_alphanumeric(self, mock_settings):
        """Test OTP generation with alphanumeric charset"""
        mock_settings.OTP_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

        otp = SecurityUtils.generate_secure_otp(length=10)

        assert len(otp) == 10
        assert otp.isalnum()

    def test_generate_secure_otp_uniqueness(self):
        """Test that generated OTPs are unique"""
        otps = [SecurityUtils.generate_secure_otp(length=8) for _ in range(100)]

        # Most should be unique (allowing for rare collisions)
        assert len(set(otps)) > 95

    @patch("app.utils.security.security_settings")
    def test_generate_csrf_token_default_length(self, mock_settings):
        """Test CSRF token generation with default length"""
        mock_settings.CSRF_TOKEN_LENGTH = 32

        token = SecurityUtils.generate_csrf_token()

        assert isinstance(token, str)
        assert len(token) > 0  # URL-safe tokens vary in length

    @patch("app.utils.security.security_settings")
    def test_generate_csrf_token_custom_length(self, mock_settings):
        """Test CSRF token generation with custom length"""
        token = SecurityUtils.generate_csrf_token(length=16)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_generate_csrf_token_uniqueness(self):
        """Test that CSRF tokens are unique"""
        tokens = [SecurityUtils.generate_csrf_token(length=32) for _ in range(100)]

        assert len(set(tokens)) == 100

    def test_generate_secure_token(self):
        """Test secure token generation"""
        token = SecurityUtils.generate_secure_token(length=32)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_generate_secure_token_uniqueness(self):
        """Test that secure tokens are unique"""
        tokens = [SecurityUtils.generate_secure_token() for _ in range(100)]

        assert len(set(tokens)) == 100


# ============================================================================
# INPUT SANITIZATION TESTS
# ============================================================================


class TestInputSanitization:
    """Tests for input sanitization functions"""

    def test_sanitize_input_basic(self):
        """Test basic input sanitization"""
        result = SecurityUtils.sanitize_input("Hello World")

        assert result == "Hello World"

    def test_sanitize_input_remove_html(self):
        """Test HTML tag removal"""
        result = SecurityUtils.sanitize_input("<script>alert('xss')</script>Hello")

        assert "<script>" not in result
        assert "</script>" not in result
        assert "Hello" in result

    def test_sanitize_input_remove_control_chars(self):
        """Test control character removal"""
        result = SecurityUtils.sanitize_input("Hello\x00\x1fWorld")

        assert "\x00" not in result
        assert "\x1f" not in result
        assert result == "HelloWorld"

    def test_sanitize_input_truncate(self):
        """Test input truncation"""
        long_string = "a" * 300

        result = SecurityUtils.sanitize_input(long_string, max_length=100)

        assert len(result) == 100

    def test_sanitize_input_strip_whitespace(self):
        """Test whitespace stripping"""
        result = SecurityUtils.sanitize_input("  Hello World  ")

        assert result == "Hello World"

    def test_sanitize_input_empty_string(self):
        """Test sanitization of empty string"""
        result = SecurityUtils.sanitize_input("")

        assert result == ""

    def test_sanitize_input_none(self):
        """Test sanitization of None"""
        result = SecurityUtils.sanitize_input(None)

        assert result == ""

    def test_sanitize_email_basic(self):
        """Test basic email sanitization"""
        result = SecurityUtils.sanitize_email("Test@Example.COM")

        assert result == "test@example.com"

    def test_sanitize_email_remove_html(self):
        """Test email sanitization removes HTML"""
        result = SecurityUtils.sanitize_email("<script>test@example.com</script>")

        assert "<script>" not in result
        assert "test@example.com" in result

    def test_sanitize_email_truncate(self):
        """Test email truncation at RFC limit"""
        long_email = "a" * 300 + "@example.com"

        result = SecurityUtils.sanitize_email(long_email)

        assert len(result) <= 254  # RFC 5321 limit

    def test_sanitize_email_empty(self):
        """Test sanitization of empty email"""
        result = SecurityUtils.sanitize_email("")

        assert result == ""

    def test_sanitize_username_basic(self):
        """Test basic username sanitization"""
        result = SecurityUtils.sanitize_username("user_name-123")

        assert result == "user_name-123"

    def test_sanitize_username_remove_special_chars(self):
        """Test removal of special characters from username"""
        result = SecurityUtils.sanitize_username("user@#$name!123")

        assert "@" not in result
        assert "#" not in result
        assert "$" not in result
        assert "!" not in result
        assert "username123" in result

    def test_sanitize_username_truncate(self):
        """Test username truncation"""
        long_username = "a" * 100

        result = SecurityUtils.sanitize_username(long_username)

        assert len(result) == 50

    def test_sanitize_username_empty(self):
        """Test sanitization of empty username"""
        result = SecurityUtils.sanitize_username("")

        assert result == ""


# ============================================================================
# CLIENT IP DETECTION TESTS
# ============================================================================


class TestClientIPDetection:
    """Tests for client IP detection"""

    def test_get_client_ip_x_forwarded_for(self, mock_request, monkeypatch):
        """Sin proxies de confianza, X-Forwarded-For (que controla el cliente) se ignora"""
        monkeypatch.setattr("app.utils.security.security_settings.TRUSTED_PROXY_HOPS", 0)
        mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}

        ip = SecurityUtils.get_client_ip(mock_request)

        assert ip == "192.168.1.1"

    def test_get_client_ip_x_real_ip(self, mock_request, monkeypatch):
        """X-Real-IP ya no se usa: la controla el cliente igual que X-Forwarded-For"""
        monkeypatch.setattr("app.utils.security.security_settings.TRUSTED_PROXY_HOPS", 0)
        mock_request.headers = {"X-Real-IP": "203.0.113.1"}

        ip = SecurityUtils.get_client_ip(mock_request)

        assert ip == "192.168.1.1"

    def test_get_client_ip_x_forwarded(self, mock_request, monkeypatch):
        """X-Forwarded ya no se usa: la controla el cliente igual que X-Forwarded-For"""
        monkeypatch.setattr("app.utils.security.security_settings.TRUSTED_PROXY_HOPS", 0)
        mock_request.headers = {"X-Forwarded": "203.0.113.1"}

        ip = SecurityUtils.get_client_ip(mock_request)

        assert ip == "192.168.1.1"

    def test_get_client_ip_direct(self, mock_request):
        """Test IP detection from direct connection"""
        ip = SecurityUtils.get_client_ip(mock_request)

        assert ip == "192.168.1.1"

    def test_get_client_ip_no_client(self, mock_request):
        """Test IP detection when no client info available"""
        mock_request.client = None

        ip = SecurityUtils.get_client_ip(mock_request)

        assert ip == "unknown"

    @patch("app.utils.security.security_settings")
    def test_hash_ip_address_enabled(self, mock_settings):
        """Test IP hashing when enabled"""
        mock_settings.HASH_IP_ADDRESSES = True
        mock_settings.IP_HASH_SALT = "test_salt"

        hashed = SecurityUtils.hash_ip_address("192.168.1.1")

        assert hashed != "192.168.1.1"
        assert len(hashed) == 16
        assert isinstance(hashed, str)

    @patch("app.utils.security.security_settings")
    def test_hash_ip_address_disabled(self, mock_settings):
        """Test IP hashing when disabled"""
        mock_settings.HASH_IP_ADDRESSES = False

        hashed = SecurityUtils.hash_ip_address("192.168.1.1")

        assert hashed == "192.168.1.1"

    @patch("app.utils.security.security_settings")
    def test_hash_ip_address_deterministic(self, mock_settings):
        """Test IP hashing is deterministic"""
        mock_settings.HASH_IP_ADDRESSES = True
        mock_settings.IP_HASH_SALT = "test_salt"

        hash1 = SecurityUtils.hash_ip_address("192.168.1.1")
        hash2 = SecurityUtils.hash_ip_address("192.168.1.1")

        assert hash1 == hash2


class TestTrustedProxyHops:
    """
    IP del cliente con proxies de confianza (TRUSTED_PROXY_HOPS).

    Con N saltos, la IP es la entrada N-ésima desde la derecha de X-Forwarded-For: las
    anteriores las puede haber escrito el cliente. Con 0 saltos solo cuenta la IP del socket.
    """

    @pytest.fixture
    def set_hops(self, monkeypatch):
        def _set(hops):
            monkeypatch.setattr("app.utils.security.security_settings.TRUSTED_PROXY_HOPS", hops)

        return _set

    def test_one_hop_takes_last_entry(self, mock_request, set_hops):
        """El proxy añade la IP que vio; lo que el cliente escribió a la izquierda no cuenta"""
        set_hops(1)
        mock_request.headers = {"X-Forwarded-For": "6.6.6.6, 203.0.113.9"}

        assert SecurityUtils.get_client_ip(mock_request) == "203.0.113.9"

    def test_two_hops_takes_second_from_right(self, mock_request, set_hops):
        set_hops(2)
        mock_request.headers = {"X-Forwarded-For": "6.6.6.6, 203.0.113.9, 10.0.0.2"}

        assert SecurityUtils.get_client_ip(mock_request) == "203.0.113.9"

    def test_one_hop_single_entry(self, mock_request, set_hops):
        set_hops(1)
        mock_request.headers = {"X-Forwarded-For": "203.0.113.9"}

        assert SecurityUtils.get_client_ip(mock_request) == "203.0.113.9"

    def test_entries_are_stripped(self, mock_request, set_hops):
        set_hops(1)
        mock_request.headers = {"X-Forwarded-For": "6.6.6.6 ,   203.0.113.9  "}

        assert SecurityUtils.get_client_ip(mock_request) == "203.0.113.9"

    def test_fewer_entries_than_hops_falls_back_to_socket(self, mock_request, set_hops):
        """Cabecera más corta que la cadena esperada: no se fía y usa la IP del socket"""
        set_hops(2)
        mock_request.headers = {"X-Forwarded-For": "203.0.113.9"}

        assert SecurityUtils.get_client_ip(mock_request) == "192.168.1.1"

    def test_trusted_hops_without_header_uses_socket(self, mock_request, set_hops):
        set_hops(1)
        mock_request.headers = {}

        assert SecurityUtils.get_client_ip(mock_request) == "192.168.1.1"

    def test_x_real_ip_and_x_forwarded_are_ignored_with_hops(self, mock_request, set_hops):
        set_hops(1)
        mock_request.headers = {"X-Real-IP": "6.6.6.6", "X-Forwarded": "7.7.7.7"}

        assert SecurityUtils.get_client_ip(mock_request) == "192.168.1.1"

    def test_zero_hops_forged_header_does_not_change_the_rate_limit_key(
        self, mock_request, set_hops
    ):
        """Rotar X-Forwarded-For no cambia el identificador sobre el que se cuenta"""
        set_hops(0)
        keys = set()
        for forged in ("1.1.1.1", "2.2.2.2, 3.3.3.3", "203.0.113.50"):
            mock_request.headers = {"X-Forwarded-For": forged}
            keys.add(SecurityUtils.hash_ip_address(SecurityUtils.get_client_ip(mock_request)))

        assert len(keys) == 1

    def test_one_hop_rotating_leading_entries_does_not_change_the_key(self, mock_request, set_hops):
        """Con un proxy de confianza, falsificar las entradas de la izquierda no evade el límite"""
        set_hops(1)
        keys = set()
        for forged in ("1.1.1.1", "2.2.2.2, 3.3.3.3", "4.4.4.4"):
            mock_request.headers = {"X-Forwarded-For": f"{forged}, 203.0.113.9"}
            keys.add(SecurityUtils.hash_ip_address(SecurityUtils.get_client_ip(mock_request)))

        assert len(keys) == 1


class TestProxyHeaderTripwire:
    """
    Aviso de configuración: llega X-Forwarded-For pero TRUSTED_PROXY_HOPS=0.

    Detrás de un proxy todos los usuarios llegarían con la IP del proxy y los límites por IP
    serían globales. get_client_ip avisa una vez por proceso (IPs enmascaradas, nunca la
    cabecera completa) y no cambia el valor que devuelve.
    """

    PREFIX = "TRUSTED_PROXY_HOPS=0 pero llegan peticiones con X-Forwarded-For"

    @pytest.fixture(autouse=True)
    def tripwire(self, monkeypatch, caplog):
        """Producción con 0 saltos y bandera reiniciada"""
        import app.utils.security as security_module

        monkeypatch.setattr(security_module, "_proxy_header_warned", False)
        monkeypatch.setattr(security_module.security_settings, "DEVELOPMENT_MODE", False)
        monkeypatch.setattr(security_module.security_settings, "TRUSTED_PROXY_HOPS", 0)
        caplog.set_level(logging.WARNING, logger="app.utils.security")
        return security_module

    def _warnings(self, caplog):
        return [r for r in caplog.records if r.getMessage().startswith(self.PREFIX)]

    def test_warns_once_per_process(self, mock_request, caplog):
        mock_request.headers = {"X-Forwarded-For": "9.9.9.9, 10.1.2.3"}

        for _ in range(5):
            SecurityUtils.get_client_ip(mock_request)

        assert len(self._warnings(caplog)) == 1

    def test_process_flag_is_set_after_warning(self, mock_request, tripwire):
        mock_request.headers = {"X-Forwarded-For": "9.9.9.9, 10.1.2.3"}

        SecurityUtils.get_client_ip(mock_request)

        assert tripwire._proxy_header_warned is True

    def test_message_masks_ips_and_omits_the_header(self, mock_request, caplog):
        header = "9.9.9.9, 10.1.2.3, 172.16.5.7"
        mock_request.headers = {"X-Forwarded-For": header}

        SecurityUtils.get_client_ip(mock_request)

        (record,) = self._warnings(caplog)
        message = record.getMessage()
        assert "entradas=3" in message
        assert "[10.1.2.x, 172.16.5.x]" in message
        assert "socket=192.168.1.x" in message
        # Solo las dos últimas entradas: la primera (la que escribe el cliente) no aparece
        assert "9.9.9" not in caplog.text
        for full_ip in ("10.1.2.3", "172.16.5.7", "192.168.1.1"):
            assert full_ip not in caplog.text
        assert header not in caplog.text

    def test_single_entry_is_reported(self, mock_request, caplog):
        mock_request.headers = {"X-Forwarded-For": "203.0.113.9"}

        SecurityUtils.get_client_ip(mock_request)

        (record,) = self._warnings(caplog)
        assert "entradas=1" in record.getMessage()
        assert "[203.0.113.x]" in record.getMessage()
        assert "203.0.113.9" not in caplog.text

    def test_garbage_entries_are_not_logged(self, mock_request, caplog):
        mock_request.headers = {"X-Forwarded-For": "<script>alert(1)</script>, evil\ttext"}

        SecurityUtils.get_client_ip(mock_request)

        (record,) = self._warnings(caplog)
        assert "[***, ***]" in record.getMessage()
        assert "script" not in caplog.text
        assert "evil" not in caplog.text

    @pytest.mark.parametrize("hops", [1, 2])
    def test_no_warning_with_trusted_hops(self, mock_request, caplog, monkeypatch, hops):
        monkeypatch.setattr("app.utils.security.security_settings.TRUSTED_PROXY_HOPS", hops)
        mock_request.headers = {"X-Forwarded-For": "6.6.6.6, 203.0.113.9, 10.0.0.2"}

        SecurityUtils.get_client_ip(mock_request)

        assert self._warnings(caplog) == []

    def test_no_warning_without_header(self, mock_request, caplog):
        mock_request.headers = {}

        SecurityUtils.get_client_ip(mock_request)

        assert self._warnings(caplog) == []

    @pytest.mark.parametrize("header", ["", "   ", " , ,"])
    def test_no_warning_with_empty_header(self, mock_request, caplog, header):
        mock_request.headers = {"X-Forwarded-For": header}

        SecurityUtils.get_client_ip(mock_request)

        assert self._warnings(caplog) == []

    def test_no_warning_in_development(self, mock_request, caplog, monkeypatch):
        monkeypatch.setattr("app.utils.security.security_settings.DEVELOPMENT_MODE", True)
        mock_request.headers = {"X-Forwarded-For": "9.9.9.9, 10.1.2.3"}

        SecurityUtils.get_client_ip(mock_request)

        assert self._warnings(caplog) == []

    @pytest.mark.parametrize(
        "hops,header,expected",
        [
            (0, "9.9.9.9, 10.1.2.3", "192.168.1.1"),
            (0, None, "192.168.1.1"),
            (1, "6.6.6.6, 203.0.113.9", "203.0.113.9"),
            (2, "203.0.113.9", "192.168.1.1"),
        ],
    )
    def test_returned_ip_is_unchanged_by_the_warning(
        self, mock_request, monkeypatch, hops, header, expected
    ):
        """El aviso es solo informativo: el valor es el mismo con y sin aviso"""
        monkeypatch.setattr("app.utils.security.security_settings.TRUSTED_PROXY_HOPS", hops)
        mock_request.headers = {} if header is None else {"X-Forwarded-For": header}

        first = SecurityUtils.get_client_ip(mock_request)  # con 0 saltos y cabecera, avisa
        second = SecurityUtils.get_client_ip(mock_request)  # bandera ya activada

        assert first == second == expected


class TestMaskIp:
    """_mask_ip: IP enmascarada para el log (nunca la dirección completa)"""

    @pytest.mark.parametrize(
        "ip,expected",
        [
            ("203.0.113.9", "203.0.113.x"),
            ("10.1.2.3", "10.1.2.x"),
            ("2001:db8:85a3::8a2e:370:7334", "2001:db8::x"),
            ("2001:0db8:0000:0000:0000:0000:0000:0001", "2001:db8::x"),
            ("::1", "0:0::x"),
        ],
    )
    def test_masks_valid_addresses(self, ip, expected):
        from app.utils.security import _mask_ip

        assert _mask_ip(ip) == expected

    @pytest.mark.parametrize(
        "value",
        ["", "unknown", "1.2.3.4:8080", "1.2.3", "999.1.1.1", "<script>1.2.3.4</script>"],
    )
    def test_anything_else_is_fully_masked(self, value):
        from app.utils.security import _mask_ip

        assert _mask_ip(value) == "***"


# ============================================================================
# USER-AGENT PARSING TESTS
# ============================================================================


class TestUserAgentParsing:
    """Tests for user-agent parsing"""

    def test_get_user_agent_info_chrome(self, mock_request):
        """Test parsing Chrome user-agent"""
        mock_request.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        info = SecurityUtils.get_user_agent_info(mock_request)

        assert "Chrome" in info["browser"]
        assert "Windows" in info["os"]
        assert info["is_pc"] is True
        assert info["is_mobile"] is False
        assert info["is_bot"] is False

    def test_get_user_agent_info_mobile(self, mock_request):
        """Test parsing mobile user-agent"""
        mock_request.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
        }

        info = SecurityUtils.get_user_agent_info(mock_request)

        assert info["is_mobile"] is True
        assert "iPhone" in info["device"]

    def test_get_user_agent_info_empty(self, mock_request):
        """Test parsing empty user-agent"""
        mock_request.headers = {}

        info = SecurityUtils.get_user_agent_info(mock_request)

        assert "raw" in info
        assert info["raw"] == ""


# ============================================================================
# HMAC SIGNATURE TESTS
# ============================================================================


class TestHMACSignature:
    """Tests for HMAC signature creation and verification"""

    def test_create_hmac_signature(self):
        """Test HMAC signature creation"""
        signature = SecurityUtils.create_hmac_signature("test data", "secret_key")

        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex = 64 chars

    def test_create_hmac_signature_deterministic(self):
        """Test HMAC signature is deterministic"""
        sig1 = SecurityUtils.create_hmac_signature("test data", "secret_key")
        sig2 = SecurityUtils.create_hmac_signature("test data", "secret_key")

        assert sig1 == sig2

    def test_create_hmac_signature_different_data(self):
        """Test different data produces different signatures"""
        sig1 = SecurityUtils.create_hmac_signature("data1", "secret_key")
        sig2 = SecurityUtils.create_hmac_signature("data2", "secret_key")

        assert sig1 != sig2

    def test_verify_hmac_signature_valid(self):
        """Test verification of valid HMAC signature"""
        data = "test data"
        secret = "secret_key"
        signature = SecurityUtils.create_hmac_signature(data, secret)

        is_valid = SecurityUtils.verify_hmac_signature(data, signature, secret)

        assert is_valid is True

    def test_verify_hmac_signature_invalid(self):
        """Test verification of invalid HMAC signature"""
        data = "test data"
        secret = "secret_key"
        signature = "invalid_signature"

        is_valid = SecurityUtils.verify_hmac_signature(data, signature, secret)

        assert is_valid is False

    def test_verify_hmac_signature_wrong_secret(self):
        """Test verification fails with wrong secret"""
        data = "test data"
        signature = SecurityUtils.create_hmac_signature(data, "secret1")

        is_valid = SecurityUtils.verify_hmac_signature(data, signature, "secret2")

        assert is_valid is False

    def test_verify_hmac_signature_tampered_data(self):
        """Test verification fails with tampered data"""
        original_data = "original data"
        secret = "secret_key"
        signature = SecurityUtils.create_hmac_signature(original_data, secret)

        is_valid = SecurityUtils.verify_hmac_signature("tampered data", signature, secret)

        assert is_valid is False


# ============================================================================
# URL VALIDATION TESTS
# ============================================================================


class TestURLValidation:
    """Tests for safe redirect URL validation"""

    def test_is_safe_redirect_url_relative(self):
        """Test relative URLs are safe"""
        assert SecurityUtils.is_safe_redirect_url("/dashboard") is True
        assert SecurityUtils.is_safe_redirect_url("/user/profile") is True

    def test_is_safe_redirect_url_protocol_relative(self):
        """Test protocol-relative URLs are unsafe"""
        assert SecurityUtils.is_safe_redirect_url("//evil.com") is False

    def test_is_safe_redirect_url_empty(self):
        """Test empty URL is unsafe"""
        assert SecurityUtils.is_safe_redirect_url("") is False
        assert SecurityUtils.is_safe_redirect_url(None) is False

    def test_is_safe_redirect_url_allowed_host(self):
        """Test absolute URL with allowed host"""
        allowed_hosts = ["example.com", "subdomain.example.com"]

        assert SecurityUtils.is_safe_redirect_url("https://example.com/page", allowed_hosts) is True

    def test_is_safe_redirect_url_disallowed_host(self):
        """Test absolute URL with disallowed host"""
        allowed_hosts = ["example.com"]

        assert SecurityUtils.is_safe_redirect_url("https://evil.com/page", allowed_hosts) is False

    def test_is_safe_redirect_url_no_allowed_hosts(self):
        """Test absolute URL without allowed hosts list"""
        assert SecurityUtils.is_safe_redirect_url("https://example.com") is False


# ============================================================================
# SENSITIVE DATA MASKING TESTS
# ============================================================================


class TestSensitiveDataMasking:
    """Tests for sensitive data masking"""

    def test_mask_sensitive_data_basic(self):
        """Test basic data masking"""
        result = SecurityUtils.mask_sensitive_data("1234567890")

        assert result == "******7890"

    def test_mask_sensitive_data_custom_visible(self):
        """Test masking with custom visible characters"""
        result = SecurityUtils.mask_sensitive_data("1234567890", visible_chars=2)

        assert result == "********90"

    def test_mask_sensitive_data_custom_mask_char(self):
        """Test masking with custom mask character"""
        result = SecurityUtils.mask_sensitive_data("1234567890", mask_char="X")

        assert result == "XXXXXX7890"

    def test_mask_sensitive_data_short_string(self):
        """Test masking string shorter than visible chars"""
        result = SecurityUtils.mask_sensitive_data("123")

        assert result == "***"

    def test_mask_sensitive_data_empty(self):
        """Test masking empty string"""
        result = SecurityUtils.mask_sensitive_data("")

        assert result == ""


# ============================================================================
# PASSWORD STRENGTH VALIDATION TESTS
# ============================================================================


class TestPasswordStrengthValidation:
    """Tests for password strength validation"""

    def test_validate_password_strength_strong(self):
        """Test validation of strong password"""
        result = SecurityUtils.validate_password_strength("MyStr0ng!Pass")

        assert result["is_valid"] is True
        assert len(result["errors"]) == 0
        assert result["score"] >= 4

    def test_validate_password_strength_too_short(self):
        """Test validation of too short password"""
        result = SecurityUtils.validate_password_strength("Short1")

        assert result["is_valid"] is False
        assert any("8 caracteres" in err for err in result["errors"])

    def test_validate_password_strength_no_lowercase(self):
        """Test validation of password without lowercase"""
        result = SecurityUtils.validate_password_strength("PASSWORD123")

        assert result["is_valid"] is False
        assert any("minúscula" in err for err in result["errors"])

    def test_validate_password_strength_no_uppercase(self):
        """Test validation of password without uppercase"""
        result = SecurityUtils.validate_password_strength("password123")

        assert result["is_valid"] is False
        assert any("mayúscula" in err for err in result["errors"])

    def test_validate_password_strength_no_digit(self):
        """Test validation of password without digit"""
        result = SecurityUtils.validate_password_strength("PasswordABC")

        assert result["is_valid"] is False
        assert any("número" in err for err in result["errors"])

    def test_validate_password_strength_common_pattern(self):
        """Test validation detects common patterns"""
        result = SecurityUtils.validate_password_strength("Password123456")

        assert result["is_valid"] is False
        assert any("patrones comunes" in err for err in result["errors"])

    def test_validate_password_strength_with_special_chars(self):
        """Test validation gives bonus for special chars"""
        result = SecurityUtils.validate_password_strength("MyStr0ng!Pass")

        assert result["score"] >= 5

    def test_validate_password_strength_long_password(self):
        """Test validation gives bonus for long password"""
        result = SecurityUtils.validate_password_strength("MyVeryLongStr0ngPassword!")

        assert result["score"] >= 6


# ============================================================================
# CONVENIENCE FUNCTIONS TESTS
# ============================================================================


class TestConvenienceFunctions:
    """Tests for module-level convenience functions"""

    def test_generate_otp_convenience(self):
        """Test convenience OTP generation function"""
        otp = generate_otp()

        assert isinstance(otp, str)
        assert len(otp) > 0

    def test_sanitize_input_convenience(self):
        """Test convenience sanitize function"""
        result = sanitize_input("Hello <script>World</script>")

        assert "script" not in result.lower()
        assert "Hello" in result

    def test_get_client_ip_convenience(self, mock_request):
        """Test convenience get client IP function"""
        ip = get_client_ip(mock_request)

        assert isinstance(ip, str)
        assert len(ip) > 0


# ============================================================================
# PROXY STARTUP WARNINGS TESTS
# ============================================================================


class TestProxyStartupWarnings:
    """validate_security_config avisa en producción de una configuración de proxy peligrosa"""

    HOPS_WARNING = "TRUSTED_PROXY_HOPS=0 en Render"
    ALLOW_ALL_WARNING = "FORWARDED_ALLOW_IPS=*"

    @pytest.fixture
    def production(self, monkeypatch):
        """Producción con secretos válidos, 0 saltos y sin RENDER ni FORWARDED_ALLOW_IPS"""
        settings = "app.config.security.security_settings"
        monkeypatch.setattr(f"{settings}.DEVELOPMENT_MODE", False)
        monkeypatch.setattr(f"{settings}.CSRF_SECRET_KEY", "csrf-secret-de-prueba")
        monkeypatch.setattr(f"{settings}.IP_HASH_SALT", "ip-salt-de-prueba")
        monkeypatch.setattr(f"{settings}.TRUSTED_PROXY_HOPS", 0)
        monkeypatch.delenv("RENDER", raising=False)
        monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
        return monkeypatch

    @pytest.mark.parametrize("render_value", ["true", "TRUE", " True "])
    def test_warns_on_render_with_zero_hops(self, production, capsys, render_value):
        from app.config.security import validate_security_config

        production.setenv("RENDER", render_value)

        assert validate_security_config() is True  # es un aviso, no un error crítico
        out = capsys.readouterr().out
        assert self.HOPS_WARNING in out
        assert "csrf-secret-de-prueba" not in out

    def test_no_warning_with_hops_set(self, production, capsys):
        from app.config.security import validate_security_config

        production.setenv("RENDER", "true")
        production.setattr("app.config.security.security_settings.TRUSTED_PROXY_HOPS", 1)

        assert validate_security_config() is True
        assert self.HOPS_WARNING not in capsys.readouterr().out

    @pytest.mark.parametrize("render_value", [None, "", "false", "0"])
    def test_no_warning_outside_render(self, production, capsys, render_value):
        from app.config.security import validate_security_config

        if render_value is not None:
            production.setenv("RENDER", render_value)

        assert validate_security_config() is True
        assert self.HOPS_WARNING not in capsys.readouterr().out

    def test_no_warnings_in_development(self, production, capsys):
        from app.config.security import validate_security_config

        production.setattr("app.config.security.security_settings.DEVELOPMENT_MODE", True)
        production.setenv("RENDER", "true")
        production.setenv("FORWARDED_ALLOW_IPS", "*")

        assert validate_security_config() is True
        out = capsys.readouterr().out
        assert self.HOPS_WARNING not in out
        assert self.ALLOW_ALL_WARNING not in out

    @pytest.mark.parametrize("value", ["*", " * "])
    def test_warns_when_forwarded_allow_ips_is_wildcard(self, production, capsys, value):
        from app.config.security import validate_security_config

        production.setenv("FORWARDED_ALLOW_IPS", value)

        assert validate_security_config() is True
        out = capsys.readouterr().out
        assert self.ALLOW_ALL_WARNING in out
        assert "suplantable" in out

    @pytest.mark.parametrize("value", ["", "127.0.0.1", "10.0.0.5, 10.0.0.6"])
    def test_no_wildcard_warning_with_specific_ips(self, production, capsys, value):
        from app.config.security import validate_security_config

        production.setenv("FORWARDED_ALLOW_IPS", value)

        assert validate_security_config() is True
        assert self.ALLOW_ALL_WARNING not in capsys.readouterr().out
