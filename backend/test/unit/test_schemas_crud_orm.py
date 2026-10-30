"""
Unit tests for app.crud.schemas_crud module (ORM versions)

Tests for schemas CRUD ORM functions with encryption support
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud import schemas_crud
from app.models.orm import Project, ProjectEncryption, Table, TableColumn, User


@pytest.fixture
def test_user(db_session: Session):
    """Create a test user - returns dict to avoid detached instance errors"""
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"testuser_schema_{unique_id}",
        email=f"testuser_schema_{unique_id}@example.com",
        password_hash="hashed_password",
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    # Capturar valores antes de que el objeto expire
    user_id = str(user.id)
    username = user.username
    email = user.email
    return {"id": user_id, "username": username, "email": email}


@pytest.fixture
def test_project(db_session: Session, test_user):
    """Create a test project without encryption - returns dict"""
    project = Project(
        id=uuid.uuid4(),
        name="Test Project Schemas",
        description="Test project for schemas testing",
        origin_db="postgres",
        destination_db="mysql",
        owner_id=test_user["id"],
        status="active",
    )
    db_session.add(project)
    db_session.commit()
    # Capturar valores antes de que el objeto expire
    project_id = str(project.id)
    return {"id": project_id, "name": project.name, "owner_id": test_user["id"]}


@pytest.fixture
def test_project_with_encryption(db_session: Session, test_user):
    """Create a test project with encryption enabled - returns dict"""
    project = Project(
        id=uuid.uuid4(),
        name="Test Project Encrypted",
        description="Test project with encryption",
        origin_db="postgres",
        destination_db="mysql",
        owner_id=test_user["id"],
        status="active",
    )
    db_session.add(project)
    db_session.flush()

    # Capturar project_id antes de más operaciones
    project_id = str(project.id)

    # Enable encryption for the project
    encryption_config = ProjectEncryption(
        project_id=project.id,
        encryption_enabled=True,
        master_key_hash="fake_hash_for_testing",
        salt_verification="fake_salt_verification",
        salt_key_derivation="fake_salt_key_derivation",
    )
    db_session.add(encryption_config)
    db_session.commit()
    return {"id": project_id, "name": project.name, "owner_id": test_user["id"]}


@pytest.fixture
def encryption_key():
    """Return a mock encryption key (32 bytes for AES-256)"""
    return b"0" * 32  # Simple 32-byte key for testing


class TestCreateTableOrm:
    """Tests for create_table_orm()"""

    def test_create_unencrypted_table(self, db_session: Session, test_project, test_user):
        """Test creating a table without encryption"""
        result = schemas_crud.create_table_orm(
            db_session, test_project["id"], "users", "origin", test_user["id"], encryption_key=None
        )

        assert result is not None
        assert result["name"] == "users"
        assert result["is_encrypted"] == False
        assert result["type"] == "origin"
        assert "id" in result
        assert "project_id" in result

    def test_create_encrypted_table_with_key(
        self, db_session: Session, test_project_with_encryption, test_user, encryption_key
    ):
        """Test creating an encrypted table with valid key"""
        result = schemas_crud.create_table_orm(
            db_session,
            test_project_with_encryption["id"],
            "sensitive_data",
            "origin",
            test_user["id"],
            encryption_key=encryption_key,
        )

        assert result is not None
        assert result["name"] == "sensitive_data"  # Plaintext en respuesta
        assert result["is_encrypted"] == True
        assert result["name_encrypted"] is not None
        assert result["name_nonce"] is not None

    def test_create_encrypted_table_without_key_fails(
        self, db_session: Session, test_project_with_encryption, test_user
    ):
        """Test that creating encrypted table without key raises 403"""
        with pytest.raises(HTTPException) as exc_info:
            schemas_crud.create_table_orm(
                db_session,
                test_project_with_encryption["id"],
                "sensitive_data",
                "origin",
                test_user["id"],
                encryption_key=None,  # NO KEY
            )

        assert exc_info.value.status_code == 403

    def test_create_duplicate_table_fails(self, db_session: Session, test_project, test_user):
        """Test that creating duplicate table raises 409"""
        # Create first table
        schemas_crud.create_table_orm(
            db_session, test_project["id"], "users", "origin", test_user["id"]
        )

        # Try to create duplicate
        with pytest.raises(HTTPException) as exc_info:
            schemas_crud.create_table_orm(
                db_session, test_project["id"], "users", "origin", test_user["id"]
            )

        assert exc_info.value.status_code == 409


class TestGetTablesByProjectOrm:
    """Tests for get_tables_by_project_orm()"""

    def test_get_unencrypted_tables(self, db_session: Session, test_project, test_user):
        """Test getting tables without encryption"""
        # Create some tables
        schemas_crud.create_table_orm(
            db_session, test_project["id"], "users", "origin", test_user["id"]
        )
        schemas_crud.create_table_orm(
            db_session, test_project["id"], "posts", "origin", test_user["id"]
        )

        # Get tables
        results = schemas_crud.get_tables_by_project_orm(db_session, test_project["id"], "origin")

        assert len(results) == 2
        names = [t["name"] for t in results]
        assert "users" in names
        assert "posts" in names

    def test_get_encrypted_tables_with_key(
        self, db_session: Session, test_project_with_encryption, test_user, encryption_key
    ):
        """Test getting encrypted tables with decryption key"""
        # Create encrypted table
        schemas_crud.create_table_orm(
            db_session,
            test_project_with_encryption["id"],
            "sensitive_data",
            "origin",
            test_user["id"],
            encryption_key=encryption_key,
        )

        # Get tables with key
        results = schemas_crud.get_tables_by_project_orm(
            db_session, test_project_with_encryption["id"], "origin", encryption_key=encryption_key
        )

        assert len(results) == 1
        assert results[0]["name"] == "sensitive_data"
        assert results[0]["is_encrypted"] == True


class TestCreateColumnOrm:
    """Tests for create_column_orm()"""

    def test_create_unencrypted_column(self, db_session: Session, test_project, test_user):
        """Test creating a column without encryption"""
        # Create table first
        table = schemas_crud.create_table_orm(
            db_session, test_project["id"], "users", "origin", test_user["id"]
        )

        # Create column
        result = schemas_crud.create_column_orm(
            db_session,
            table["id"],
            "email",
            "VARCHAR",
            "origin",
            is_nullable=False,
            is_primary=False,
            is_autogenerated=False,
            user_id=test_user["id"],
            encryption_key=None,
        )

        assert result is not None
        assert result["name"] == "email"
        assert result["data_type"] == "VARCHAR"
        assert result["is_encrypted"] == False
        assert result["is_nullable"] == False

    def test_create_encrypted_column_with_key(
        self, db_session: Session, test_project_with_encryption, test_user, encryption_key
    ):
        """Test creating an encrypted column with valid key"""
        # Create encrypted table first
        table = schemas_crud.create_table_orm(
            db_session,
            test_project_with_encryption["id"],
            "sensitive_data",
            "origin",
            test_user["id"],
            encryption_key=encryption_key,
        )

        # Create encrypted column
        result = schemas_crud.create_column_orm(
            db_session,
            table["id"],
            "ssn",
            "VARCHAR",
            "origin",
            is_nullable=False,
            is_primary=False,
            is_autogenerated=False,
            user_id=test_user["id"],
            encryption_key=encryption_key,
        )

        assert result is not None
        assert result["name"] == "ssn"  # Plaintext en respuesta
        assert result["data_type"] == "VARCHAR"
        assert result["is_encrypted"] == True

    def test_create_encrypted_column_without_key_fails(
        self, db_session: Session, test_project_with_encryption, test_user, encryption_key
    ):
        """Test that creating encrypted column without key raises 403"""
        # Create encrypted table first
        table = schemas_crud.create_table_orm(
            db_session,
            test_project_with_encryption["id"],
            "sensitive_data",
            "origin",
            test_user["id"],
            encryption_key=encryption_key,
        )

        # Try to create column without key
        with pytest.raises(HTTPException) as exc_info:
            schemas_crud.create_column_orm(
                db_session,
                table["id"],
                "ssn",
                "VARCHAR",
                "origin",
                is_nullable=False,
                is_primary=False,
                is_autogenerated=False,
                user_id=test_user["id"],
                encryption_key=None,  # NO KEY
            )

        assert exc_info.value.status_code == 403


class TestUpdateTableOrm:
    """Tests for update_table_orm()"""

    def test_update_unencrypted_table(self, db_session: Session, test_project, test_user):
        """Test updating a table without encryption"""
        # Create table
        table = schemas_crud.create_table_orm(
            db_session, test_project["id"], "users", "origin", test_user["id"]
        )

        # Update table
        result = schemas_crud.update_table_orm(
            db_session, table["id"], "users_new", test_user["id"]
        )

        assert result is not None
        assert result["name"] == "users_new"


class TestDeleteTableOrm:
    """Tests for delete_table_orm()"""

    def test_delete_table(self, db_session: Session, test_project, test_user):
        """Test deleting a table"""
        # Create table with column
        table = schemas_crud.create_table_orm(
            db_session, test_project["id"], "users", "origin", test_user["id"]
        )

        column = schemas_crud.create_column_orm(
            db_session,
            table["id"],
            "email",
            "VARCHAR",
            "origin",
            is_nullable=False,
            is_primary=False,
            is_autogenerated=False,
            user_id=test_user["id"],
        )

        # Delete table
        table_info, column_names, mappings_deleted = schemas_crud.delete_table_orm(
            db_session, table["id"], test_user["id"]
        )

        assert table_info is not None
        assert table_info["name"] == "users"
        assert "email" in column_names


class TestGetColumnsByTableOrm:
    """Tests for get_columns_by_table_orm()"""

    def test_get_unencrypted_columns(self, db_session: Session, test_project, test_user):
        """Test getting columns without encryption"""
        # Create table
        table = schemas_crud.create_table_orm(
            db_session, test_project["id"], "users", "origin", test_user["id"]
        )

        # Create columns
        schemas_crud.create_column_orm(
            db_session,
            table["id"],
            "email",
            "VARCHAR",
            "origin",
            is_nullable=False,
            is_primary=False,
            is_autogenerated=False,
            user_id=test_user["id"],
        )
        schemas_crud.create_column_orm(
            db_session,
            table["id"],
            "name",
            "VARCHAR",
            "origin",
            is_nullable=False,
            is_primary=False,
            is_autogenerated=False,
            user_id=test_user["id"],
        )

        # Get columns
        results = schemas_crud.get_columns_by_table_orm(db_session, table["id"])

        assert len(results) == 2
        names = [c["name"] for c in results]
        assert "email" in names
        assert "name" in names


class TestCheckTableLimitsOrm:
    """Tests for check_table_limits_orm()"""

    def test_check_table_limits(self, db_session: Session, test_project, test_user):
        """Test checking table limits for free plan"""
        has_pro, current_count, max_allowed = schemas_crud.check_table_limits_orm(
            db_session, test_project["id"]
        )

        assert has_pro == False
        assert max_allowed == 20
        assert current_count >= 0


class TestCheckColumnLimitsOrm:
    """Tests for check_column_limits_orm()"""

    def test_check_column_limits(self, db_session: Session, test_project, test_user):
        """Test checking column limits for free plan"""
        # Create table
        table = schemas_crud.create_table_orm(
            db_session, test_project["id"], "users", "origin", test_user["id"]
        )

        has_pro, current_count, max_allowed = schemas_crud.check_column_limits_orm(
            db_session, table["id"]
        )

        assert has_pro == False
        assert max_allowed == 60
        assert current_count >= 0


class TestUpdateColumnOrm:
    """Tests for update_column_orm() return value completeness"""

    def test_update_column_returns_complete_old_data(
        self, db_session: Session, test_project, test_user
    ):
        """old_data must contain every field consumed by the router (regression for KeyError on is_nullable)"""
        table = schemas_crud.create_table_orm(
            db_session, test_project["id"], "orders", "origin", test_user["id"]
        )
        column = schemas_crud.create_column_orm(
            db_session,
            table["id"],
            name="order_ref",
            data_type="VARCHAR(100)",
            table_type="origin",
            is_nullable=True,
            is_primary=False,
            is_autogenerated=False,
            user_id=test_user["id"],
        )

        old_data, new_data, mappings_renamed = schemas_crud.update_column_orm(
            db_session,
            column["id"],
            name="order_reference",
            data_type="TEXT",
            table_type="origin",
            is_nullable=False,
            is_primary=False,
            is_autogenerated=False,
            user_id=test_user["id"],
        )

        # old_data must not be None and must contain all fields the router accesses
        assert old_data is not None
        required_fields = {
            "id",
            "table_id",
            "name",
            "data_type",
            "table_type",
            "is_encrypted",
            "is_nullable",
            "is_primary",
            "is_autogenerated",
            "created_at",
            "updated_at",
            "table_name",
            "project_id",
        }
        assert (
            required_fields <= old_data.keys()
        ), f"old_data is missing fields: {required_fields - old_data.keys()}"

        # old_data must reflect the pre-update state
        assert old_data["name"] == "order_ref"
        assert old_data["data_type"] == "VARCHAR(100)"

        # new_data must reflect the post-update state
        assert new_data is not None
        assert new_data["name"] == "order_reference"
        assert new_data["data_type"] == "TEXT"

    def test_update_column_old_data_preserves_pre_update_booleans(
        self, db_session: Session, test_project, test_user
    ):
        """old_data boolean flags must capture the state *before* the update, not after"""
        table = schemas_crud.create_table_orm(
            db_session, test_project["id"], "products", "origin", test_user["id"]
        )
        column = schemas_crud.create_column_orm(
            db_session,
            table["id"],
            name="sku",
            data_type="VARCHAR(50)",
            table_type="origin",
            is_nullable=True,
            is_primary=False,
            is_autogenerated=False,
            user_id=test_user["id"],
        )

        old_data, new_data, _ = schemas_crud.update_column_orm(
            db_session,
            column["id"],
            name="sku",
            data_type="VARCHAR(50)",
            table_type="origin",
            is_nullable=False,
            is_primary=True,
            is_autogenerated=False,
            user_id=test_user["id"],
        )

        assert old_data is not None
        assert old_data["is_nullable"] is True  # was True before the update
        assert old_data["is_primary"] is False  # was False before the update

        assert new_data is not None
        assert new_data["is_nullable"] is False  # updated to False
        assert new_data["is_primary"] is True  # updated to True
