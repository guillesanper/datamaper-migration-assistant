"""
Encryption Manager para DataMap
Sistema de cifrado enterprise con AES-256-GCM + Argon2id

Características:
- Master key derivada con Argon2id (one-way hash)
- Cifrado de datos con AES-256-GCM (AEAD)
- Nonces únicos por operación
- Configuración OWASP 2025 compliant

Autor: DataMap Security Team
Fecha: 2025
"""

import base64
import os
import secrets
from typing import Optional, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Import Argon2 - fallback si no está instalado
try:
    from argon2 import PasswordHasher, low_level
    from argon2.low_level import Type

    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False
    print("WARNING: argon2-cffi not installed. Install with: pip install argon2-cffi")


class EncryptionError(Exception):
    """Base exception for encryption-related errors"""

    pass


class KeyDerivationError(EncryptionError):
    """Error during key derivation"""

    pass


class DecryptionError(EncryptionError):
    """Error during decryption (wrong key, corrupted data, etc.)"""

    pass


class EncryptionManager:
    """
    Gestor centralizado de cifrado para DataMap

    Implementa:
    - Derivación de master key hash (Argon2id) - one-way
    - Derivación de encryption key (Argon2id) - para AES
    - Cifrado/Descifrado con AES-256-GCM
    - Generación segura de salts y nonces

    Configuración por defecto (OWASP 2025):
    - Argon2id: 64 MiB memory, 3 iterations, 1 parallelism
    - AES-256-GCM: 256-bit key, 96-bit nonce, 128-bit tag
    """

    # Configuración Argon2id (OWASP 2025 recommendations)
    ARGON2_MEMORY_COST = 64 * 1024  # 64 MiB en KB
    ARGON2_TIME_COST = 3  # Iterations
    ARGON2_PARALLELISM = 1  # Degree of parallelism
    ARGON2_HASH_LENGTH = 32  # 256 bits output
    ARGON2_SALT_LENGTH = 16  # 128 bits

    # Configuración AES-GCM
    AES_KEY_LENGTH = 32  # 256 bits for AES-256
    AES_NONCE_LENGTH = 12  # 96 bits (recommended for GCM)

    def __init__(self):
        """Initialize the encryption manager"""
        if not ARGON2_AVAILABLE:
            raise ImportError(
                "argon2-cffi is required for encryption. " "Install with: pip install argon2-cffi"
            )

    @staticmethod
    def generate_salt(length: Optional[int] = None) -> bytes:
        """
        Generate a cryptographically secure random salt

        Args:
            length: Length in bytes (default: ARGON2_SALT_LENGTH)

        Returns:
            Random bytes suitable for use as salt
        """
        if length is None:
            length = EncryptionManager.ARGON2_SALT_LENGTH
        return secrets.token_bytes(length)

    @staticmethod
    def generate_nonce() -> bytes:
        """
        Generate a unique nonce for AES-GCM encryption

        CRITICAL: NEVER reuse a nonce with the same key!

        Returns:
            96-bit (12 byte) random nonce
        """
        return secrets.token_bytes(EncryptionManager.AES_NONCE_LENGTH)

    @staticmethod
    def derive_master_key_hash(
        passphrase: str,
        salt: bytes,
        memory_cost: Optional[int] = None,
        time_cost: Optional[int] = None,
        parallelism: Optional[int] = None,
    ) -> bytes:
        """
        Derive a one-way hash of the master key using Argon2id

        This hash is stored in the database and used ONLY for verification.
        It CANNOT be reversed to obtain the original passphrase.

        Args:
            passphrase: User's master passphrase
            salt: Unique salt for verification (16 bytes recommended)
            memory_cost: Memory usage in KB (default: 64 MiB)
            time_cost: Number of iterations (default: 3)
            parallelism: Degree of parallelism (default: 1)

        Returns:
            256-bit Argon2id hash

        Raises:
            KeyDerivationError: If key derivation fails
        """
        if not passphrase:
            raise KeyDerivationError("Passphrase cannot be empty")

        if not salt or len(salt) < 16:
            raise KeyDerivationError("Salt must be at least 16 bytes")

        # Use defaults if not specified
        memory_cost = memory_cost or EncryptionManager.ARGON2_MEMORY_COST
        time_cost = time_cost or EncryptionManager.ARGON2_TIME_COST
        parallelism = parallelism or EncryptionManager.ARGON2_PARALLELISM

        try:
            # Argon2id (hybrid mode - best of Argon2i and Argon2d)
            hash_bytes = low_level.hash_secret_raw(
                secret=passphrase.encode("utf-8"),
                salt=salt,
                time_cost=time_cost,
                memory_cost=memory_cost,
                parallelism=parallelism,
                hash_len=EncryptionManager.ARGON2_HASH_LENGTH,
                type=Type.ID,  # Argon2id
            )
            return hash_bytes
        except Exception as e:
            raise KeyDerivationError(f"Failed to derive master key hash: {str(e)}")

    @staticmethod
    def derive_encryption_key(
        passphrase: str,
        salt: bytes,
        memory_cost: Optional[int] = None,
        time_cost: Optional[int] = None,
        parallelism: Optional[int] = None,
    ) -> bytes:
        """
        Derive an AES-256 encryption key from passphrase using Argon2id

        This key is used for actual data encryption with AES-GCM.
        NEVER store this key - derive it on-demand from the passphrase.

        Args:
            passphrase: User's master passphrase
            salt: Unique salt for key derivation (16 bytes recommended)
            memory_cost: Memory usage in KB (default: 64 MiB)
            time_cost: Number of iterations (default: 3)
            parallelism: Degree of parallelism (default: 1)

        Returns:
            256-bit AES key

        Raises:
            KeyDerivationError: If key derivation fails
        """
        if not passphrase:
            raise KeyDerivationError("Passphrase cannot be empty")

        if not salt or len(salt) < 16:
            raise KeyDerivationError("Salt must be at least 16 bytes")

        # Use defaults if not specified
        memory_cost = memory_cost or EncryptionManager.ARGON2_MEMORY_COST
        time_cost = time_cost or EncryptionManager.ARGON2_TIME_COST
        parallelism = parallelism or EncryptionManager.ARGON2_PARALLELISM

        try:
            # Derive 256-bit key using Argon2id
            key_bytes = low_level.hash_secret_raw(
                secret=passphrase.encode("utf-8"),
                salt=salt,
                time_cost=time_cost,
                memory_cost=memory_cost,
                parallelism=parallelism,
                hash_len=EncryptionManager.AES_KEY_LENGTH,  # 32 bytes for AES-256
                type=Type.ID,  # Argon2id
            )
            return key_bytes
        except Exception as e:
            raise KeyDerivationError(f"Failed to derive encryption key: {str(e)}")

    @staticmethod
    def verify_master_key(passphrase: str, stored_hash: bytes, salt: bytes) -> bool:
        """
        Verify if a passphrase matches the stored master key hash

        Args:
            passphrase: Passphrase to verify
            stored_hash: Stored Argon2id hash from database
            salt: Salt used during original hash

        Returns:
            True if passphrase is correct, False otherwise
        """
        try:
            # Derive hash from provided passphrase
            computed_hash = EncryptionManager.derive_master_key_hash(passphrase, salt)

            # Constant-time comparison to prevent timing attacks
            return secrets.compare_digest(computed_hash, stored_hash)
        except Exception:
            return False

    @staticmethod
    def encrypt_field(
        plaintext: str, encryption_key: bytes, nonce: Optional[bytes] = None
    ) -> Tuple[bytes, bytes]:
        """
        Encrypt a field using AES-256-GCM

        AES-GCM provides:
        - Confidentiality (encryption)
        - Authenticity (authentication tag)
        - Integrity (tampering detection)

        Args:
            plaintext: String to encrypt
            encryption_key: 256-bit AES key (from derive_encryption_key)
            nonce: 96-bit nonce (auto-generated if not provided)

        Returns:
            Tuple of (ciphertext, nonce) - both as bytes
            The ciphertext includes the authentication tag

        Raises:
            EncryptionError: If encryption fails
        """
        if not plaintext:
            # Empty string is valid - encrypt it
            plaintext = ""

        if not encryption_key or len(encryption_key) != EncryptionManager.AES_KEY_LENGTH:
            raise EncryptionError(
                f"Encryption key must be {EncryptionManager.AES_KEY_LENGTH} bytes"
            )

        # Generate nonce if not provided
        if nonce is None:
            nonce = EncryptionManager.generate_nonce()
        elif len(nonce) != EncryptionManager.AES_NONCE_LENGTH:
            raise EncryptionError(f"Nonce must be {EncryptionManager.AES_NONCE_LENGTH} bytes")

        try:
            # Initialize AES-GCM cipher
            aesgcm = AESGCM(encryption_key)

            # Encrypt (includes authentication tag)
            ciphertext = aesgcm.encrypt(
                nonce=nonce,
                data=plaintext.encode("utf-8"),
                associated_data=None,  # Could add metadata here if needed
            )

            return ciphertext, nonce
        except Exception as e:
            raise EncryptionError(f"Failed to encrypt field: {str(e)}")

    @staticmethod
    def decrypt_field(ciphertext: bytes, nonce: bytes, encryption_key: bytes) -> str:
        """
        Decrypt a field using AES-256-GCM

        Args:
            ciphertext: Encrypted data (includes auth tag)
            nonce: Nonce used during encryption
            encryption_key: 256-bit AES key

        Returns:
            Decrypted plaintext string

        Raises:
            DecryptionError: If decryption fails (wrong key, corrupted data, etc.)
        """
        if not ciphertext:
            raise DecryptionError("Ciphertext cannot be empty")

        if not nonce or len(nonce) != EncryptionManager.AES_NONCE_LENGTH:
            raise DecryptionError(f"Nonce must be {EncryptionManager.AES_NONCE_LENGTH} bytes")

        if not encryption_key or len(encryption_key) != EncryptionManager.AES_KEY_LENGTH:
            raise DecryptionError(
                f"Encryption key must be {EncryptionManager.AES_KEY_LENGTH} bytes"
            )

        try:
            # Initialize AES-GCM cipher
            aesgcm = AESGCM(encryption_key)

            # Decrypt and verify authentication tag
            plaintext_bytes = aesgcm.decrypt(nonce=nonce, data=ciphertext, associated_data=None)

            return plaintext_bytes.decode("utf-8")
        except InvalidTag:
            raise DecryptionError(
                "Decryption failed: invalid authentication tag. "
                "Data may have been tampered with or wrong key was used."
            )
        except Exception as e:
            raise DecryptionError(f"Failed to decrypt field: {str(e)}")

    @staticmethod
    def encode_for_storage(data: bytes) -> str:
        """
        Encode binary data to base64 for database storage

        Args:
            data: Binary data (ciphertext, nonce, salt, etc.)

        Returns:
            Base64-encoded string
        """
        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def decode_from_storage(encoded: str) -> bytes:
        """
        Decode base64-encoded data from database

        Args:
            encoded: Base64-encoded string

        Returns:
            Binary data

        Raises:
            DecryptionError: If decoding fails
        """
        try:
            return base64.b64decode(encoded.encode("ascii"))
        except Exception as e:
            raise DecryptionError(f"Failed to decode data: {str(e)}")


