"""
Unit tests for app.utils.encryption module

Tests for EncryptionManager:
- Salt and nonce generation
- Master key hash derivation (Argon2id)
- Encryption key derivation (Argon2id)
- Master key verification
- AES-256-GCM encryption/decryption
- Base64 encoding/decoding
- High-level encrypt/decrypt functions
"""

import base64
import secrets
from unittest.mock import MagicMock, patch

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.utils.encryption import (
    ARGON2_AVAILABLE,
    DecryptionError,
    EncryptionError,
    EncryptionManager,
    KeyDerivationError,
    decrypt_text,
    encrypt_text,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def encryption_manager():
    """Provide an EncryptionManager instance"""
    return EncryptionManager()


@pytest.fixture
def test_passphrase():
    """Provide a test passphrase"""
    return "TestSecurePassphrase123!"


@pytest.fixture
def test_salt():
    """Provide a test salt (16 bytes)"""
    return secrets.token_bytes(16)


@pytest.fixture
def test_encryption_key():
    """Provide a test 256-bit encryption key"""
    return secrets.token_bytes(32)


@pytest.fixture
def test_nonce():
    """Provide a test nonce (12 bytes)"""
    return secrets.token_bytes(12)


@pytest.fixture
def test_plaintext():
    """Provide test plaintext"""
    return "Sensitive data: user_financial_records"


# ============================================================================
# SALT AND NONCE GENERATION TESTS
# ============================================================================


class TestSaltAndNonceGeneration:
    """Tests for cryptographically secure random generation"""

    def test_generate_salt_default_length(self):
        """Test salt generation with default length (16 bytes)"""
        salt = EncryptionManager.generate_salt()

        assert isinstance(salt, bytes)
        assert len(salt) == 16
        assert len(salt) == EncryptionManager.ARGON2_SALT_LENGTH

    def test_generate_salt_custom_length(self):
        """Test salt generation with custom length"""
        custom_length = 32
        salt = EncryptionManager.generate_salt(custom_length)

        assert isinstance(salt, bytes)
        assert len(salt) == custom_length

    def test_generate_salt_uniqueness(self):
        """Test that generated salts are unique"""
        salt1 = EncryptionManager.generate_salt()
        salt2 = EncryptionManager.generate_salt()

        assert salt1 != salt2

    def test_generate_nonce_length(self):
        """Test nonce generation (12 bytes for GCM)"""
        nonce = EncryptionManager.generate_nonce()

        assert isinstance(nonce, bytes)
        assert len(nonce) == 12
        assert len(nonce) == EncryptionManager.AES_NONCE_LENGTH

    def test_generate_nonce_uniqueness(self):
        """Test that generated nonces are unique (critical for GCM security)"""
        nonces = [EncryptionManager.generate_nonce() for _ in range(100)]

        # All nonces should be unique
        assert len(set(nonces)) == 100


# ============================================================================
# KEY DERIVATION TESTS
# ============================================================================


class TestKeyDerivation:
    """Tests for Argon2id key derivation"""

    def test_derive_master_key_hash_success(self, encryption_manager, test_passphrase, test_salt):
        """Test successful master key hash derivation"""
        hash_result = encryption_manager.derive_master_key_hash(test_passphrase, test_salt)

        assert isinstance(hash_result, bytes)
        assert len(hash_result) == 32  # 256 bits
        assert len(hash_result) == EncryptionManager.ARGON2_HASH_LENGTH

    def test_derive_master_key_hash_deterministic(
        self, encryption_manager, test_passphrase, test_salt
    ):
        """Test that same inputs produce same hash (deterministic)"""
        hash1 = encryption_manager.derive_master_key_hash(test_passphrase, test_salt)
        hash2 = encryption_manager.derive_master_key_hash(test_passphrase, test_salt)

        assert hash1 == hash2

    def test_derive_master_key_hash_different_salt(self, encryption_manager, test_passphrase):
        """Test that different salts produce different hashes"""
        salt1 = secrets.token_bytes(16)
        salt2 = secrets.token_bytes(16)

        hash1 = encryption_manager.derive_master_key_hash(test_passphrase, salt1)
        hash2 = encryption_manager.derive_master_key_hash(test_passphrase, salt2)

        assert hash1 != hash2

    def test_derive_master_key_hash_empty_passphrase(self, encryption_manager, test_salt):
        """Test that empty passphrase raises error"""
        with pytest.raises(KeyDerivationError, match="Passphrase cannot be empty"):
            encryption_manager.derive_master_key_hash("", test_salt)

    def test_derive_master_key_hash_short_salt(self, encryption_manager, test_passphrase):
        """Test that short salt raises error"""
        short_salt = secrets.token_bytes(8)  # Less than 16 bytes

        with pytest.raises(KeyDerivationError, match="Salt must be at least 16 bytes"):
            encryption_manager.derive_master_key_hash(test_passphrase, short_salt)

    def test_derive_master_key_hash_custom_parameters(
        self, encryption_manager, test_passphrase, test_salt
    ):
        """Test custom Argon2 parameters"""
        hash_result = encryption_manager.derive_master_key_hash(
            test_passphrase, test_salt, memory_cost=32 * 1024, time_cost=2, parallelism=1  # 32 MiB
        )

        assert isinstance(hash_result, bytes)
        assert len(hash_result) == 32

    def test_derive_encryption_key_success(self, encryption_manager, test_passphrase, test_salt):
        """Test successful encryption key derivation"""
        key = encryption_manager.derive_encryption_key(test_passphrase, test_salt)

        assert isinstance(key, bytes)
        assert len(key) == 32  # 256 bits for AES-256
        assert len(key) == EncryptionManager.AES_KEY_LENGTH

    def test_derive_encryption_key_deterministic(
        self, encryption_manager, test_passphrase, test_salt
    ):
        """Test that encryption key derivation is deterministic"""
        key1 = encryption_manager.derive_encryption_key(test_passphrase, test_salt)
        key2 = encryption_manager.derive_encryption_key(test_passphrase, test_salt)

        assert key1 == key2

    def test_derive_encryption_key_different_from_hash(self, encryption_manager, test_passphrase):
        """Test that encryption key is different from master hash with different salts"""
        salt1 = secrets.token_bytes(16)
        salt2 = secrets.token_bytes(16)

        master_hash = encryption_manager.derive_master_key_hash(test_passphrase, salt1)
        enc_key = encryption_manager.derive_encryption_key(test_passphrase, salt2)

        # Different purposes should use different salts
        assert master_hash != enc_key

    def test_derive_encryption_key_empty_passphrase(self, encryption_manager, test_salt):
        """Test that empty passphrase raises error"""
        with pytest.raises(KeyDerivationError, match="Passphrase cannot be empty"):
            encryption_manager.derive_encryption_key("", test_salt)

    def test_derive_encryption_key_short_salt(self, encryption_manager, test_passphrase):
        """Test that short salt raises error"""
        short_salt = secrets.token_bytes(8)

        with pytest.raises(KeyDerivationError, match="Salt must be at least 16 bytes"):
            encryption_manager.derive_encryption_key(test_passphrase, short_salt)


# ============================================================================
# MASTER KEY VERIFICATION TESTS
# ============================================================================


class TestMasterKeyVerification:
    """Tests for master key passphrase verification"""

    def test_verify_master_key_correct_passphrase(
        self, encryption_manager, test_passphrase, test_salt
    ):
        """Test verification with correct passphrase"""
        # Derive hash
        stored_hash = encryption_manager.derive_master_key_hash(test_passphrase, test_salt)

        # Verify
        is_valid = encryption_manager.verify_master_key(test_passphrase, stored_hash, test_salt)

        assert is_valid is True

    def test_verify_master_key_wrong_passphrase(
        self, encryption_manager, test_passphrase, test_salt
    ):
        """Test verification with wrong passphrase"""
        # Derive hash with correct passphrase
        stored_hash = encryption_manager.derive_master_key_hash(test_passphrase, test_salt)

        # Verify with wrong passphrase
        is_valid = encryption_manager.verify_master_key("WrongPassword123", stored_hash, test_salt)

        assert is_valid is False

    def test_verify_master_key_wrong_salt(self, encryption_manager, test_passphrase):
        """Test verification with wrong salt"""
        salt1 = secrets.token_bytes(16)
        salt2 = secrets.token_bytes(16)

        # Derive hash with salt1
        stored_hash = encryption_manager.derive_master_key_hash(test_passphrase, salt1)

        # Verify with salt2 (wrong salt)
        is_valid = encryption_manager.verify_master_key(test_passphrase, stored_hash, salt2)

        assert is_valid is False

    def test_verify_master_key_exception_handling(self, encryption_manager):
        """Test that exceptions during verification return False"""
        # Invalid inputs that would cause exception
        is_valid = encryption_manager.verify_master_key(
            "test", b"invalid_hash", b"short"  # Salt too short
        )

        assert is_valid is False


# ============================================================================
# AES-GCM ENCRYPTION/DECRYPTION TESTS
# ============================================================================


class TestAESGCMEncryption:
    """Tests for AES-256-GCM encryption and decryption"""

    def test_encrypt_field_success(self, encryption_manager, test_plaintext, test_encryption_key):
        """Test successful field encryption"""
        ciphertext, nonce = encryption_manager.encrypt_field(test_plaintext, test_encryption_key)

        assert isinstance(ciphertext, bytes)
        assert isinstance(nonce, bytes)
        assert len(nonce) == 12
        assert len(ciphertext) > 0
        assert ciphertext != test_plaintext.encode("utf-8")

    def test_encrypt_field_with_custom_nonce(
        self, encryption_manager, test_plaintext, test_encryption_key, test_nonce
    ):
        """Test encryption with custom nonce"""
        ciphertext, returned_nonce = encryption_manager.encrypt_field(
            test_plaintext, test_encryption_key, nonce=test_nonce
        )

        assert returned_nonce == test_nonce

    def test_encrypt_field_empty_string(self, encryption_manager, test_encryption_key):
        """Test encrypting empty string (should succeed)"""
        ciphertext, nonce = encryption_manager.encrypt_field("", test_encryption_key)

        assert isinstance(ciphertext, bytes)
        assert isinstance(nonce, bytes)

    def test_encrypt_field_invalid_key_length(self, encryption_manager, test_plaintext):
        """Test encryption with invalid key length"""
        short_key = secrets.token_bytes(16)  # 128-bit key (need 256-bit)

        with pytest.raises(EncryptionError, match="Encryption key must be 32 bytes"):
            encryption_manager.encrypt_field(test_plaintext, short_key)

    def test_encrypt_field_invalid_nonce_length(
        self, encryption_manager, test_plaintext, test_encryption_key
    ):
        """Test encryption with invalid nonce length"""
        short_nonce = secrets.token_bytes(8)  # Less than 12 bytes

        with pytest.raises(EncryptionError, match="Nonce must be 12 bytes"):
            encryption_manager.encrypt_field(test_plaintext, test_encryption_key, nonce=short_nonce)

    def test_decrypt_field_success(self, encryption_manager, test_plaintext, test_encryption_key):
        """Test successful field decryption"""
        # Encrypt first
        ciphertext, nonce = encryption_manager.encrypt_field(test_plaintext, test_encryption_key)

        # Decrypt
        decrypted = encryption_manager.decrypt_field(ciphertext, nonce, test_encryption_key)

        assert decrypted == test_plaintext

    def test_decrypt_field_wrong_key(self, encryption_manager, test_plaintext, test_encryption_key):
        """Test decryption with wrong key"""
        # Encrypt
        ciphertext, nonce = encryption_manager.encrypt_field(test_plaintext, test_encryption_key)

        # Try to decrypt with wrong key
        wrong_key = secrets.token_bytes(32)

        with pytest.raises(DecryptionError, match="invalid authentication tag"):
            encryption_manager.decrypt_field(ciphertext, nonce, wrong_key)

    def test_decrypt_field_tampered_ciphertext(
        self, encryption_manager, test_plaintext, test_encryption_key
    ):
        """Test decryption of tampered ciphertext (tampering detection)"""
        # Encrypt
        ciphertext, nonce = encryption_manager.encrypt_field(test_plaintext, test_encryption_key)

        # Tamper with ciphertext
        tampered = bytearray(ciphertext)
        tampered[0] ^= 1  # Flip one bit

        with pytest.raises(DecryptionError, match="invalid authentication tag"):
            encryption_manager.decrypt_field(bytes(tampered), nonce, test_encryption_key)

    def test_decrypt_field_empty_ciphertext(
        self, encryption_manager, test_nonce, test_encryption_key
    ):
        """Test decryption with empty ciphertext"""
        with pytest.raises(DecryptionError, match="Ciphertext cannot be empty"):
            encryption_manager.decrypt_field(b"", test_nonce, test_encryption_key)

    def test_decrypt_field_invalid_nonce_length(self, encryption_manager, test_encryption_key):
        """Test decryption with invalid nonce length"""
        ciphertext = secrets.token_bytes(32)
        short_nonce = secrets.token_bytes(8)

        with pytest.raises(DecryptionError, match="Nonce must be 12 bytes"):
            encryption_manager.decrypt_field(ciphertext, short_nonce, test_encryption_key)

    def test_decrypt_field_invalid_key_length(self, encryption_manager, test_nonce):
        """Test decryption with invalid key length"""
        ciphertext = secrets.token_bytes(32)
        short_key = secrets.token_bytes(16)

        with pytest.raises(DecryptionError, match="Encryption key must be 32 bytes"):
            encryption_manager.decrypt_field(ciphertext, test_nonce, short_key)

    def test_encrypt_decrypt_roundtrip(self, encryption_manager, test_encryption_key):
        """Test full encrypt-decrypt roundtrip with various data"""
        test_data = [
            "Simple text",
            "Text with special chars: !@#$%^&*()",
            "Unicode: 你好世界 🌍",
            "Multi\nline\ntext",
            "",  # Empty string
        ]

        for plaintext in test_data:
            ciphertext, nonce = encryption_manager.encrypt_field(plaintext, test_encryption_key)
            decrypted = encryption_manager.decrypt_field(ciphertext, nonce, test_encryption_key)

            assert decrypted == plaintext


# ============================================================================
# BASE64 ENCODING/DECODING TESTS
# ============================================================================


class TestBase64EncodingDecoding:
    """Tests for base64 encoding/decoding for storage"""

    def test_encode_for_storage(self, encryption_manager):
        """Test encoding binary data to base64"""
        data = b"test binary data"
        encoded = encryption_manager.encode_for_storage(data)

        assert isinstance(encoded, str)
        # Verify it's valid base64
        assert base64.b64decode(encoded) == data

    def test_decode_from_storage(self, encryption_manager):
        """Test decoding base64 to binary"""
        data = b"test binary data"
        encoded = base64.b64encode(data).decode("ascii")

        decoded = encryption_manager.decode_from_storage(encoded)

        assert decoded == data

    def test_encode_decode_roundtrip(self, encryption_manager):
        """Test encode-decode roundtrip"""
        original_data = secrets.token_bytes(32)

        encoded = encryption_manager.encode_for_storage(original_data)
        decoded = encryption_manager.decode_from_storage(encoded)

        assert decoded == original_data

    def test_decode_invalid_base64(self, encryption_manager):
        """Test decoding invalid base64 raises error"""
        invalid_base64 = "invalid!@#$%"

        with pytest.raises(DecryptionError, match="Failed to decode data"):
            encryption_manager.decode_from_storage(invalid_base64)


# ============================================================================
# HIGH-LEVEL FUNCTIONS TESTS
# ============================================================================


class TestHighLevelFunctions:
    """Tests for convenience encrypt_text/decrypt_text functions"""

    def test_encrypt_text(self, test_plaintext, test_passphrase, test_salt):
        """Test high-level encrypt_text function"""
        encoded_ciphertext, encoded_nonce = encrypt_text(test_plaintext, test_passphrase, test_salt)

        assert isinstance(encoded_ciphertext, str)
        assert isinstance(encoded_nonce, str)
        # Verify they're valid base64
        base64.b64decode(encoded_ciphertext)
        base64.b64decode(encoded_nonce)

    def test_decrypt_text(self, test_plaintext, test_passphrase, test_salt):
        """Test high-level decrypt_text function"""
        # Encrypt first
        encoded_ciphertext, encoded_nonce = encrypt_text(test_plaintext, test_passphrase, test_salt)

        # Decrypt
        decrypted = decrypt_text(encoded_ciphertext, encoded_nonce, test_passphrase, test_salt)

        assert decrypted == test_plaintext

    def test_encrypt_decrypt_text_roundtrip(self, test_passphrase, test_salt):
        """Test full roundtrip with high-level functions"""
        test_data = [
            "Simple message",
            "Special chars: !@#$%^&*()",
            "Unicode: 你好 🌍",
            "",
        ]

        for plaintext in test_data:
            encoded_ciphertext, encoded_nonce = encrypt_text(plaintext, test_passphrase, test_salt)
            decrypted = decrypt_text(encoded_ciphertext, encoded_nonce, test_passphrase, test_salt)

            assert decrypted == plaintext

    def test_decrypt_text_wrong_passphrase(self, test_plaintext, test_passphrase, test_salt):
        """Test decrypt with wrong passphrase"""
        # Encrypt
        encoded_ciphertext, encoded_nonce = encrypt_text(test_plaintext, test_passphrase, test_salt)

        # Try to decrypt with wrong passphrase
        with pytest.raises(DecryptionError):
            decrypt_text(encoded_ciphertext, encoded_nonce, "WrongPass123", test_salt)


# ============================================================================
# EXCEPTION TESTS
# ============================================================================


class TestExceptions:
    """Tests for custom exceptions"""

    def test_encryption_error_inheritance(self):
        """Test EncryptionError is base exception"""
        error = EncryptionError("test")
        assert isinstance(error, Exception)

    def test_key_derivation_error_inheritance(self):
        """Test KeyDerivationError inherits from EncryptionError"""
        error = KeyDerivationError("test")
        assert isinstance(error, EncryptionError)
        assert isinstance(error, Exception)

    def test_decryption_error_inheritance(self):
        """Test DecryptionError inherits from EncryptionError"""
        error = DecryptionError("test")
        assert isinstance(error, EncryptionError)
        assert isinstance(error, Exception)


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================


class TestInitialization:
    """Tests for EncryptionManager initialization"""

    def test_init_success_with_argon2(self):
        """Test successful initialization when argon2-cffi is available"""
        if ARGON2_AVAILABLE:
            manager = EncryptionManager()
            assert manager is not None

    @patch("app.utils.encryption.ARGON2_AVAILABLE", False)
    def test_init_fails_without_argon2(self):
        """Test initialization fails when argon2-cffi is not available"""
        with pytest.raises(ImportError, match="argon2-cffi is required"):
            EncryptionManager()


# ============================================================================
# CONSTANTS TESTS
# ============================================================================


class TestConstants:
    """Tests for encryption configuration constants"""

    def test_argon2_constants(self):
        """Test Argon2 configuration constants"""
        assert EncryptionManager.ARGON2_MEMORY_COST == 64 * 1024  # 64 MiB
        assert EncryptionManager.ARGON2_TIME_COST == 3
        assert EncryptionManager.ARGON2_PARALLELISM == 1
        assert EncryptionManager.ARGON2_HASH_LENGTH == 32
        assert EncryptionManager.ARGON2_SALT_LENGTH == 16

    def test_aes_constants(self):
        """Test AES configuration constants"""
        assert EncryptionManager.AES_KEY_LENGTH == 32  # 256 bits
        assert EncryptionManager.AES_NONCE_LENGTH == 12  # 96 bits
