"""
Unit tests for app.crud.master_key_crud module (ORM versions)

Tests for master key CRUD ORM functions - Core encryption management
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import master_key_crud
from app.models.orm import Project, ProjectEncryption, User


@pytest.fixture
def test_user(db_session: Session):
    """Create a test user"""
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"testuser_masterkey_{unique_id}",
        email=f"testuser_masterkey_{unique_id}@example.com",
        password_hash="hashed_password",
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_project(db_session: Session, test_user):
    """Create a test project without encryption"""
    project = Project(
        id=uuid.uuid4(),
        name="Test Project Master Key",
        description="Test project for master key testing",
        origin_db="postgres",
        destination_db="mysql",
        owner_id=test_user.id,
        status="active",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def test_passphrase():
    """Return a test passphrase"""
    return "SuperSecretPassphrase123!"


class TestCreateProjectEncryptionOrm:
    """Tests for create_project_encryption_orm()"""

    def test_create_encryption_config(self, db_session: Session, test_project, test_passphrase):
        """Test creating encryption configuration for a project"""
        result = master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        assert result is not None
        assert result["project_id"] == str(test_project.id)
        assert result["encryption_enabled"] is True
        assert result["master_key_hash"] is not None
        assert result["salt_verification"] is not None
        assert result["salt_key_derivation"] is not None
        assert "created_at" in result
        assert "updated_at" in result

    def test_create_duplicate_encryption_config(
        self, db_session: Session, test_project, test_passphrase
    ):
        """Test that creating duplicate encryption config raises IntegrityError"""
        # Create first config
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Try to create duplicate - should raise IntegrityError
        with pytest.raises(IntegrityError):
            master_key_crud.create_project_encryption_orm(
                db_session, str(test_project.id), test_passphrase
            )


class TestGetProjectEncryptionOrm:
    """Tests for get_project_encryption_orm()"""

    def test_get_existing_encryption_config(
        self, db_session: Session, test_project, test_passphrase
    ):
        """Test getting existing encryption configuration"""
        # Create config first
        created = master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Retrieve it
        result = master_key_crud.get_project_encryption_orm(db_session, str(test_project.id))

        assert result is not None
        assert result["project_id"] == str(test_project.id)
        assert result["encryption_enabled"] is True
        assert result["master_key_hash"] == created["master_key_hash"]
        assert result["salt_verification"] == created["salt_verification"]
        assert result["salt_key_derivation"] == created["salt_key_derivation"]

    def test_get_nonexistent_encryption_config(self, db_session: Session):
        """Test getting encryption config for project without one"""
        fake_project_id = str(uuid.uuid4())
        result = master_key_crud.get_project_encryption_orm(db_session, fake_project_id)

        assert result is None


class TestVerifyProjectPassphraseOrm:
    """Tests for verify_project_passphrase_orm()"""

    def test_verify_correct_passphrase(self, db_session: Session, test_project, test_passphrase):
        """Test verifying correct passphrase"""
        # Create config
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Verify correct passphrase
        result = master_key_crud.verify_project_passphrase_orm(
            db_session, str(test_project.id), test_passphrase
        )

        assert result is True

    def test_verify_incorrect_passphrase(self, db_session: Session, test_project, test_passphrase):
        """Test verifying incorrect passphrase"""
        # Create config
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Verify wrong passphrase
        result = master_key_crud.verify_project_passphrase_orm(
            db_session, str(test_project.id), "WrongPassphrase123"
        )

        assert result is False

    def test_verify_passphrase_nonexistent_project(self, db_session: Session):
        """Test verifying passphrase for project without encryption"""
        fake_project_id = str(uuid.uuid4())
        result = master_key_crud.verify_project_passphrase_orm(
            db_session, fake_project_id, "AnyPassphrase"
        )

        assert result is False


class TestGetEncryptionSaltsOrm:
    """Tests for get_encryption_salts_orm()"""

    def test_get_salts_existing_project(self, db_session: Session, test_project, test_passphrase):
        """Test getting salts for existing encrypted project"""
        # Create config
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Get salts
        result = master_key_crud.get_encryption_salts_orm(db_session, str(test_project.id))

        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 2
        salt_verification, salt_key_derivation = result
        assert isinstance(salt_verification, bytes)
        assert isinstance(salt_key_derivation, bytes)
        assert len(salt_verification) > 0
        assert len(salt_key_derivation) > 0

    def test_get_salts_nonexistent_project(self, db_session: Session):
        """Test getting salts for project without encryption"""
        fake_project_id = str(uuid.uuid4())
        result = master_key_crud.get_encryption_salts_orm(db_session, fake_project_id)

        assert result is None


class TestDeriveEncryptionKeyForProjectOrm:
    """Tests for derive_encryption_key_for_project_orm()"""

    def test_derive_key_correct_passphrase(
        self, db_session: Session, test_project, test_passphrase
    ):
        """Test deriving encryption key with correct passphrase"""
        # Create config
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Derive key
        result = master_key_crud.derive_encryption_key_for_project_orm(
            db_session, str(test_project.id), test_passphrase
        )

        assert result is not None
        assert isinstance(result, bytes)
        assert len(result) == 32  # AES-256 key is 32 bytes

    def test_derive_key_incorrect_passphrase(
        self, db_session: Session, test_project, test_passphrase
    ):
        """Test deriving encryption key with incorrect passphrase"""
        # Create config
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Try to derive key with wrong passphrase
        result = master_key_crud.derive_encryption_key_for_project_orm(
            db_session, str(test_project.id), "WrongPassphrase"
        )

        assert result is None

    def test_derive_key_nonexistent_project(self, db_session: Session):
        """Test deriving key for project without encryption"""
        fake_project_id = str(uuid.uuid4())
        result = master_key_crud.derive_encryption_key_for_project_orm(
            db_session, fake_project_id, "AnyPassphrase"
        )

        assert result is None


class TestUpdateProjectEncryptionEnabledOrm:
    """Tests for update_project_encryption_enabled_orm()"""

    def test_disable_encryption(self, db_session: Session, test_project, test_passphrase):
        """Test disabling encryption for a project"""
        # Create config (enabled by default)
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Disable encryption
        result = master_key_crud.update_project_encryption_enabled_orm(
            db_session, str(test_project.id), False
        )

        assert result is not None
        assert result["encryption_enabled"] is False

    def test_enable_encryption(self, db_session: Session, test_project, test_passphrase):
        """Test enabling encryption for a project"""
        # Create config
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Disable first
        master_key_crud.update_project_encryption_enabled_orm(
            db_session, str(test_project.id), False
        )

        # Enable again
        result = master_key_crud.update_project_encryption_enabled_orm(
            db_session, str(test_project.id), True
        )

        assert result is not None
        assert result["encryption_enabled"] is True


class TestDeleteProjectEncryptionOrm:
    """Tests for delete_project_encryption_orm()"""

    def test_delete_existing_encryption(self, db_session: Session, test_project, test_passphrase):
        """Test deleting existing encryption configuration"""
        # Create config
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Delete it
        result = master_key_crud.delete_project_encryption_orm(db_session, str(test_project.id))

        assert result is True

        # Verify it's gone
        config = master_key_crud.get_project_encryption_orm(db_session, str(test_project.id))
        assert config is None

    def test_delete_nonexistent_encryption(self, db_session: Session):
        """Test deleting encryption config that doesn't exist"""
        fake_project_id = str(uuid.uuid4())
        result = master_key_crud.delete_project_encryption_orm(db_session, fake_project_id)

        assert result is False