# Convenience functions for common operations


def encrypt_text(plaintext: str, passphrase: str, salt: bytes) -> Tuple[str, str]:
    """
    High-level function to encrypt text

    Args:
        plaintext: Text to encrypt
        passphrase: User's passphrase
        salt: Salt for key derivation

    Returns:
        Tuple of (base64_ciphertext, base64_nonce)
    """
    manager = EncryptionManager()

    # Derive encryption key
    encryption_key = manager.derive_encryption_key(passphrase, salt)

    # Encrypt
    ciphertext, nonce = manager.encrypt_field(plaintext, encryption_key)

    # Encode for storage
    encoded_ciphertext = manager.encode_for_storage(ciphertext)
    encoded_nonce = manager.encode_for_storage(nonce)

    return encoded_ciphertext, encoded_nonce


def decrypt_text(encoded_ciphertext: str, encoded_nonce: str, passphrase: str, salt: bytes) -> str:
    """
    High-level function to decrypt text

    Args:
        encoded_ciphertext: Base64-encoded ciphertext
        encoded_nonce: Base64-encoded nonce
        passphrase: User's passphrase
        salt: Salt for key derivation

    Returns:
        Decrypted plaintext
    """
    manager = EncryptionManager()

    # Decode from storage
    ciphertext = manager.decode_from_storage(encoded_ciphertext)
    nonce = manager.decode_from_storage(encoded_nonce)

    # Derive encryption key
    encryption_key = manager.derive_encryption_key(passphrase, salt)

    # Decrypt
    plaintext = manager.decrypt_field(ciphertext, nonce, encryption_key)

    return plaintext


