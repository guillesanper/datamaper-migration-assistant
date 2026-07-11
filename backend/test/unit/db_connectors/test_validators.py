"""
Unit tests for app.utils.db_adapters.validators module

Tests for security validators:
- SQL injection detection and prevention
- Identifier validation (tables, columns, schemas, indexes)
- Reserved keyword blocking
- Connection configuration validation
- Logging sanitization
"""

import pytest

from app.utils.db_adapters.exceptions import DBValidationError
from app.utils.db_adapters.validators import (
    detect_sql_injection_attempt,
    sanitize_for_logging,
    validate_column_name,
    validate_connection_config,
    validate_identifier,
    validate_index_name,
    validate_schema_name,
    validate_table_name,
)

# ============================================================================
# TEST validate_identifier()
# ============================================================================


class TestValidateIdentifier:
    """Tests for validate_identifier() function"""

    def test_valid_identifiers(self):
        """Test: Valid identifiers should pass validation"""
        valid = ["users", "user_profiles", "UserProfiles", "user123", "_internal", "a", "_"]
        for identifier in valid:
            result = validate_identifier(identifier)
            assert result == identifier

    def test_invalid_identifiers_raise_error(self):
        """Test: Invalid identifiers should raise DBValidationError"""
        invalid = ["", "123users", "user-profiles", "user.profiles", "user profiles"]
        for identifier in invalid:
            with pytest.raises(DBValidationError):
                validate_identifier(identifier)

    def test_reserved_keywords_blocked(self):
        """Test: SQL reserved keywords should be blocked"""
        keywords = ["SELECT", "INSERT", "DROP", "DELETE", "UNION"]
        for keyword in keywords:
            with pytest.raises(DBValidationError, match="reserved SQL keyword"):
                validate_identifier(keyword)

    def test_sql_injection_attempts_blocked(self):
        """Test: SQL injection attempts should be blocked"""
        injections = [
            "users'; DROP TABLE users;--",
            "admin'--",
            "1' OR '1'='1",
        ]
        for injection in injections:
            with pytest.raises(DBValidationError):
                validate_identifier(injection)


# ============================================================================
# TEST validate_table_name()
# ============================================================================


class TestValidateTableName:
    """Tests for validate_table_name() function"""

    def test_valid_table_names(self):
        """Test: Valid table names should pass validation"""
        valid = ["users", "user_profiles", "orders_2024"]
        for table in valid:
            result = validate_table_name(table)
            assert result == table

    def test_invalid_table_names(self):
        """Test: Invalid table names should raise DBValidationError"""
        with pytest.raises(DBValidationError, match="Table name"):
            validate_table_name("invalid-table")


# ============================================================================
# TEST detect_sql_injection_attempt()
# ============================================================================


class TestDetectSQLInjectionAttempt:
    """Tests for detect_sql_injection_attempt() function"""

    def test_clean_values_not_flagged(self):
        """Test: Clean values should not be flagged"""
        clean = ["users", "user_profiles", "valid_table_name"]
        for value in clean:
            assert detect_sql_injection_attempt(value) is False

    def test_sql_injection_patterns_detected(self):
        """Test: SQL injection patterns should be detected"""
        injections = [
            "users; DROP TABLE users",
            "table--comment",
            "UNION SELECT",
            "EXEC xp_cmdshell",
        ]
        for injection in injections:
            assert detect_sql_injection_attempt(injection) is True


# ============================================================================
# TEST sanitize_for_logging()
# ============================================================================


class TestSanitizeForLogging:
    """Tests for sanitize_for_logging() function"""

    def test_short_string_not_truncated(self):
        """Test: Short strings should not be truncated"""
        value = "short string"
        result = sanitize_for_logging(value)
        assert result == value

    def test_long_string_truncated(self):
        """Test: Long strings should be truncated"""
        value = "a" * 150
        result = sanitize_for_logging(value, max_length=100)
        assert result.endswith("...")

    def test_empty_string_returns_placeholder(self):
        """Test: Empty string should return placeholder"""
        assert sanitize_for_logging("") == "[empty]"


# ============================================================================
# TEST validate_connection_config()
# ============================================================================


class TestValidateConnectionConfig:
    """Tests for validate_connection_config() function"""

    def test_valid_config(self):
        """Test: Valid configuration should pass"""
        config = {
            "host": "localhost",
            "port": 5432,
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
        }
        result = validate_connection_config(config)
        assert result == config

    def test_missing_required_field(self):
        """Test: Missing required field should raise error"""
        config = {"host": "localhost", "port": 5432}
        with pytest.raises(DBValidationError, match="Missing required field"):
            validate_connection_config(config)

    def test_invalid_port(self):
        """Test: Invalid port should raise error"""
        config = {
            "host": "localhost",
            "port": 99999,
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
        }
        with pytest.raises(DBValidationError, match="Invalid port"):
            validate_connection_config(config)
