"""
Unit tests for app.crud.pk_crud module (ORM versions)

Tests for PrimaryKeyCRUD ORM functions:
- Get PK constraint by table ID
- Get legacy PK columns
- Get columns by IDs
- Get table by ID
- Get columns for validation
- Create PK constraint
- Update PK constraint
- Update columns primary flag
- Delete PK constraint
- Clear all primary flags
- Insert audit log
- Get origin tables with PKs
- Count column mappings
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.crud.pk_crud import PrimaryKeyCRUD
from app.models.orm import (
    Mapping,
    MigrationAuditLog,
    PrimaryKeyConstraint,
    Project,
    Table,
    TableColumn,
    User,
)

# ============================================================================
# FIXTURES
# ============================================================================
# Nota: db_session fixture está definido en conftest.py


@pytest.fixture
def test_user(db_session: Session):
    """Create a test user"""
    # Usar UUID único para evitar colisiones en tests paralelos
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"testuser_pk_{unique_id}",
        email=f"testuser_pk_{unique_id}@example.com",
        password_hash="hashed_password",
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_project(db_session: Session, test_user):
    """Create a test project"""
    project = Project(
        id=uuid.uuid4(),
        name="Test Project PK",
        description="Test project for PK testing",
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
def test_table(db_session: Session, test_project):
    """Create a test table"""
    table = Table(
        id=uuid.uuid4(), project_id=test_project.id, name="users", type="origin", is_encrypted=False
    )
    db_session.add(table)
    db_session.commit()
    db_session.refresh(table)
    return table


@pytest.fixture
def test_columns(db_session: Session, test_table):
    """Create test columns"""
    columns = []

    # Column 1 - Primary key
    col1 = TableColumn(
        id=uuid.uuid4(),
        table_id=test_table.id,
        name="user_id",
        data_type="integer",
        is_nullable=False,
        is_primary=True,
        table_type="origin",
    )
    columns.append(col1)

    # Column 2 - Regular column
    col2 = TableColumn(
        id=uuid.uuid4(),
        table_id=test_table.id,
        name="username",
        data_type="varchar",
        is_nullable=False,
        is_primary=False,
        table_type="origin",
    )
    columns.append(col2)

    # Column 3 - Another column
    col3 = TableColumn(
        id=uuid.uuid4(),
        table_id=test_table.id,
        name="email",
        data_type="varchar",
        is_nullable=True,
        is_primary=False,
        table_type="origin",
    )
    columns.append(col3)

    for col in columns:
        db_session.add(col)

    db_session.commit()

    for col in columns:
        db_session.refresh(col)

    return columns


# ============================================================================
# GET PK CONSTRAINT BY TABLE ID TESTS
# ============================================================================


class TestGetPkConstraintByTableIdOrm:
    """Tests for get_pk_constraint_by_table_id_orm()"""

    def test_get_pk_constraint_exists(self, db_session: Session, test_table, test_columns):
        """Test getting existing PK constraint"""
        # Arrange
        pk_constraint = PrimaryKeyConstraint(
            table_id=test_table.id, column_ids=[str(test_columns[0].id)], constraint_name="pk_users"
        )
        db_session.add(pk_constraint)
        db_session.commit()

        # Act
        result = PrimaryKeyCRUD.get_pk_constraint_by_table_id_orm(
            db_session, table_id=str(test_table.id)
        )

        # Assert
        assert result is not None
        assert result["table_id"] == str(test_table.id)
        assert result["constraint_name"] == "pk_users"
        assert len(result["column_ids"]) == 1

    def test_get_pk_constraint_not_found(self, db_session: Session):
        """Test getting PK constraint when none exists"""
        # Arrange
        non_existent_id = str(uuid.uuid4())

        # Act
        result = PrimaryKeyCRUD.get_pk_constraint_by_table_id_orm(
            db_session, table_id=non_existent_id
        )

        # Assert
        assert result is None


# ============================================================================
# GET LEGACY PK COLUMNS TESTS
# ============================================================================


class TestGetLegacyPkColumnsOrm:
    """Tests for get_legacy_pk_columns_orm()"""

    def test_get_legacy_pk_columns_with_results(
        self, db_session: Session, test_table, test_columns
    ):
        """Test getting legacy PK columns"""
        # Act
        result = PrimaryKeyCRUD.get_legacy_pk_columns_orm(db_session, table_id=str(test_table.id))

        # Assert
        assert len(result) == 1
        assert result[0]["name"] == "user_id"

    def test_get_legacy_pk_columns_empty(self, db_session: Session, test_table):
        """Test getting legacy PK columns when none exist"""
        # Arrange - Set all columns to is_primary=False
        db_session.query(TableColumn).filter(TableColumn.table_id == test_table.id).update(
            {"is_primary": False}
        )
        db_session.commit()

        # Act
        result = PrimaryKeyCRUD.get_legacy_pk_columns_orm(db_session, table_id=str(test_table.id))

        # Assert
        assert len(result) == 0


# ============================================================================
# GET COLUMNS BY IDS TESTS
# ============================================================================


class TestGetColumnsByIdsOrm:
    """Tests for get_columns_by_ids_orm()"""

    def test_get_columns_by_ids_success(self, db_session: Session, test_columns):
        """Test getting columns by IDs"""
        # Arrange
        column_ids = [str(col.id) for col in test_columns[:2]]

        # Act
        result = PrimaryKeyCRUD.get_columns_by_ids_orm(db_session, column_ids=column_ids)

        # Assert
        assert len(result) == 2
        assert result[0]["name"] in ["user_id", "username"]
        assert result[1]["name"] in ["user_id", "username"]

    def test_get_columns_by_ids_empty_list(self, db_session: Session):
        """Test getting columns with empty ID list"""
        # Act
        result = PrimaryKeyCRUD.get_columns_by_ids_orm(db_session, column_ids=[])

        # Assert
        assert len(result) == 0

    def test_get_columns_by_ids_preserves_order(self, db_session: Session, test_columns):
        """Test that column order is preserved"""
        # Arrange
        column_ids = [str(test_columns[2].id), str(test_columns[0].id)]

        # Act
        result = PrimaryKeyCRUD.get_columns_by_ids_orm(db_session, column_ids=column_ids)

        # Assert
        assert len(result) == 2
        # First result should be email (index 2), second should be user_id (index 0)
        assert result[0]["id"] == str(test_columns[2].id)
        assert result[1]["id"] == str(test_columns[0].id)


# ============================================================================
# GET TABLE BY ID TESTS
# ============================================================================


class TestGetTableByIdOrm:
    """Tests for get_table_by_id_orm()"""

    def test_get_table_by_id_exists(self, db_session: Session, test_table, test_project):
        """Test getting existing table"""
        # Act
        result = PrimaryKeyCRUD.get_table_by_id_orm(db_session, table_id=str(test_table.id))

        # Assert
        assert result is not None
        assert result["id"] == str(test_table.id)
        assert result["name"] == "users"
        assert result["type"] == "origin"
        assert result["project_id"] == str(test_project.id)

    def test_get_table_by_id_not_found(self, db_session: Session):
        """Test getting non-existent table"""
        # Arrange
        non_existent_id = str(uuid.uuid4())

        # Act
        result = PrimaryKeyCRUD.get_table_by_id_orm(db_session, table_id=non_existent_id)

        # Assert
        assert result is None


# ============================================================================
# GET COLUMNS FOR VALIDATION TESTS
# ============================================================================


class TestGetColumnsForValidationOrm:
    """Tests for get_columns_for_validation_orm()"""

    def test_get_columns_for_validation_success(self, db_session: Session, test_columns):
        """Test getting columns for validation"""
        # Arrange
        column_ids = [str(col.id) for col in test_columns[:2]]

        # Act
        result = PrimaryKeyCRUD.get_columns_for_validation_orm(db_session, column_ids=column_ids)

        # Assert
        assert len(result) == 2
        assert all("table_id" in col for col in result)
        assert all("is_nullable" in col for col in result)
        assert all("data_type" in col for col in result)


# ============================================================================
# CREATE PK CONSTRAINT TESTS
# ============================================================================


class TestCreatePkConstraintOrm:
    """Tests for create_pk_constraint_orm()"""

    def test_create_pk_constraint_with_auto_id(self, db_session: Session, test_table, test_columns):
        """Test creating PK constraint with auto-generated ID"""
        # Arrange
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        column_ids = [str(test_columns[0].id)]

        # Act
        result = PrimaryKeyCRUD.create_pk_constraint_orm(
            db_session,
            table_id=str(test_table.id),
            column_ids=column_ids,
            constraint_name="pk_users",
            now=now,
        )

        # Assert
        assert result is not None
        assert result["table_id"] == str(test_table.id)
        assert result["constraint_name"] == "pk_users"
        # Convertir UUIDs a strings para comparación
        assert [str(col_id) for col_id in result["column_ids"]] == column_ids

    def test_create_pk_constraint_without_name(self, db_session: Session, test_table, test_columns):
        """Test creating PK constraint without constraint name"""
        # Arrange
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        column_ids = [str(test_columns[0].id)]

        # Act
        result = PrimaryKeyCRUD.create_pk_constraint_orm(
            db_session,
            table_id=str(test_table.id),
            column_ids=column_ids,
            constraint_name=None,
            now=now,
        )

        # Assert
        assert result is not None
        assert result["constraint_name"] is None


# ============================================================================
# UPDATE PK CONSTRAINT TESTS
# ============================================================================


class TestUpdatePkConstraintOrm:
    """Tests for update_pk_constraint_orm()"""

    def test_update_pk_constraint_success(self, db_session: Session, test_table, test_columns):
        """Test updating PK constraint"""
        # Arrange
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Create initial PK constraint
        pk_constraint = PrimaryKeyConstraint(
            table_id=test_table.id, column_ids=[str(test_columns[0].id)], constraint_name="pk_users"
        )
        db_session.add(pk_constraint)
        db_session.commit()

        # Act - Update to include more columns
        new_column_ids = [str(test_columns[0].id), str(test_columns[1].id)]
        result = PrimaryKeyCRUD.update_pk_constraint_orm(
            db_session,
            table_id=str(test_table.id),
            column_ids=new_column_ids,
            constraint_name="pk_users_updated",
            now=now,
        )

        # Assert
        assert result is not None
        assert len(result["column_ids"]) == 2
        assert result["constraint_name"] == "pk_users_updated"

    def test_update_pk_constraint_change_name(self, db_session: Session, test_table, test_columns):
        """Test updating only constraint name"""
        # Arrange
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Create initial PK constraint
        pk_constraint = PrimaryKeyConstraint(
            table_id=test_table.id, column_ids=[str(test_columns[0].id)], constraint_name="pk_users"
        )
        db_session.add(pk_constraint)
        db_session.commit()

        # Act
        result = PrimaryKeyCRUD.update_pk_constraint_orm(
            db_session,
            table_id=str(test_table.id),
            column_ids=[str(test_columns[0].id)],
            constraint_name="new_pk_name",
            now=now,
        )

        # Assert
        assert result["constraint_name"] == "new_pk_name"

    def test_update_pk_constraint_not_found(self, db_session: Session):
        """Test updating non-existent PK constraint"""
        # Arrange
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        non_existent_table_id = str(uuid.uuid4())
        # Usar un UUID válido en lugar de un string
        valid_column_id = str(uuid.uuid4())

        # Act
        result = PrimaryKeyCRUD.update_pk_constraint_orm(
            db_session,
            table_id=non_existent_table_id,
            column_ids=[valid_column_id],
            constraint_name="pk_test",
            now=now,
        )

        # Assert
        assert result is None


# ============================================================================
# UPDATE COLUMNS PRIMARY FLAG TESTS
# ============================================================================


class TestUpdateColumnsPrimaryFlagOrm:
    """Tests for update_columns_primary_flag_orm()"""

    def test_update_columns_primary_flag_success(
        self, db_session: Session, test_table, test_columns
    ):
        """Test updating is_primary flags on columns"""
        # Arrange
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        column_ids = [str(test_columns[0].id), str(test_columns[1].id)]

        # Act
        PrimaryKeyCRUD.update_columns_primary_flag_orm(
            db_session, table_id=str(test_table.id), column_ids=column_ids, now=now
        )

        # Assert - Verify columns were updated
        col1 = db_session.query(TableColumn).filter(TableColumn.id == test_columns[0].id).first()
        col2 = db_session.query(TableColumn).filter(TableColumn.id == test_columns[1].id).first()
        col3 = db_session.query(TableColumn).filter(TableColumn.id == test_columns[2].id).first()

        assert col1.is_primary is True
        assert col2.is_primary is True
        assert col3.is_primary is False

    def test_update_columns_primary_flag_empty_list(
        self, db_session: Session, test_table, test_columns
    ):
        """Test updating with empty column list"""
        # Arrange
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Act
        PrimaryKeyCRUD.update_columns_primary_flag_orm(
            db_session, table_id=str(test_table.id), column_ids=[], now=now
        )

        # Assert - All columns should have is_primary=False
        columns = db_session.query(TableColumn).filter(TableColumn.table_id == test_table.id).all()

        assert all(col.is_primary is False for col in columns)


# ============================================================================
# DELETE PK CONSTRAINT TESTS
# ============================================================================


class TestDeletePkConstraintOrm:
    """Tests for delete_pk_constraint_orm()"""

    def test_delete_pk_constraint_success(self, db_session: Session, test_table, test_columns):
        """Test deleting PK constraint"""
        # Arrange
        pk_constraint = PrimaryKeyConstraint(
            table_id=test_table.id, column_ids=[str(test_columns[0].id)], constraint_name="pk_users"
        )
        db_session.add(pk_constraint)
        db_session.commit()

        # Act
        PrimaryKeyCRUD.delete_pk_constraint_orm(db_session, table_id=str(test_table.id))

        # Assert
        result = (
            db_session.query(PrimaryKeyConstraint)
            .filter(PrimaryKeyConstraint.table_id == test_table.id)
            .first()
        )
        assert result is None


# ============================================================================
# CLEAR ALL PRIMARY FLAGS TESTS
# ============================================================================


class TestClearAllPrimaryFlagsOrm:
    """Tests for clear_all_primary_flags_orm()"""

    def test_clear_all_primary_flags_success(self, db_session: Session, test_table, test_columns):
        """Test clearing all is_primary flags"""
        # Arrange
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Act
        PrimaryKeyCRUD.clear_all_primary_flags_orm(db_session, table_id=str(test_table.id), now=now)

        # Assert
        columns = db_session.query(TableColumn).filter(TableColumn.table_id == test_table.id).all()

        assert all(col.is_primary is False for col in columns)


# ============================================================================
# INSERT AUDIT LOG TESTS
# ============================================================================


class TestInsertAuditLogOrm:
    """Tests for insert_audit_log_orm()"""

    def test_insert_audit_log_pk_created(self, db_session: Session, test_table, test_user):
        """Test inserting audit log for PK creation"""
        # Arrange
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        old_value = {}
        new_value = {"constraint_name": "pk_users", "column_ids": ["col_1", "col_2"]}

        # Act
        PrimaryKeyCRUD.insert_audit_log_orm(
            db_session,
            action="PK_CREATED",
            table_id=str(test_table.id),
            old_value=old_value,
            new_value=new_value,
            user_id=str(test_user.id),
            timestamp=now,
        )

        # Assert
        audit_log = (
            db_session.query(MigrationAuditLog)
            .filter(
                MigrationAuditLog.action == "PK_CREATED",
                MigrationAuditLog.table_id == test_table.id,
            )
            .first()
        )

        assert audit_log is not None
        assert audit_log.action == "PK_CREATED"
        assert audit_log.new_value == new_value

    def test_insert_audit_log_pk_updated(self, db_session: Session, test_table, test_user):
        """Test inserting audit log for PK update"""
        # Arrange
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        old_value = {"column_ids": ["col_1"]}
        new_value = {"column_ids": ["col_1", "col_2"]}

        # Act
        PrimaryKeyCRUD.insert_audit_log_orm(
            db_session,
            action="PK_UPDATED",
            table_id=str(test_table.id),
            old_value=old_value,
            new_value=new_value,
            user_id=str(test_user.id),
            timestamp=now,
        )

        # Assert
        audit_log = (
            db_session.query(MigrationAuditLog)
            .filter(MigrationAuditLog.action == "PK_UPDATED")
            .first()
        )

        assert audit_log is not None


# ============================================================================
# GET ORIGIN TABLES WITH PKS TESTS
# ============================================================================


class TestGetOriginTablesWithPksOrm:
    """Tests for get_origin_tables_with_pks_orm()"""

    def test_get_origin_tables_with_pks_success(
        self, db_session: Session, test_project, test_table, test_columns
    ):
        """Test getting origin tables with PKs"""
        # Arrange
        pk_constraint = PrimaryKeyConstraint(
            table_id=test_table.id, column_ids=[str(test_columns[0].id)], constraint_name="pk_users"
        )
        db_session.add(pk_constraint)
        db_session.commit()

        # Act
        result = PrimaryKeyCRUD.get_origin_tables_with_pks_orm(
            db_session, project_id=str(test_project.id)
        )

        # Assert
        assert len(result) >= 1
        assert any(r["table_name"] == "users" for r in result)

    def test_get_origin_tables_with_pks_empty(self, db_session: Session, test_project):
        """Test getting origin tables when none have PKs"""
        # Act
        result = PrimaryKeyCRUD.get_origin_tables_with_pks_orm(
            db_session, project_id=str(test_project.id)
        )

        # Assert - test_table doesn't have a PK constraint yet
        assert len(result) == 0


# ============================================================================
# COUNT COLUMN MAPPINGS TESTS
# ============================================================================


class TestCountColumnMappingsOrm:
    """Tests for count_column_mappings_orm()"""

    def test_count_column_mappings_with_results(self, db_session: Session, test_project):
        """Test counting mappings for a column"""
        # Arrange
        for i in range(3):
            mapping = Mapping(
                id=uuid.uuid4(),
                project_id=test_project.id,
                origin_table="users",
                origin_column="user_id",
                destination_table="users_dest",
                destination_column="id",
                transformation_logic=None,  # Campo correcto es transformation_logic
                is_encrypted=False,
            )
            db_session.add(mapping)
        db_session.commit()

        # Act
        result = PrimaryKeyCRUD.count_column_mappings_orm(
            db_session, project_id=str(test_project.id), table_name="users", column_name="user_id"
        )

        # Assert
        assert result == 3

    def test_count_column_mappings_no_mappings(self, db_session: Session, test_project):
        """Test counting when no mappings exist"""
        # Act
        result = PrimaryKeyCRUD.count_column_mappings_orm(
            db_session, project_id=str(test_project.id), table_name="users", column_name="email"
        )

        # Assert
        assert result == 0
