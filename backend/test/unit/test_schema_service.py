"""
Unit tests for app.services.schema_service module

Tests for SchemaService:
- Table name validation
- Table type validation
- Column name validation
- Data type parsing
- Column type validation
- User permissions validation
- Create/update/delete operations with validation
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status

from app.services.schema_service import ALLOWED_COLUMN_TYPES, SchemaService

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


# ============================================================================
# TABLE NAME VALIDATION TESTS
# ============================================================================


class TestValidateTableName:
    """Tests for validate_table_name()"""

    def test_validate_table_name_valid(self):
        """Test validation of valid table names"""
        valid_names = ["users", "UserTable", "user_table", "_private_table", "table123", "t"]

        for name in valid_names:
            # Should not raise
            SchemaService.validate_table_name(name)

    def test_validate_table_name_empty(self):
        """Test validation fails for empty name"""
        with pytest.raises(HTTPException) as exc_info:
            SchemaService.validate_table_name("")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "obligatorio" in exc_info.value.detail

    def test_validate_table_name_whitespace(self):
        """Test validation fails for whitespace-only name"""
        with pytest.raises(HTTPException) as exc_info:
            SchemaService.validate_table_name("   ")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    def test_validate_table_name_invalid_characters(self):
        """Test validation fails for invalid characters"""
        invalid_names = [
            "user-table",  # Hyphen not allowed
            "user table",  # Space not allowed
            "user@table",  # Special char not allowed
            "123table",  # Cannot start with number
        ]

        for name in invalid_names:
            with pytest.raises(HTTPException):
                SchemaService.validate_table_name(name)

    def test_validate_table_name_too_long(self):
        """Test validation fails for names exceeding 63 characters"""
        long_name = "a" * 64

        with pytest.raises(HTTPException) as exc_info:
            SchemaService.validate_table_name(long_name)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# TABLE TYPE VALIDATION TESTS
# ============================================================================


class TestValidateTableType:
    """Tests for validate_table_type()"""

    def test_validate_table_type_origin(self):
        """Test validation of 'origin' table type"""
        result = SchemaService.validate_table_type("origin")

        assert result == "origin"

    def test_validate_table_type_destination(self):
        """Test validation of 'destination' table type"""
        result = SchemaService.validate_table_type("destination")

        assert result == "destination"

    def test_validate_table_type_case_insensitive(self):
        """Test validation is case-insensitive"""
        result = SchemaService.validate_table_type("ORIGIN")

        assert result == "origin"

    def test_validate_table_type_whitespace_trimmed(self):
        """Test validation trims whitespace"""
        result = SchemaService.validate_table_type("  destination  ")

        assert result == "destination"

    def test_validate_table_type_invalid(self):
        """Test validation fails for invalid types"""
        with pytest.raises(HTTPException) as exc_info:
            SchemaService.validate_table_type("invalid")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "inválido" in exc_info.value.detail

    def test_validate_table_type_empty(self):
        """Test validation fails for empty type"""
        with pytest.raises(HTTPException) as exc_info:
            SchemaService.validate_table_type("")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# COLUMN NAME VALIDATION TESTS
# ============================================================================


class TestValidateColumnName:
    """Tests for validate_column_name()"""

    def test_validate_column_name_valid(self):
        """Test validation of valid column names"""
        valid_names = ["id", "user_name", "firstName", "_hidden", "col123"]

        for name in valid_names:
            # Should not raise
            SchemaService.validate_column_name(name)

    def test_validate_column_name_empty(self):
        """Test validation fails for empty name"""
        with pytest.raises(HTTPException) as exc_info:
            SchemaService.validate_column_name("")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    def test_validate_column_name_invalid(self):
        """Test validation fails for invalid names"""
        invalid_names = [
            "column name",  # Space
            "column-name",  # Hyphen
            "123column",  # Starts with number
        ]

        for name in invalid_names:
            with pytest.raises(HTTPException):
                SchemaService.validate_column_name(name)


# ============================================================================
# DATA TYPE PARSING TESTS
# ============================================================================


class TestParseDataType:
    """Tests for parse_data_type()"""

    def test_parse_data_type_simple(self):
        """Test parsing simple data types"""
        result = SchemaService.parse_data_type("INTEGER")

        assert result["base_type"] == "INTEGER"
        assert result["parameters"] == {}

    def test_parse_data_type_varchar_with_length(self):
        """Test parsing VARCHAR with length parameter"""
        result = SchemaService.parse_data_type("VARCHAR(255)")

        assert result["base_type"] == "VARCHAR"
        assert result["parameters"]["length"] == 255

    def test_parse_data_type_numeric_with_precision(self):
        """Test parsing NUMERIC with precision and scale"""
        result = SchemaService.parse_data_type("NUMERIC(10,2)")

        assert result["base_type"] == "NUMERIC"
        assert result["parameters"]["precision"] == 10
        assert result["parameters"]["scale"] == 2

    def test_parse_data_type_case_insensitive(self):
        """Test parsing is case-insensitive"""
        result = SchemaService.parse_data_type("varchar(100)")

        assert result["base_type"] == "VARCHAR"
        assert result["parameters"]["length"] == 100

    def test_parse_data_type_whitespace(self):
        """Test parsing handles whitespace"""
        result = SchemaService.parse_data_type("  VARCHAR  ( 50 )  ")

        assert result["base_type"] == "VARCHAR"
        assert result["parameters"]["length"] == 50


# ============================================================================
# COLUMN TYPE VALIDATION TESTS
# ============================================================================


class TestValidateColumnType:
    """Tests for validate_column_type()"""

    def test_validate_column_type_allowed_simple(self):
        """Test validation of allowed simple types"""
        allowed_types = ["TEXT", "INTEGER", "BOOLEAN", "DATE"]

        for data_type in allowed_types:
            result = SchemaService.validate_column_type(data_type)
            assert result.upper() == data_type

    def test_validate_column_type_varchar_with_params(self):
        """Test validation of VARCHAR with parameters"""
        result = SchemaService.validate_column_type("VARCHAR(255)")

        assert "VARCHAR" in result

    def test_validate_column_type_numeric_with_params(self):
        """Test validation of NUMERIC with parameters"""
        result = SchemaService.validate_column_type("NUMERIC(10,2)")

        assert "NUMERIC" in result

    def test_validate_column_type_invalid(self):
        """Test validation fails for invalid types"""
        with pytest.raises(HTTPException) as exc_info:
            SchemaService.validate_column_type("INVALID_TYPE")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    def test_validate_column_type_empty(self):
        """Test validation fails for empty type"""
        with pytest.raises(HTTPException) as exc_info:
            SchemaService.validate_column_type("")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# USER PERMISSIONS TESTS
# ============================================================================


class TestCanUserModifySchema:
    """Tests for can_user_modify_schema() - SQLAlchemy ORM"""

    def test_can_user_modify_schema_owner(self, mock_db):
        """Test owner can modify schema"""
        # Create mock project
        mock_project = MagicMock()
        mock_project.id = "proj_123"
        mock_project.name = "Test"
        mock_project.origin_db = "db1"
        mock_project.destination_db = "db2"
        mock_project.owner_id = "user_123"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_project

        can_modify, project_data = SchemaService.can_user_modify_schema(
            mock_db, "proj_123", "user_123"
        )

        assert can_modify is True
        assert project_data["owner_id"] == "user_123"

    def test_can_user_modify_schema_editor(self, mock_db):
        """Test editor can modify schema"""
        from app.models.orm.project import MemberRole

        # Create mock project
        mock_project = MagicMock()
        mock_project.id = "proj_123"
        mock_project.name = "Test"
        mock_project.origin_db = "db1"
        mock_project.destination_db = "db2"
        mock_project.owner_id = "other_user"

        # Create mock member with editor role
        mock_member = MagicMock()
        mock_member.role = MemberRole.EDITOR

        # First query returns project, second returns member
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_project,
            mock_member,
        ]

        can_modify, project_data = SchemaService.can_user_modify_schema(
            mock_db, "proj_123", "user_123"
        )

        assert can_modify is True

    def test_can_user_modify_schema_viewer(self, mock_db):
        """Test viewer cannot modify schema"""
        from app.models.orm.project import MemberRole

        # Create mock project
        mock_project = MagicMock()
        mock_project.id = "proj_123"
        mock_project.name = "Test"
        mock_project.origin_db = "db1"
        mock_project.destination_db = "db2"
        mock_project.owner_id = "other_user"

        # Create mock member with viewer role
        mock_member = MagicMock()
        mock_member.role = MemberRole.VIEWER

        # First query returns project, second returns member
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_project,
            mock_member,
        ]

        with pytest.raises(HTTPException) as exc_info:
            SchemaService.can_user_modify_schema(mock_db, "proj_123", "user_123")

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    def test_can_user_modify_schema_no_access(self, mock_db):
        """Test user with no access cannot modify"""
        # Create mock project
        mock_project = MagicMock()
        mock_project.id = "proj_123"
        mock_project.name = "Test"
        mock_project.origin_db = "db1"
        mock_project.destination_db = "db2"
        mock_project.owner_id = "other_user"

        # First query returns project, second returns None (no member)
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_project, None]

        with pytest.raises(HTTPException) as exc_info:
            SchemaService.can_user_modify_schema(mock_db, "proj_123", "user_123")

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# CREATE TABLE TESTS
# ============================================================================


class TestCreateTableWithValidation:
    """Tests for create_table_with_validation()"""

    @patch("app.services.schema_service.schemas_crud.check_table_limits_orm")
    @patch("app.services.schema_service.schemas_crud.get_table_by_name_orm")
    @patch("app.services.schema_service.SchemaService.can_user_modify_schema")
    @patch("app.services.schema_service.schemas_crud.create_table_orm")
    def test_create_table_success(
        self, mock_create_table, mock_can_modify, mock_get_table_by_name, mock_check_limits, mock_db
    ):
        """Test successful table creation"""
        mock_can_modify.return_value = (True, {"id": "proj_123"})
        mock_check_limits.return_value = (False, 5, 60)  # has_pro, current_count, max_allowed
        mock_get_table_by_name.return_value = None  # No existing table
        mock_create_table.return_value = {
            "id": "table_123",
            "name": "users",
            "table_type": "origin",
        }

        result = SchemaService.create_table_with_validation(
            mock_db, "proj_123", "user_123", "users", "origin"
        )

        assert result["name"] == "users"

        # Verify validations were called
        mock_can_modify.assert_called_once()
        mock_create_table.assert_called_once()

    @patch("app.services.schema_service.SchemaService.can_user_modify_schema")
    def test_create_table_no_permission(self, mock_can_modify, mock_db):
        """Test table creation fails without permission"""
        mock_can_modify.side_effect = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para modificar el esquema de este proyecto",
        )

        with pytest.raises(HTTPException) as exc_info:
            SchemaService.create_table_with_validation(
                mock_db, "proj_123", "user_123", "users", "origin"
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @patch("app.services.schema_service.SchemaService.can_user_modify_schema")
    def test_create_table_invalid_name(self, mock_can_modify, mock_db):
        """Test table creation fails with invalid name"""
        mock_can_modify.return_value = (True, {"id": "proj_123"})

        with pytest.raises(HTTPException):
            SchemaService.create_table_with_validation(
                mock_db,
                "proj_123",
                "user_123",
                "invalid-name",  # Invalid: contains hyphen
                "origin",
            )


# ============================================================================
# CREATE COLUMN TESTS
# ============================================================================


class TestCreateColumnWithValidation:
    """Tests for create_column_with_validation()"""

    @patch("app.services.schema_service.schemas_crud.check_column_limits_orm")
    @patch("app.services.schema_service.SchemaService.can_user_modify_schema")
    @patch("app.services.schema_service.schemas_crud.get_table_by_id_orm")
    @patch("app.services.schema_service.schemas_crud.create_column_orm")
    def test_create_column_success(
        self, mock_create_column, mock_get_table, mock_can_modify, mock_check_limits, mock_db
    ):
        """Test successful column creation"""
        mock_get_table.return_value = {
            "id": "table_123",
            "project_id": "proj_123",
            "name": "users",
            "type": "origin",
        }
        mock_can_modify.return_value = (True, {"id": "proj_123"})
        mock_check_limits.return_value = (False, 10, 60)
        mock_create_column.return_value = {
            "id": "col_123",
            "name": "email",
            "data_type": "VARCHAR(255)",
        }

        result = SchemaService.create_column_with_validation(
            mock_db, "table_123", "user_123", "email", "VARCHAR(255)"
        )

        assert result["name"] == "email"

        mock_get_table.assert_called_once()
        mock_can_modify.assert_called_once()
        mock_create_column.assert_called_once()

    @patch("app.services.schema_service.SchemaService.can_user_modify_schema")
    @patch("app.services.schema_service.schemas_crud.get_table_by_id_orm")
    def test_create_column_no_permission(self, mock_get_table, mock_can_modify, mock_db):
        """Test column creation fails without permission"""
        mock_get_table.return_value = {
            "id": "table_123",
            "project_id": "proj_123",
            "name": "users",
            "type": "origin",
        }
        mock_can_modify.side_effect = HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para modificar el esquema de este proyecto",
        )

        with pytest.raises(HTTPException) as exc_info:
            SchemaService.create_column_with_validation(
                mock_db, "table_123", "user_123", "email", "VARCHAR(255)"
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


# ============================================================================
# CONSTANTS TESTS
# ============================================================================


class TestConstants:
    """Tests for module constants"""

    def test_allowed_column_types_complete(self):
        """Test that common column types are allowed"""
        common_types = ["TEXT", "INTEGER", "VARCHAR", "BOOLEAN", "DATE", "JSON"]

        for type_name in common_types:
            assert type_name in ALLOWED_COLUMN_TYPES

    def test_allowed_column_types_count(self):
        """Test reasonable number of allowed types"""
        assert len(ALLOWED_COLUMN_TYPES) > 10
        assert len(ALLOWED_COLUMN_TYPES) < 50
