"""
Unit tests for app.services.encryption_service module

Tests for EncryptionService:
- Setup project encryption
- Passphrase verification
- Encryption key derivation
- Master key rotation
- Encryption enable/disable
- Existing data encryption
- Passphrase strength validation
- User permission verification
"""

from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import HTTPException, status

from app.services.encryption_service import EncryptionService

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db():
    """Provide a mock SQLAlchemy session"""
    db = MagicMock()
    db.query = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


@pytest.fixture
def test_project_id():
    """Provide a test project ID"""
    return "proj_12345"


@pytest.fixture
def test_user_id():
    """Provide a test user ID"""
    return "user_12345"


@pytest.fixture
def strong_passphrase():
    """Provide a strong passphrase"""
    return "MyVerySecurePass123!"


@pytest.fixture
def weak_passphrase_short():
    """Provide a weak passphrase (too short)"""
    return "Short1!"


@pytest.fixture
def weak_passphrase_no_upper():
    """Provide a weak passphrase (no uppercase)"""
    return "lowercasepass123!"


@pytest.fixture
def weak_passphrase_no_digit():
    """Provide a weak passphrase (no digit)"""
    return "NoDigitsHere!"


@pytest.fixture
def mock_encryption_config():
    """Provide a mock encryption configuration"""
    return {
        "project_id": "proj_12345",
        "encryption_enabled": True,
        "created_at": "2025-01-01T00:00:00",
        "master_key_hash": "base64_hash",
        "master_key_salt": "base64_salt",
        "kdf_salt": "base64_kdf_salt",
    }


@pytest.fixture
def mock_encryption_key():
    """Provide a mock 256-bit encryption key"""
    import secrets

    return secrets.token_bytes(32)


# ============================================================================
# PASSPHRASE STRENGTH VALIDATION TESTS
# ============================================================================


class TestPassphraseStrengthValidation:
    """Tests for _validate_passphrase_strength()"""

    def test_strong_passphrase_valid(self, strong_passphrase):
        """Test that strong passphrase passes validation"""
        # Should not raise
        EncryptionService._validate_passphrase_strength(strong_passphrase)

    def test_passphrase_too_short(self, weak_passphrase_short):
        """Test that short passphrase raises error"""
        with pytest.raises(HTTPException) as exc_info:
            EncryptionService._validate_passphrase_strength(weak_passphrase_short)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "al menos 12 caracteres" in exc_info.value.detail

    def test_passphrase_no_uppercase(self, weak_passphrase_no_upper):
        """Test that passphrase without uppercase raises error"""
        with pytest.raises(HTTPException) as exc_info:
            EncryptionService._validate_passphrase_strength(weak_passphrase_no_upper)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "mayúsculas y minúsculas" in exc_info.value.detail

    def test_passphrase_no_digit(self, weak_passphrase_no_digit):
        """Test that passphrase without digit raises error"""
        with pytest.raises(HTTPException) as exc_info:
            EncryptionService._validate_passphrase_strength(weak_passphrase_no_digit)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "al menos un número" in exc_info.value.detail

    def test_passphrase_long_without_special_chars_valid(self):
        """Test that long passphrase without special chars is valid (diceware style)"""
        passphrase = "CorrectHorseBatteryStaple123"  # No special chars but long
        # Should not raise
        EncryptionService._validate_passphrase_strength(passphrase)


# ============================================================================
# USER PERMISSION VERIFICATION TESTS
# ============================================================================


