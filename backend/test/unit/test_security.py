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

    def test_get_client_ip_x_forwarded_for(self, mock_request):
        """Test IP detection from X-Forwarded-For header"""
        mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}

        ip = SecurityUtils.get_client_ip(mock_request)

        assert ip == "203.0.113.1"

    def test_get_client_ip_x_real_ip(self, mock_request):
        """Test IP detection from X-Real-IP header"""
        mock_request.headers = {"X-Real-IP": "203.0.113.1"}

        ip = SecurityUtils.get_client_ip(mock_request)

        assert ip == "203.0.113.1"

    def test_get_client_ip_x_forwarded(self, mock_request):
        """Test IP detection from X-Forwarded header"""
        mock_request.headers = {"X-Forwarded": "203.0.113.1"}

        ip = SecurityUtils.get_client_ip(mock_request)

        assert ip == "203.0.113.1"

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
