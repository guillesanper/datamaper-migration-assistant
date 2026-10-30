# backend/app/services/schema_service.py
"""
Business logic and validation for schema (tables and columns) operations
"""

import re
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.crud import schemas_crud
from app.utils.error_codes import ErrorCode, make_error

# Validation patterns and constants
# Pattern requires starting with letter or underscore, then allows letters, numbers, and underscores
IDENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# Expanded list of allowed column types (PostgreSQL-compatible)
ALLOWED_COLUMN_TYPES = {
    # Text types
    "TEXT",
    "VARCHAR",
    "CHAR",
    # Integer types
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    # Numeric types with precision
    "NUMERIC",
    "DECIMAL",
    "REAL",
    "FLOAT",
    "DOUBLE PRECISION",
    # Boolean
    "BOOLEAN",
    # Date/Time types
    "DATE",
    "DATETIME",
    "TIME",
    "TIMESTAMP",
    "TIMESTAMPTZ",
    "INTERVAL",
    # JSON types
    "JSON",
    "JSONB",
    # UUID
    "UUID",
    # Binary
    "BYTEA",
    # Network address types
    "INET",
    "MACADDR",
    # Array (generic)
    "ARRAY",
}

# Types that support parameters
PARAMETRIZED_TYPES = {
    "VARCHAR": ["length"],
    "CHAR": ["length"],
    "NUMERIC": ["precision", "scale"],
    "DECIMAL": ["precision", "scale"],
}

ALLOWED_TABLE_TYPES = {"origin", "destination"}