class TestUserPermissionVerification:
    """Tests for _verify_user_can_modify_encryption() - SQLAlchemy ORM"""

    def test_owner_has_permission(self, mock_db, test_project_id, test_user_id):
        """Test that project owner has permission"""
        # Create mock project
        mock_project = MagicMock()
        mock_project.owner_id = test_user_id

        mock_db.query.return_value.filter.return_value.first.return_value = mock_project

        # Should not raise
        EncryptionService._verify_user_can_modify_encryption(mock_db, test_project_id, test_user_id)

    def test_editor_has_permission(self, mock_db, test_project_id):
        """Test that editor has permission"""
        from app.models.orm.project import MemberRole

        user_id = "user_editor"
        owner_id = "user_owner"

        # Create mock project and member
        mock_project = MagicMock()
        mock_project.owner_id = owner_id

        mock_member = MagicMock()
        mock_member.role = MemberRole.EDITOR

        # First query returns project, second returns member
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_project,
            mock_member,
        ]

        # Should not raise
        EncryptionService._verify_user_can_modify_encryption(mock_db, test_project_id, user_id)

    def test_viewer_no_permission(self, mock_db, test_project_id):
        """Test that viewer does not have permission"""
        from app.models.orm.project import MemberRole

        user_id = "user_viewer"
        owner_id = "user_owner"

        # Create mock project and member
        mock_project = MagicMock()
        mock_project.owner_id = owner_id

        mock_member = MagicMock()
        mock_member.role = MemberRole.VIEWER  # Viewer, not editor

        # First query returns project, second returns member
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_project,
            mock_member,
        ]

        with pytest.raises(HTTPException) as exc_info:
            EncryptionService._verify_user_can_modify_encryption(mock_db, test_project_id, user_id)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "No tienes permisos" in exc_info.value.detail

    def test_project_not_found(self, mock_db, test_user_id):
        """Test error when project not found"""
        # Mock project not found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            EncryptionService._verify_user_can_modify_encryption(
                mock_db, "nonexistent_project", test_user_id
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "no encontrado" in exc_info.value.detail


# ============================================================================
# SETUP PROJECT ENCRYPTION TESTS
# ============================================================================


