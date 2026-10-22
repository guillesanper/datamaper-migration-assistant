"""ENCRYPTION_MASTER_KEY estricta y validación de secretos al arrancar en producción."""

import base64
import os
from unittest.mock import MagicMock

import pytest

from app.config import security as security_config
from app.services.db_connection_service import DBConnectionService
from app.utils.master_key import InvalidMasterKeyError, parse_master_key

VALID_KEY = base64.b64encode(os.urandom(32)).decode()


class TestParseMasterKey:
    def test_valid_base64_key(self):
        assert len(parse_master_key(VALID_KEY)) == 32

    def test_raw_32_bytes(self):
        assert parse_master_key(b"k" * 32) == b"k" * 32

    @pytest.mark.parametrize(
        "value",
        [
            "password",  # base64 válido de 6 bytes
            "a" * 44,  # 33 bytes
            "test-encryption-key-min-32-chars-long-for-security",  # no es base64
            "",
            base64.b64encode(b"short").decode(),
        ],
    )
    def test_weak_or_malformed_keys_are_rejected(self, value):
        with pytest.raises(InvalidMasterKeyError):
            parse_master_key(value)

    def test_service_refuses_weak_key(self):
        with pytest.raises(InvalidMasterKeyError):
            DBConnectionService(MagicMock(), "password")


class TestStartupValidation:
    @pytest.fixture
    def production(self, monkeypatch):
        monkeypatch.setattr(type(security_config.security_settings), "DEVELOPMENT_MODE", False)
        monkeypatch.setenv("SECRET_KEY", "s" * 40)
        monkeypatch.setenv("ENCRYPTION_MASTER_KEY", VALID_KEY)
        return monkeypatch

    def test_valid_configuration_passes(self, production):
        assert security_config.validate_security_config()

    def test_empty_secret_key_fails(self, production):
        production.setenv("SECRET_KEY", "")
        with pytest.raises(ValueError, match="SECRET_KEY"):
            security_config.validate_security_config()

    def test_invalid_master_key_fails(self, production):
        production.setenv("ENCRYPTION_MASTER_KEY", "password")
        with pytest.raises(ValueError, match="ENCRYPTION_MASTER_KEY"):
            security_config.validate_security_config()

    def test_missing_master_key_is_only_a_warning(self, production):
        production.delenv("ENCRYPTION_MASTER_KEY")
        assert security_config.validate_security_config()