class SchemaService:
    """Service layer for schema operations with business logic"""

    @staticmethod
    def validate_table_name(name: str) -> None:
        """
        Validate table name format

        Raises:
            HTTPException: If name is invalid
        """
        if not name or not name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.TABLE_NAME_REQUIRED),
            )

        name = name.strip()

        if not IDENT_PATTERN.fullmatch(name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.TABLE_NAME_INVALID),
            )

    @staticmethod
    def validate_table_type(table_type: str) -> str:
        """
        Validate and normalize table type

        Returns:
            Normalized table type

        Raises:
            HTTPException: If type is invalid
        """
        if not table_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.TABLE_TYPE_REQUIRED),
            )

        table_type = table_type.strip().lower()

        if table_type not in ALLOWED_TABLE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.TABLE_TYPE_INVALID),
            )

        return table_type

    @staticmethod
    def validate_column_name(name: str) -> None:
        """
        Validate column name format

        Raises:
            HTTPException: If name is invalid
        """
        if not name or not name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.COLUMN_NAME_REQUIRED),
            )

        name = name.strip()

        if not IDENT_PATTERN.fullmatch(name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.COLUMN_NAME_INVALID),
            )

    @staticmethod
    def parse_data_type(data_type: str) -> Dict[str, Any]:
        """
        Parse a data type string into its components

        Args:
            data_type: Full data type string (e.g., "VARCHAR(255)", "NUMERIC(10,2)")

        Returns:
            Dict with base_type, parameters, and full_type

        Examples:
            >>> parse_data_type("VARCHAR(255)")
            {'base_type': 'VARCHAR', 'parameters': {'length': 255}, 'full_type': 'VARCHAR(255)'}

            >>> parse_data_type("NUMERIC(10,2)")
            {'base_type': 'NUMERIC', 'parameters': {'precision': 10, 'scale': 2}, 'full_type': 'NUMERIC(10,2)'}

            >>> parse_data_type("INTEGER")
            {'base_type': 'INTEGER', 'parameters': {}, 'full_type': 'INTEGER'}
        """
        data_type = data_type.strip().upper()

        # Check for parametrized types
        if "(" in data_type and ")" in data_type:
            base_type = data_type[: data_type.index("(")].strip()
            params_str = data_type[data_type.index("(") + 1 : data_type.index(")")].strip()

            parameters = {}

            if "," in params_str:
                # NUMERIC(10,2) or DECIMAL(10,2)
                parts = [p.strip() for p in params_str.split(",")]
                if base_type in ["NUMERIC", "DECIMAL"]:
                    if len(parts) >= 1:
                        parameters["precision"] = int(parts[0])
                    if len(parts) >= 2:
                        parameters["scale"] = int(parts[1])
            else:
                # VARCHAR(255) or CHAR(50)
                if base_type in ["VARCHAR", "CHAR"]:
                    parameters["length"] = int(params_str)

            return {"base_type": base_type, "parameters": parameters, "full_type": data_type}
        else:
            # Simple type without parameters
            return {"base_type": data_type, "parameters": {}, "full_type": data_type}

    @staticmethod
    def validate_column_type(data_type: str) -> str:
        """
        Validate and normalize column data type.
        Now supports parametrized types like VARCHAR(255), NUMERIC(10,2)

        Returns:
            Normalized data type (full type with parameters)

        Raises:
            HTTPException: If data type is invalid
        """
        if not data_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.DATA_TYPE_REQUIRED),
            )

        # Parse the data type
        try:
            parsed = SchemaService.parse_data_type(data_type)
        except (ValueError, IndexError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.DATA_TYPE_FORMAT_INVALID, type=data_type),
            )

        base_type = parsed["base_type"]
        parameters = parsed["parameters"]

        # Validate base type
        if base_type not in ALLOWED_COLUMN_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.DATA_TYPE_INVALID),
            )

        # Validate parameters if present
        if base_type in PARAMETRIZED_TYPES:
            expected_params = PARAMETRIZED_TYPES[base_type]

            # Validate parameter ranges
            if base_type in ["VARCHAR", "CHAR"]:
                if "length" in parameters:
                    length = parameters["length"]
                    if length < 1 or length > 10485760:  # PostgreSQL max
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=make_error(
                                ErrorCode.LENGTH_INVALID, type=base_type, min=1, max=10485760
                            ),
                        )

            elif base_type in ["NUMERIC", "DECIMAL"]:
                if "precision" in parameters:
                    precision = parameters["precision"]
                    if precision < 1 or precision > 1000:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=make_error(
                                ErrorCode.PRECISION_INVALID, type=base_type, min=1, max=1000
                            ),
                        )

                if "scale" in parameters:
                    scale = parameters["scale"]
                    precision = parameters.get("precision", 1000)

                    if scale < 0 or scale > precision:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=make_error(
                                ErrorCode.SCALE_INVALID, type=base_type, precision=precision
                            ),
                        )

        return str(parsed["full_type"])

    @staticmethod
    def can_user_modify_schema(db, project_id: str, user_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if user can modify schema (must be owner or editor)

        Returns:
            Tuple of (can_modify, project_data)

        Raises:
            HTTPException: If project not found or user has no permission
        """
        from app.models.orm.project import MemberRole, Project, ProjectMember

        # Get project using SQLAlchemy ORM
        project = db.query(Project).filter(Project.id == project_id).first()

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=make_error(ErrorCode.PROJECT_NOT_FOUND),
            )

        project_dict = {
            "id": str(project.id),
            "name": project.name,
            "origin_db": project.origin_db,
            "destination_db": project.destination_db,
            "owner_id": str(project.owner_id),
        }

        # Check if user is owner
        if str(project.owner_id) == str(user_id):
            return True, project_dict

        # Check if user is editor
        member = (
            db.query(ProjectMember)
            .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
            .first()
        )

        if not member or member.role != MemberRole.EDITOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=make_error(ErrorCode.SCHEMA_NO_PERMISSION),
            )

        return True, project_dict

    @staticmethod
    def create_table_with_validation(
        db,
        project_id: str,
        user_id: str,
        name: str,
        table_type: str,
        encryption_key: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """
        Create a table with full validation

        Args:
            db: Database connection
            project_id: Project ID
            user_id: User ID
            name: Table name
            table_type: Table type ('origin' or 'destination')
            encryption_key: Optional encryption key from session

        Returns:
            Created table data

        Raises:
            HTTPException: If validation fails or limits exceeded
        """
        # Validate permissions
        SchemaService.can_user_modify_schema(db, project_id, user_id)

        # Validate input
        SchemaService.validate_table_name(name)
        table_type = SchemaService.validate_table_type(table_type)

        name = name.strip()

        # Check limits
        has_pro, current_count, max_allowed = schemas_crud.check_table_limits_orm(db, project_id)

        if current_count >= max_allowed:
            if has_pro:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=make_error(ErrorCode.TABLE_LIMIT, max=max_allowed, plan="Pro"),
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=make_error(ErrorCode.TABLE_LIMIT, max=max_allowed, plan="Free"),
                )

        # Check for duplicates
        existing = schemas_crud.get_table_by_name_orm(db, project_id, name, table_type)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.TABLE_DUPLICATE, type=table_type, name=name),
            )

        # Create table with encryption key if provided
        try:
            table = schemas_crud.create_table_orm(
                db, project_id, name, table_type, user_id, encryption_key
            )
            return table
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.TABLE_DUPLICATE, type=table_type, name=name),
            )

    @staticmethod
    def update_table_with_validation(
        db, table_id: str, user_id: str, name: str, encryption_key: Optional[bytes] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update a table with validation

        Args:
            db: Database connection
            table_id: Table ID to update
            user_id: User ID
            name: New table name
            encryption_key: Optional encryption key from session

        Returns:
            Updated table data

        Raises:
            HTTPException: If validation fails or table not found
        """
        # Get table and check it exists
        table = schemas_crud.get_table_by_id_orm(db, table_id, encryption_key)  # type: ignore[arg-type]
        if not table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=make_error(ErrorCode.TABLE_NOT_FOUND)
            )

        # Validate permissions
        SchemaService.can_user_modify_schema(db, table["project_id"], user_id)

        # Validate input
        SchemaService.validate_table_name(name)
        name = name.strip()

        # Check for name conflicts (different table with same name and type)
        existing = schemas_crud.get_table_by_name_orm(db, table["project_id"], name, table["type"])
        if existing and existing["id"] != table_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.TABLE_DUPLICATE, type=table["type"], name=name),
            )

        # Update table with encryption key if provided
        try:
            updated_table = schemas_crud.update_table_orm(
                db, table_id, name, user_id, encryption_key
            )
            return updated_table
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.TABLE_DUPLICATE, type="", name=name),
            )

    @staticmethod
    def delete_table_with_cleanup(
        db, table_id: str, user_id: str
    ) -> Tuple[Dict[str, Any], int, int]:
        """
        Delete a table and clean up related data

        Returns:
            Tuple of (table_data, columns_deleted, mappings_deleted)

        Raises:
            HTTPException: If table not found or no permission
        """
        # Get table and check it exists
        table = schemas_crud.get_table_by_id_orm(db, table_id)
        if not table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=make_error(ErrorCode.TABLE_NOT_FOUND)
            )

        # Validate permissions
        SchemaService.can_user_modify_schema(db, table["project_id"], user_id)

        # Delete table (includes columns and mappings)
        table_data, column_names, mappings_deleted = schemas_crud.delete_table_orm(
            db, table_id, user_id
        )

        if not table_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=make_error(ErrorCode.TABLE_NOT_FOUND)
            )

        columns_deleted = len(column_names)

        return table_data, columns_deleted, mappings_deleted

    @staticmethod
    def create_column_with_validation(
        db,
        table_id: str,
        user_id: str,
        name: str,
        data_type: str,
        is_nullable: bool = True,
        is_primary: bool = False,
        is_autogenerated: bool = False,
        encryption_key: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """
        Create a column with full validation

        Args:
            db: Database connection
            table_id: Table ID
            user_id: User ID
            name: Column name
            data_type: Column data type
            is_nullable: Whether column can be null
            is_primary: Whether column is primary key
            is_autogenerated: Whether column is autogenerated
            encryption_key: Optional encryption key from session (bytes)

        Returns:
            Created column data

        Raises:
            HTTPException: If validation fails or limits exceeded
        """
        # Get table and check it exists
        table = schemas_crud.get_table_by_id_orm(db, table_id)
        if not table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=make_error(ErrorCode.TABLE_NOT_FOUND)
            )

        # Validate permissions
        SchemaService.can_user_modify_schema(db, table["project_id"], user_id)

        # Validate input
        SchemaService.validate_column_name(name)
        data_type = SchemaService.validate_column_type(data_type)

        name = name.strip()

        # Check limits
        has_pro, current_count, max_allowed = schemas_crud.check_column_limits_orm(db, table_id)

        if current_count >= max_allowed:
            plan_name = "Pro" if has_pro else "Free"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=make_error(ErrorCode.COLUMN_LIMIT, max=max_allowed, plan=plan_name),
            )

        # Create column
        try:
            column = schemas_crud.create_column_orm(
                db,
                table_id,
                name,
                data_type,
                table["type"],
                is_nullable,
                is_primary,
                is_autogenerated,
                user_id,
                encryption_key,
            )
            return column
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.COLUMN_DUPLICATE, name=name),
            )

    @staticmethod
    def update_column_with_validation(
        db,
        column_id: str,
        user_id: str,
        name: str,
        data_type: str,
        is_nullable: bool,
        is_primary: bool,
        is_autogenerated: bool,
        encryption_key: Optional[bytes] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], int]:
        """
        Update a column with validation

        Args:
            db: Database connection
            column_id: Column ID
            user_id: User ID
            name: New column name
            data_type: New column data type
            is_nullable: Whether column can be null
            is_primary: Whether column is primary key
            is_autogenerated: Whether column is autogenerated
            encryption_key: Optional encryption key from session (bytes)

        Returns:
            Tuple of (old_data, new_data, mappings_renamed)

        Raises:
            HTTPException: If validation fails or column not found
        """
        # Get column and check it exists
        column = schemas_crud.get_column_by_id_orm(db, column_id, encryption_key)
        if not column:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=make_error(ErrorCode.COLUMN_NOT_FOUND)
            )

        # Validate permissions
        SchemaService.can_user_modify_schema(db, column["project_id"], user_id)

        # Validate input
        SchemaService.validate_column_name(name)
        data_type = SchemaService.validate_column_type(data_type)

        name = name.strip()

        # Update column
        try:
            old_data, new_data, mappings_renamed = schemas_crud.update_column_orm(
                db,
                column_id,
                name,
                data_type,
                column["table_type"],
                is_nullable,
                is_primary,
                is_autogenerated,
                user_id,
                encryption_key,
            )

            if not new_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=make_error(ErrorCode.COLUMN_NOT_FOUND),
                )

            return old_data, new_data, mappings_renamed
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=make_error(ErrorCode.COLUMN_DUPLICATE, name=name),
            )

    @staticmethod
    def delete_column_with_cleanup(db, column_id: str, user_id: str) -> Tuple[Dict[str, Any], int]:
        """
        Delete a column and clean up related mappings

        Returns:
            Tuple of (column_data, mappings_deleted)

        Raises:
            HTTPException: If column not found or no permission
        """
        # Get column and check it exists
        column = schemas_crud.get_column_by_id_orm(db, column_id)
        if not column:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=make_error(ErrorCode.COLUMN_NOT_FOUND)
            )

        # Validate permissions
        SchemaService.can_user_modify_schema(db, column["project_id"], user_id)

        # Delete column
        column_data, mappings_deleted = schemas_crud.delete_column_orm(db, column_id, user_id)

        if not column_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=make_error(ErrorCode.COLUMN_NOT_FOUND)
            )

        return column_data, mappings_deleted