class TestSetupProjectEncryption:
    """Tests for setup_project_encryption()"""

    @patch("app.services.encryption_service.master_key_crud")
    @patch("app.services.encryption_service.EncryptionService._verify_user_can_modify_encryption")
    @patch("app.services.encryption_service.EncryptionService.encrypt_existing_project_data")
    def test_setup_encryption_success(
        self,
        mock_encrypt_data,
        mock_verify_perms,
        mock_master_key_crud,
        mock_db,
        test_project_id,
        test_user_id,
        strong_passphrase,
        mock_encryption_key,
    ):
        """Test successful encryption setup"""
        # Mock no existing encryption
        mock_master_key_crud.get_project_encryption_orm.return_value = None

        # Mock encryption config creation
        mock_master_key_crud.create_project_encryption_orm.return_value = {
            "created_at": "2025-01-01T00:00:00"
        }

        # Mock encryption key derivation
        mock_master_key_crud.derive_encryption_key_for_project_orm.return_value = (
            mock_encryption_key
        )

        # Mock data encryption stats
        mock_encrypt_data.return_value = {
            "tables_encrypted": 5,
            "columns_encrypted": 20,
            "total_encrypted": 25,
        }

        result = EncryptionService.setup_project_encryption(
            mock_db, test_project_id, strong_passphrase, test_user_id
        )

        assert result["status"] == "success"
        assert result["encryption_enabled"] is True
        assert result["project_id"] == test_project_id
        assert "encrypted_data" in result

        # Verify calls
        mock_master_key_crud.get_project_encryption_orm.assert_called_once_with(
            mock_db, test_project_id
        )
        mock_verify_perms.assert_called_once()
        mock_master_key_crud.create_project_encryption_orm.assert_called_once()

    @patch("app.services.encryption_service.master_key_crud")
    def test_setup_encryption_already_exists(
        self,
        mock_master_key_crud,
        mock_db,
        test_project_id,
        test_user_id,
        strong_passphrase,
        mock_encryption_config,
    ):
        """Test setup fails when encryption already configured"""
        # Mock existing encryption
        mock_master_key_crud.get_project_encryption_orm.return_value = mock_encryption_config

        with pytest.raises(HTTPException) as exc_info:
            EncryptionService.setup_project_encryption(
                mock_db, test_project_id, strong_passphrase, test_user_id
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "ya tiene cifrado configurado" in exc_info.value.detail

    @patch("app.services.encryption_service.master_key_crud")
    def test_setup_encryption_weak_passphrase(
        self, mock_master_key_crud, mock_db, test_project_id, test_user_id, weak_passphrase_short
    ):
        """Test setup fails with weak passphrase"""
        # Mock no existing encryption
        mock_master_key_crud.get_project_encryption_orm.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            EncryptionService.setup_project_encryption(
                mock_db, test_project_id, weak_passphrase_short, test_user_id
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# VERIFY PASSPHRASE TESTS
# ============================================================================


class TestVerifyProjectPassphrase:
    """Tests for verify_project_passphrase()"""

    @patch("app.services.encryption_service.master_key_crud")
    def test_verify_passphrase_correct(
        self, mock_master_key_crud, mock_db, test_project_id, strong_passphrase
    ):
        """Test passphrase verification with correct passphrase"""
        mock_master_key_crud.verify_project_passphrase_orm.return_value = True

        result = EncryptionService.verify_project_passphrase(
            mock_db, test_project_id, strong_passphrase
        )

        assert result is True
        mock_master_key_crud.verify_project_passphrase_orm.assert_called_once_with(
            mock_db, test_project_id, strong_passphrase
        )

    @patch("app.services.encryption_service.master_key_crud")
    def test_verify_passphrase_incorrect(self, mock_master_key_crud, mock_db, test_project_id):
        """Test passphrase verification with incorrect passphrase"""
        mock_master_key_crud.verify_project_passphrase_orm.return_value = False

        result = EncryptionService.verify_project_passphrase(
            mock_db, test_project_id, "WrongPassword123"
        )

        assert result is False


# ============================================================================
# GET ENCRYPTION KEY TESTS
# ============================================================================


class TestGetEncryptionKey:
    """Tests for get_encryption_key()"""

    @patch("app.services.encryption_service.master_key_crud")
    def test_get_encryption_key_success(
        self,
        mock_master_key_crud,
        mock_db,
        test_project_id,
        strong_passphrase,
        mock_encryption_config,
        mock_encryption_key,
    ):
        """Test successful encryption key retrieval"""
        mock_master_key_crud.get_project_encryption_orm.return_value = mock_encryption_config
        mock_master_key_crud.derive_encryption_key_for_project_orm.return_value = (
            mock_encryption_key
        )

        result = EncryptionService.get_encryption_key(mock_db, test_project_id, strong_passphrase)

        assert result == mock_encryption_key

    @patch("app.services.encryption_service.master_key_crud")
    def test_get_encryption_key_no_config(
        self, mock_master_key_crud, mock_db, test_project_id, strong_passphrase
    ):
        """Test error when project has no encryption configured"""
        mock_master_key_crud.get_project_encryption_orm.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            EncryptionService.get_encryption_key(mock_db, test_project_id, strong_passphrase)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "no tiene cifrado configurado" in exc_info.value.detail

    @patch("app.services.encryption_service.master_key_crud")
    def test_get_encryption_key_disabled(
        self,
        mock_master_key_crud,
        mock_db,
        test_project_id,
        strong_passphrase,
        mock_encryption_config,
    ):
        """Test error when encryption is disabled"""
        disabled_config = mock_encryption_config.copy()
        disabled_config["encryption_enabled"] = False
        mock_master_key_crud.get_project_encryption_orm.return_value = disabled_config

        with pytest.raises(HTTPException) as exc_info:
            EncryptionService.get_encryption_key(mock_db, test_project_id, strong_passphrase)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "deshabilitado" in exc_info.value.detail

    @patch("app.services.encryption_service.master_key_crud")
    def test_get_encryption_key_wrong_passphrase(
        self, mock_master_key_crud, mock_db, test_project_id, mock_encryption_config
    ):
        """Test returns None when passphrase is wrong"""
        mock_master_key_crud.get_project_encryption_orm.return_value = mock_encryption_config
        mock_master_key_crud.derive_encryption_key_for_project_orm.return_value = None

        result = EncryptionService.get_encryption_key(mock_db, test_project_id, "WrongPassword123")

        assert result is None


# ============================================================================
# ROTATE MASTER KEY TESTS
# ============================================================================


class TestRotateMasterKey:
    """Tests for rotate_master_key()"""

    @patch("app.services.encryption_service.master_key_crud")
    @patch("app.services.encryption_service.EncryptionService._verify_user_can_modify_encryption")
    def test_rotate_master_key_success(
        self,
        mock_verify_perms,
        mock_master_key_crud,
        mock_db,
        test_project_id,
        test_user_id,
        strong_passphrase,
        mock_encryption_key,
    ):
        """Test successful master key rotation"""
        old_pass = strong_passphrase
        new_pass = "NewSecurePass456!"

        # Mock passphrase verification
        mock_master_key_crud.verify_project_passphrase_orm.return_value = True

        # Mock old encryption key
        mock_master_key_crud.derive_encryption_key_for_project_orm.return_value = (
            mock_encryption_key
        )

        # Mock rotation success
        mock_master_key_crud.rotate_project_master_key_orm.return_value = True

        result = EncryptionService.rotate_master_key(
            mock_db, test_project_id, old_pass, new_pass, test_user_id
        )

        assert result["status"] == "success"
        assert result["project_id"] == test_project_id
        assert "warning" in result

        mock_verify_perms.assert_called_once()
        mock_master_key_crud.verify_project_passphrase_orm.assert_called_once()
        mock_master_key_crud.rotate_project_master_key_orm.assert_called_once()

    @patch("app.services.encryption_service.master_key_crud")
    @patch("app.services.encryption_service.EncryptionService._verify_user_can_modify_encryption")
    def test_rotate_master_key_wrong_old_passphrase(
        self, mock_verify_perms, mock_master_key_crud, mock_db, test_project_id, test_user_id
    ):
        """Test rotation fails with wrong old passphrase"""
        mock_master_key_crud.verify_project_passphrase_orm.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            EncryptionService.rotate_master_key(
                mock_db, test_project_id, "WrongOldPass1!", "NewSecurePass456!", test_user_id
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "incorrecta" in exc_info.value.detail

    @patch("app.services.encryption_service.master_key_crud")
    @patch("app.services.encryption_service.EncryptionService._verify_user_can_modify_encryption")
    def test_rotate_master_key_same_passphrase(
        self,
        mock_verify_perms,
        mock_master_key_crud,
        mock_db,
        test_project_id,
        test_user_id,
        strong_passphrase,
    ):
        """Test rotation fails when new passphrase equals old"""
        mock_master_key_crud.verify_project_passphrase_orm.return_value = True

        with pytest.raises(HTTPException) as exc_info:
            EncryptionService.rotate_master_key(
                mock_db, test_project_id, strong_passphrase, strong_passphrase, test_user_id
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "debe ser diferente" in exc_info.value.detail


# ============================================================================
# ENABLE/DISABLE ENCRYPTION TESTS
# ============================================================================


class TestEnableDisableEncryption:
    """Tests for enable_encryption() and disable_encryption()"""

    @patch("app.services.encryption_service.master_key_crud")
    @patch("app.services.encryption_service.EncryptionService._verify_user_can_modify_encryption")
    def test_disable_encryption_success(
        self,
        mock_verify_perms,
        mock_master_key_crud,
        mock_db,
        test_project_id,
        test_user_id,
        strong_passphrase,
    ):
        """Test successful encryption disable"""
        mock_master_key_crud.verify_project_passphrase_orm.return_value = True
        mock_master_key_crud.update_project_encryption_enabled_orm.return_value = {
            "encryption_enabled": False
        }

        result = EncryptionService.disable_encryption(
            mock_db, test_project_id, test_user_id, strong_passphrase
        )

        assert result["status"] == "success"
        assert result["encryption_enabled"] is False

    @patch("app.services.encryption_service.master_key_crud")
    @patch("app.services.encryption_service.EncryptionService._verify_user_can_modify_encryption")
    def test_disable_encryption_wrong_passphrase(
        self, mock_verify_perms, mock_master_key_crud, mock_db, test_project_id, test_user_id
    ):
        """Test disable fails with wrong passphrase"""
        mock_master_key_crud.verify_project_passphrase_orm.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            EncryptionService.disable_encryption(
                mock_db, test_project_id, test_user_id, "WrongPass123"
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("app.services.encryption_service.master_key_crud")
    @patch("app.services.encryption_service.EncryptionService._verify_user_can_modify_encryption")
    @patch("app.services.encryption_service.EncryptionService.encrypt_existing_project_data")
    def test_enable_encryption_success(
        self,
        mock_encrypt_data,
        mock_verify_perms,
        mock_master_key_crud,
        mock_db,
        test_project_id,
        test_user_id,
        strong_passphrase,
        mock_encryption_key,
    ):
        """Test successful encryption enable"""
        mock_master_key_crud.verify_project_passphrase_orm.return_value = True
        mock_master_key_crud.derive_encryption_key_for_project_orm.return_value = (
            mock_encryption_key
        )
        mock_master_key_crud.update_project_encryption_enabled_orm.return_value = {
            "encryption_enabled": True
        }
        mock_encrypt_data.return_value = {
            "tables_encrypted": 3,
            "columns_encrypted": 10,
            "total_encrypted": 13,
        }

        result = EncryptionService.enable_encryption(
            mock_db, test_project_id, test_user_id, strong_passphrase
        )

        assert result["status"] == "success"
        assert result["encryption_enabled"] is True
        assert "encrypted_data" in result


# ============================================================================
# ENCRYPT EXISTING DATA TESTS
# ============================================================================


class TestEncryptExistingProjectData:
    """Tests for encrypt_existing_project_data() - SQLAlchemy ORM"""

    @patch("app.services.encryption_service.master_key_crud")
    def test_encrypt_existing_data_success(
        self, mock_master_key_crud, mock_db, test_project_id, mock_encryption_key
    ):
        """Test successful encryption of existing data"""
        # Create mock table
        mock_table = MagicMock()
        mock_table.name = "users"
        mock_table.is_encrypted = False

        # Create mock column
        mock_column = MagicMock()
        mock_column.name = "email"
        mock_column.data_type = "VARCHAR"
        mock_column.is_encrypted = False

        # Create mock mapping
        mock_mapping = MagicMock()
        mock_mapping.origin_table = "t1"
        mock_mapping.origin_column = "c1"
        mock_mapping.destination_table = "t2"
        mock_mapping.destination_column = "c2"
        mock_mapping.is_encrypted = False

        # Setup mock query chains to return our mock objects
        mock_db.query.return_value.filter.return_value.all.side_effect = [
            [mock_table],  # Tables query
            [mock_column],  # Columns query
            [mock_mapping],  # Mappings query
        ]
        mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = [
            mock_column
        ]

        # Mock encryption functions
        mock_master_key_crud.encrypt_table_name.return_value = ("encrypted", "nonce")
        mock_master_key_crud.encrypt_column_name.return_value = ("encrypted", "nonce")
        mock_master_key_crud.encrypt_column_type.return_value = ("encrypted", "nonce")
        mock_master_key_crud.encrypt_mapping_field.return_value = ("encrypted", "nonce")

        result = EncryptionService.encrypt_existing_project_data(
            mock_db, test_project_id, mock_encryption_key
        )

        assert result["tables_encrypted"] == 1
        assert result["columns_encrypted"] == 1
        assert result["mappings_encrypted"] == 1
        assert result["total_encrypted"] == 3

        mock_db.commit.assert_called_once()

    def test_encrypt_existing_data_rollback_on_error(
        self, mock_db, test_project_id, mock_encryption_key
    ):
        """Test rollback on encryption error"""
        # Mock database error on first query
        mock_db.query.return_value.filter.return_value.all.side_effect = Exception("Database error")

        with pytest.raises(HTTPException):
            EncryptionService.encrypt_existing_project_data(
                mock_db, test_project_id, mock_encryption_key
            )

        mock_db.rollback.assert_called_once()


# ============================================================================
# GET ENCRYPTION STATS TESTS
# ============================================================================


class TestGetEncryptionStats:
    """Tests for get_encryption_stats() - SQLAlchemy"""

    def test_get_encryption_stats_success(self, mock_db, test_project_id):
        """Test successful retrieval of encryption stats"""
        # La implementación usa db.query().filter().scalar() (ORM),
        # se llama scalar() 10 veces (tables, columns, mappings, versions, comments × 2)
        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.scalar.side_effect = [10, 5, 50, 25, 0, 0, 0, 0, 0, 0]
        mock_db.query.return_value = mock_chain

        result = EncryptionService.get_encryption_stats(mock_db, test_project_id)

        assert result["tables_total"] == 10
        assert result["tables_encrypted"] == 5
        assert result["columns_total"] == 50
        assert result["columns_encrypted"] == 25

    def test_get_encryption_stats_no_data(self, mock_db, test_project_id):
        """Test stats when no data exists — retorna dict con ceros"""
        # La implementación usa db.query().filter().scalar() (ORM),
        # devuelve 0 cuando no hay datos (nunca un dict vacío)
        mock_chain = MagicMock()
        mock_chain.filter.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.scalar.return_value = 0
        mock_db.query.return_value = mock_chain

        result = EncryptionService.get_encryption_stats(mock_db, test_project_id)

        assert result["tables_total"] == 0
        assert result["tables_encrypted"] == 0
        assert result["encryption_percentage"] == 0.0
