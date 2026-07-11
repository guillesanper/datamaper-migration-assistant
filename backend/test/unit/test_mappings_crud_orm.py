"""
Tests for mappings_crud ORM functions

Tests de funciones _orm de mappings_crud.py con:
- Modo import/connector híbrido
- Encriptación AES-256-GCM para import mode
- Hashing SHA-256 para connector mode
- Validaciones estrictas de encriptación
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud import mappings_crud, master_key_crud
from app.models.orm import Mapping, Project, ProjectEncryption, User


@pytest.fixture
def test_user(db_session: Session):
    """Create a test user for mapping tests"""
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"testuser_mapping_{unique_id}",
        email=f"testuser_mapping_{unique_id}@example.com",
        password_hash="hashed_password",
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_project(db_session: Session, test_user):
    """Create a test project for mapping tests"""
    project = Project(
        id=uuid.uuid4(),
        name="Test Project",
        owner_id=test_user.id,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


class TestCreateMappingOrm:
    """Tests for create_mapping_orm"""

    def test_create_unencrypted_mapping_import_mode(self, db_session, test_user):
        """Test creating an unencrypted mapping in import mode (legacy behavior)"""
        # Create a test project (without encryption)
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            name="Test Project",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)
        db_session.commit()

        # Create mapping
        result = mappings_crud.create_mapping_orm(
            db=db_session,
            project_id=project_id,
            origin_table="users",
            origin_column="id",
            destination_table="customers",
            destination_column="user_id",
            user_id=str(uuid.uuid4()),
            origin_source_type="import",
            destination_source_type="import",
        )

        # Verify result
        assert result is not None
        assert result["project_id"] == project_id
        assert result["origin_table"] == "users"
        assert result["origin_column"] == "id"
        assert result["destination_table"] == "customers"
        assert result["destination_column"] == "user_id"
        assert result["is_encrypted"] is False
        assert result["origin_source_type"] == "import"
        assert result["destination_source_type"] == "import"

        # Verify database persistence
        mapping = db_session.query(Mapping).filter(Mapping.id == result["id"]).first()
        assert mapping is not None
        assert mapping.origin_table == "users"
        assert mapping.destination_table == "customers"

    def test_create_encrypted_mapping_with_key(self, db_session, test_user):
        """Test creating an encrypted mapping with encryption key (import mode)"""
        # Create project with encryption enabled
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            name="Encrypted Project",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)

        # Create encryption config with fake salts
        salt_verification = "fake_salt_verification"
        salt_key_derivation = "fake_salt_key_derivation"

        encryption_config = ProjectEncryption(
            project_id=project_id,
            encryption_enabled=True,
            master_key_hash="fake_hash",  # For testing, we use a fake hash
            salt_verification=salt_verification,
            salt_key_derivation=salt_key_derivation,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(encryption_config)
        db_session.commit()

        # Use a fake encryption key (32 bytes for AES-256)
        encryption_key = b"0" * 32  # 32 bytes fake key

        # Create encrypted mapping
        result = mappings_crud.create_mapping_orm(
            db=db_session,
            project_id=project_id,
            origin_table="sensitive_users",
            origin_column="ssn",
            destination_table="masked_users",
            destination_column="user_ssn",
            user_id=str(uuid.uuid4()),
            encryption_key=encryption_key,
            origin_source_type="import",
            destination_source_type="import",
        )

        # Verify result
        assert result is not None
        assert result["is_encrypted"] is True
        # Should return plaintext for immediate use
        assert result["origin_table"] == "sensitive_users"
        assert result["origin_column"] == "ssn"
        assert result["destination_table"] == "masked_users"
        assert result["destination_column"] == "user_ssn"

        # Verify database has encrypted values
        mapping = db_session.query(Mapping).filter(Mapping.id == result["id"]).first()
        assert mapping.origin_table is None  # NULL when encrypted
        assert mapping.origin_column is None  # NULL when encrypted
        assert mapping.origin_table_encrypted is not None
        assert mapping.origin_table_nonce is not None
        assert mapping.origin_column_encrypted is not None
        assert mapping.origin_column_nonce is not None

        # Verify we can decrypt
        decrypted_origin_table = master_key_crud.decrypt_mapping_field(
            mapping.origin_table_encrypted, mapping.origin_table_nonce, encryption_key
        )
        assert decrypted_origin_table == "sensitive_users"

    def test_create_encrypted_mapping_without_key_fails(self, db_session, test_user):
        """Test creating mapping in encrypted project without key raises HTTP 403"""
        # Create project with encryption enabled
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            name="Encrypted Project",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)

        # Create encryption config with fake salts
        encryption_config = ProjectEncryption(
            project_id=project_id,
            encryption_enabled=True,
            master_key_hash="fake_hash",
            salt_verification="fake_salt_verification",
            salt_key_derivation="fake_salt_key_derivation",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(encryption_config)
        db_session.commit()

        # Try to create mapping WITHOUT encryption key - should fail with 403
        with pytest.raises(HTTPException) as exc_info:
            mappings_crud.create_mapping_orm(
                db=db_session,
                project_id=project_id,
                origin_table="users",
                origin_column="id",
                destination_table="customers",
                destination_column="user_id",
                user_id=str(uuid.uuid4()),
                encryption_key=None,  # NO KEY PROVIDED
                origin_source_type="import",
                destination_source_type="import",
            )

        assert exc_info.value.status_code == 403
        assert "encriptación" in exc_info.value.detail.lower()

    def test_create_connector_mode_mapping_with_hashes(self, db_session, test_user):
        """Test creating mapping in connector mode with SHA-256 hashes"""
        # Create project
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            name="Connector Project",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)
        db_session.commit()

        # Create mapping in connector mode
        origin_session_id = str(uuid.uuid4())
        destination_session_id = str(uuid.uuid4())

        result = mappings_crud.create_mapping_orm(
            db=db_session,
            project_id=project_id,
            origin_table="external_users",
            origin_column="user_id",
            destination_table="local_users",
            destination_column="external_id",
            user_id=str(uuid.uuid4()),
            origin_source_type="connector",
            destination_source_type="connector",
            origin_session_id=origin_session_id,
            destination_session_id=destination_session_id,
        )

        # Verify result
        assert result is not None
        assert result["origin_source_type"] == "connector"
        assert result["destination_source_type"] == "connector"
        assert result["origin_session_id"] == origin_session_id
        assert result["destination_session_id"] == destination_session_id

        # Verify hashes are created
        import hashlib

        expected_origin_table_hash = hashlib.sha256("external_users".encode()).hexdigest()
        expected_origin_column_hash = hashlib.sha256("user_id".encode()).hexdigest()

        assert result["origin_table_hash"] == expected_origin_table_hash
        assert result["origin_column_hash"] == expected_origin_column_hash

        # Verify database persistence
        mapping = db_session.query(Mapping).filter(Mapping.id == result["id"]).first()
        assert mapping.origin_table_hash == expected_origin_table_hash
        assert mapping.origin_column_hash == expected_origin_column_hash


class TestGetMappingsByProjectOrm:
    """Tests for get_mappings_by_project_orm"""

    def test_get_mappings_with_encryption(self, db_session, test_user):
        """Test getting mappings with decryption"""
        # Create project with encryption
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            name="Encrypted Project",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)

        # Create encryption config with fake salts
        encryption_config = ProjectEncryption(
            project_id=project_id,
            encryption_enabled=True,
            master_key_hash="fake_hash",
            salt_verification="fake_salt_verification",
            salt_key_derivation="fake_salt_key_derivation",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(encryption_config)
        db_session.commit()

        # Use fake encryption key
        encryption_key = b"0" * 32

        # Create encrypted mappings
        mapping1 = mappings_crud.create_mapping_orm(
            db=db_session,
            project_id=project_id,
            origin_table="table1",
            origin_column="col1",
            destination_table="table2",
            destination_column="col2",
            user_id=str(uuid.uuid4()),
            encryption_key=encryption_key,
        )

        mapping2 = mappings_crud.create_mapping_orm(
            db=db_session,
            project_id=project_id,
            origin_table="table3",
            origin_column="col3",
            destination_table="table4",
            destination_column="col4",
            user_id=str(uuid.uuid4()),
            encryption_key=encryption_key,
        )

        # Get mappings with encryption key
        results = mappings_crud.get_mappings_by_project_orm(
            db=db_session, project_id=project_id, encryption_key=encryption_key
        )

        # Verify results
        assert len(results) == 2
        assert all(m["is_encrypted"] is True for m in results)

        # Verify decryption
        mapping1_result = next(m for m in results if m["id"] == str(mapping1["id"]))
        assert mapping1_result["origin_table"] == "table1"
        assert mapping1_result["origin_column"] == "col1"

    def test_get_mappings_without_encryption_key(self, db_session, test_user):
        """Test getting encrypted mappings without key returns encrypted data"""
        # Create project with encryption
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            name="Encrypted Project",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)

        # Create encryption config with fake salts
        encryption_config = ProjectEncryption(
            project_id=project_id,
            encryption_enabled=True,
            master_key_hash="fake_hash",
            salt_verification="fake_salt_verification",
            salt_key_derivation="fake_salt_key_derivation",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(encryption_config)
        db_session.commit()

        # Use fake encryption key
        encryption_key = b"0" * 32

        # Create encrypted mapping
        mappings_crud.create_mapping_orm(
            db=db_session,
            project_id=project_id,
            origin_table="secret_table",
            origin_column="secret_col",
            destination_table="public_table",
            destination_column="public_col",
            user_id=str(uuid.uuid4()),
            encryption_key=encryption_key,
        )

        # Get mappings WITHOUT encryption key
        results = mappings_crud.get_mappings_by_project_orm(
            db=db_session, project_id=project_id, encryption_key=None  # NO KEY
        )

        # Verify encrypted fields are NULL
        assert len(results) == 1
        assert results[0]["is_encrypted"] is True
        assert results[0]["origin_table"] is None
        assert results[0]["origin_column"] is None


class TestUpdateMappingOrm:
    """Tests for update_mapping_orm"""

    def test_update_encrypted_mapping(self, db_session, test_user):
        """Test updating an encrypted mapping"""
        # Create project with encryption
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            name="Encrypted Project",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)

        # Create encryption config with fake salts
        encryption_config = ProjectEncryption(
            project_id=project_id,
            encryption_enabled=True,
            master_key_hash="fake_hash",
            salt_verification="fake_salt_verification",
            salt_key_derivation="fake_salt_key_derivation",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(encryption_config)
        db_session.commit()

        # Use fake encryption key
        encryption_key = b"0" * 32

        # Create mapping
        mapping = mappings_crud.create_mapping_orm(
            db=db_session,
            project_id=project_id,
            origin_table="old_table",
            origin_column="old_col",
            destination_table="dest_table",
            destination_column="dest_col",
            user_id=str(uuid.uuid4()),
            encryption_key=encryption_key,
        )

        # Update mapping
        updated = mappings_crud.update_mapping_orm(
            db=db_session,
            mapping_id=str(mapping["id"]),
            origin_table="new_table",
            origin_column="new_col",
            user_id=str(uuid.uuid4()),
            encryption_key=encryption_key,
        )

        # Verify update
        assert updated["origin_table"] == "new_table"
        assert updated["origin_column"] == "new_col"
        assert updated["is_encrypted"] is True

        # Verify database persistence
        db_mapping = db_session.query(Mapping).filter(Mapping.id == mapping["id"]).first()
        assert db_mapping.origin_table is None  # NULL when encrypted
        decrypted = master_key_crud.decrypt_mapping_field(
            db_mapping.origin_table_encrypted, db_mapping.origin_table_nonce, encryption_key
        )
        assert decrypted == "new_table"


class TestDeleteMappingOrm:
    """Tests for delete_mapping_orm"""

    def test_delete_mapping(self, db_session, test_user):
        """Test deleting a mapping"""
        # Create project
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            name="Delete Test Project",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)
        db_session.commit()

        # Create mapping
        mapping = mappings_crud.create_mapping_orm(
            db=db_session,
            project_id=project_id,
            origin_table="users",
            origin_column="id",
            destination_table="customers",
            destination_column="user_id",
            user_id=str(uuid.uuid4()),
        )

        # Delete mapping
        deleted = mappings_crud.delete_mapping_orm(
            db=db_session, mapping_id=str(mapping["id"]), user_id=str(uuid.uuid4())
        )

        # Verify deletion
        assert deleted is not None
        assert deleted["id"] == str(mapping["id"])

        # Verify no longer in database
        db_mapping = db_session.query(Mapping).filter(Mapping.id == mapping["id"]).first()
        assert db_mapping is None

    def test_delete_nonexistent_mapping(self, db_session):
        """Test deleting non-existent mapping returns None"""
        result = mappings_crud.delete_mapping_orm(
            db=db_session, mapping_id=str(uuid.uuid4()), user_id=str(uuid.uuid4())
        )

        assert result is None


class TestGetMappingByIdOrm:
    """Tests for get_mapping_by_id_orm"""

    def test_get_mapping_by_id_with_decryption(self, db_session, test_user):
        """Test getting a mapping by ID with decryption"""
        # Create project with encryption
        project_id = str(uuid.uuid4())
        project = Project(
            id=project_id,
            name="Encrypted Project",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)

        # Create encryption config with fake salts
        encryption_config = ProjectEncryption(
            project_id=project_id,
            encryption_enabled=True,
            master_key_hash="fake_hash",
            salt_verification="fake_salt_verification",
            salt_key_derivation="fake_salt_key_derivation",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(encryption_config)
        db_session.commit()

        # Use fake encryption key
        encryption_key = b"0" * 32

        # Create encrypted mapping
        mapping = mappings_crud.create_mapping_orm(
            db=db_session,
            project_id=project_id,
            origin_table="secret_table",
            origin_column="secret_col",
            destination_table="public_table",
            destination_column="public_col",
            user_id=str(uuid.uuid4()),
            encryption_key=encryption_key,
        )

        # Get mapping by ID with encryption key
        result = mappings_crud.get_mapping_by_id_orm(
            db=db_session, mapping_id=str(mapping["id"]), encryption_key=encryption_key
        )

        # Verify result
        assert result is not None
        assert result["origin_table"] == "secret_table"
        assert result["origin_column"] == "secret_col"
        assert result["is_encrypted"] is True

    def test_get_nonexistent_mapping_by_id(self, db_session):
        """Test getting non-existent mapping returns None"""
        result = mappings_crud.get_mapping_by_id_orm(db=db_session, mapping_id=str(uuid.uuid4()))

        assert result is None


# ============================================================================
# DELETE ALL MAPPINGS TESTS
# ============================================================================


class TestDeleteAllMappingsOrm:
    """Tests for delete_all_mappings_orm"""

    def test_delete_all_success(self, db_session, test_project):
        """Test deleting all mappings from project"""
        from datetime import datetime, timezone

        from app.models.orm.mapping import Mapping

        # Create multiple mappings
        for i in range(3):
            mapping = Mapping(
                id=uuid.uuid4(),
                project_id=test_project.id,
                origin_table=f"table_{i}",
                origin_column=f"col_{i}",
                destination_table=f"dest_table_{i}",
                destination_column=f"dest_col_{i}",
                origin_source_type="import",
                destination_source_type="import",
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db_session.add(mapping)
        db_session.commit()

        # Delete all
        count = mappings_crud.delete_all_mappings_orm(db_session, str(test_project.id))

        assert count == 3

        # Verify none remain
        remaining = db_session.query(Mapping).filter(Mapping.project_id == test_project.id).count()
        assert remaining == 0

    def test_delete_returns_zero_when_empty(self, db_session, test_project):
        """Test deleting when no mappings exist"""
        count = mappings_crud.delete_all_mappings_orm(db_session, str(test_project.id))

        assert count == 0


# ============================================================================
# BULK CREATE MAPPINGS TESTS
# ============================================================================


class TestBulkCreateMappingsOrm:
    """Tests for bulk_create_mappings_orm"""

    def test_bulk_create_no_encryption(self, db_session, test_project):
        """Test creating multiple mappings without encryption"""
        from app.models.orm.mapping import Mapping

        mappings_data = [
            {
                "origin_table": "users",
                "origin_column": "id",
                "destination_table": "customers",
                "destination_column": "user_id",
                "origin_source_type": "import",
                "destination_source_type": "import",
            },
            {
                "origin_table": "orders",
                "origin_column": "customer_id",
                "destination_table": "sales",
                "destination_column": "cust_id",
                "origin_source_type": "import",
                "destination_source_type": "import",
            },
        ]

        results = mappings_crud.bulk_create_mappings_orm(
            db_session, project_id=str(test_project.id), mappings=mappings_data
        )

        assert len(results) == 2
        assert results[0]["origin_table"] == "users"
        assert results[1]["origin_table"] == "orders"

        # Verify in database
        db_mappings = db_session.query(Mapping).filter(Mapping.project_id == test_project.id).all()
        assert len(db_mappings) == 2

    def test_bulk_create_with_encryption(self, db_session, test_user):
        """Test creating multiple mappings with encryption"""
        from datetime import datetime, timezone

        from app.models.orm import ProjectEncryption
        from app.models.orm.mapping import Mapping

        # Create encrypted project
        project_id = uuid.uuid4()
        project = Project(
            id=project_id,
            name="Encrypted Bulk Project",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)

        # Create encryption config
        encryption_config = ProjectEncryption(
            project_id=project_id,
            encryption_enabled=True,
            master_key_hash="fake_hash",
            salt_verification="fake_salt_verification",
            salt_key_derivation="fake_salt_key_derivation",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(encryption_config)
        db_session.commit()

        # Use fake encryption key
        encryption_key = b"0" * 32

        mappings_data = [
            {
                "origin_table": "sensitive_users",
                "origin_column": "id",
                "destination_table": "public_users",
                "destination_column": "user_id",
                "origin_source_type": "import",
                "destination_source_type": "import",
            }
        ]

        results = mappings_crud.bulk_create_mappings_orm(
            db_session,
            project_id=str(project_id),
            mappings=mappings_data,
            encryption_key=encryption_key,
        )

        assert len(results) == 1
        # Response should have decrypted values
        assert results[0]["origin_table"] == "sensitive_users"

        # Database should have encrypted values
        db_mapping = db_session.query(Mapping).filter(Mapping.project_id == project_id).first()
        assert db_mapping.origin_table_encrypted is not None
        assert db_mapping.origin_table_nonce is not None
        assert db_mapping.origin_table is None  # Plaintext should be None

    def test_bulk_create_requires_encryption_key(self, db_session, test_user):
        """Test that encrypted project without key raises 403"""
        from datetime import datetime, timezone

        import pytest
        from fastapi import HTTPException

        from app.models.orm import ProjectEncryption

        # Create encrypted project
        project_id = uuid.uuid4()
        project = Project(
            id=project_id,
            name="Encrypted Bulk Project 2",
            owner_id=test_user.id,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(project)

        # Create encryption config
        encryption_config = ProjectEncryption(
            project_id=project_id,
            encryption_enabled=True,
            master_key_hash="fake_hash",
            salt_verification="fake_salt_verification",
            salt_key_derivation="fake_salt_key_derivation",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(encryption_config)
        db_session.commit()

        mappings_data = [
            {
                "origin_table": "test",
                "origin_column": "id",
                "destination_table": "dest",
                "destination_column": "id",
                "origin_source_type": "import",
                "destination_source_type": "import",
            }
        ]

        with pytest.raises(HTTPException) as exc_info:
            mappings_crud.bulk_create_mappings_orm(
                db_session,
                project_id=str(project_id),
                mappings=mappings_data,
                # No encryption_key provided
            )

        assert exc_info.value.status_code == 403
        assert "encriptación" in exc_info.value.detail.lower()