class TestRotateProjectMasterKeyOrm:
    """Tests for rotate_project_master_key_orm()"""

    def test_rotate_with_correct_old_passphrase(
        self, db_session: Session, test_project, test_passphrase
    ):
        """Test rotating master key with correct old passphrase"""
        # Create config
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Get original hash
        original_config = master_key_crud.get_project_encryption_orm(
            db_session, str(test_project.id)
        )
        original_hash = original_config["master_key_hash"]

        # Rotate key
        new_passphrase = "NewSuperSecretPassphrase456!"
        result = master_key_crud.rotate_project_master_key_orm(
            db_session, str(test_project.id), test_passphrase, new_passphrase
        )

        assert result is True

        # Verify new passphrase works
        verify_new = master_key_crud.verify_project_passphrase_orm(
            db_session, str(test_project.id), new_passphrase
        )
        assert verify_new is True

        # Verify old passphrase no longer works
        verify_old = master_key_crud.verify_project_passphrase_orm(
            db_session, str(test_project.id), test_passphrase
        )
        assert verify_old is False

        # Verify hash changed
        new_config = master_key_crud.get_project_encryption_orm(db_session, str(test_project.id))
        assert new_config["master_key_hash"] != original_hash

    def test_rotate_with_incorrect_old_passphrase(
        self, db_session: Session, test_project, test_passphrase
    ):
        """Test rotating master key with incorrect old passphrase"""
        # Create config
        master_key_crud.create_project_encryption_orm(
            db_session, str(test_project.id), test_passphrase
        )

        # Try to rotate with wrong old passphrase
        result = master_key_crud.rotate_project_master_key_orm(
            db_session, str(test_project.id), "WrongOldPassphrase", "NewPassphrase"
        )

        assert result is False

        # Verify original passphrase still works
        verify_original = master_key_crud.verify_project_passphrase_orm(
            db_session, str(test_project.id), test_passphrase
        )
        assert verify_original is True