# Example usage (for testing)
if __name__ == "__main__":
    # This code only runs if the file is executed directly
    print("=== EncryptionManager Test ===\n")

    if not ARGON2_AVAILABLE:
        print("ERROR: argon2-cffi not installed")
        print("Install with: pip install argon2-cffi")
        exit(1)

    manager = EncryptionManager()

    # Test 1: Generate salt
    print("1. Generating salt...")
    salt_verify = manager.generate_salt()
    salt_kdf = manager.generate_salt()
    print(f"   Salt verification: {manager.encode_for_storage(salt_verify)[:32]}...")
    print(f"   Salt KDF: {manager.encode_for_storage(salt_kdf)[:32]}...")

    # Test 2: Derive master key hash
    print("\n2. Deriving master key hash (one-way)...")
    passphrase = "MySecurePassphrase123!"
    master_hash = manager.derive_master_key_hash(passphrase, salt_verify)
    print(f"   Hash: {manager.encode_for_storage(master_hash)[:32]}...")

    # Test 3: Verify master key
    print("\n3. Verifying passphrase...")
    is_valid = manager.verify_master_key(passphrase, master_hash, salt_verify)
    print(f"   Correct passphrase: {is_valid}")
    is_invalid = manager.verify_master_key("WrongPassword", master_hash, salt_verify)
    print(f"   Wrong passphrase: {is_invalid}")

    # Test 4: Derive encryption key
    print("\n4. Deriving encryption key...")
    enc_key = manager.derive_encryption_key(passphrase, salt_kdf)
    print(f"   Key: {manager.encode_for_storage(enc_key)[:32]}...")

    # Test 5: Encrypt data
    print("\n5. Encrypting sensitive data...")
    plaintext = "Sensitive table name: users_financial_data"
    ciphertext, nonce = manager.encrypt_field(plaintext, enc_key)
    print(f"   Plaintext: {plaintext}")
    print(f"   Ciphertext: {manager.encode_for_storage(ciphertext)[:40]}...")
    print(f"   Nonce: {manager.encode_for_storage(nonce)}")

    # Test 6: Decrypt data
    print("\n6. Decrypting data...")
    decrypted = manager.decrypt_field(ciphertext, nonce, enc_key)
    print(f"   Decrypted: {decrypted}")
    print(f"   Match: {decrypted == plaintext}")

    # Test 7: Tampering detection
    print("\n7. Testing tampering detection...")
    try:
        # Modify ciphertext (simulate tampering)
        tampered = bytearray(ciphertext)
        tampered[0] ^= 1  # Flip one bit
        manager.decrypt_field(bytes(tampered), nonce, enc_key)
        print("   ERROR: Tampering not detected!")
    except DecryptionError as e:
        print(f"   SUCCESS: Tampering detected - {str(e)[:50]}...")

    print("\n=== All tests completed ===")
