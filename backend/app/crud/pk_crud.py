"""
CRUD operations for Primary Key constraints
Handles all database queries related to primary keys
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


class PrimaryKeyCRUD:
    """CRUD operations for Primary Key constraints"""

    # ========================================================================
    # SQLALCHEMY ORM VERSIONS - Funciones con sufijo _orm
    # ========================================================================

    @staticmethod
    def get_pk_constraint_by_table_id_orm(db, table_id: str) -> Optional[Dict[str, Any]]:
        """
        Get primary key constraint for a table (ORM version)

        Args:
            db: SQLAlchemy Session
            table_id: ID of the table (UUID string)

        Returns:
            Primary key constraint record as dict or None
        """
        from app.models.orm import PrimaryKeyConstraint
        from app.utils.orm_helpers import model_to_dict

        pk_constraint = (
            db.query(PrimaryKeyConstraint).filter(PrimaryKeyConstraint.table_id == table_id).first()
        )

        return model_to_dict(pk_constraint) if pk_constraint else None

    @staticmethod
    def get_legacy_pk_columns_orm(db, table_id: str) -> List[Dict[str, Any]]:
        """
        Get columns marked as primary key (legacy approach) (ORM version)

        Args:
            db: SQLAlchemy Session
            table_id: ID of the table (UUID string)

        Returns:
            List of columns with is_primary=true as dicts
        """
        from app.models.orm import TableColumn

        columns = (
            db.query(
                TableColumn.id, TableColumn.name, TableColumn.data_type, TableColumn.is_nullable
            )
            .filter(TableColumn.table_id == table_id, TableColumn.is_primary == True)
            .order_by(TableColumn.id)
            .all()
        )

        return [
            {"id": str(col_id), "name": name, "data_type": data_type, "is_nullable": is_nullable}
            for col_id, name, data_type, is_nullable in columns
        ]

    @staticmethod
    def get_columns_by_ids_orm(db, column_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get column details by their IDs, preserving order (ORM version)

        Args:
            db: SQLAlchemy Session
            column_ids: List of column IDs (UUID strings)

        Returns:
            List of column records in the specified order
        """
        from sqlalchemy import case

        from app.models.orm import TableColumn

        if not column_ids:
            return []

        # Create ordering based on position in the list
        whens = {col_id: index for index, col_id in enumerate(column_ids)}
        order_case = case(whens, value=TableColumn.id)

        columns = (
            db.query(
                TableColumn.id,
                TableColumn.name,
                TableColumn.data_type,
                TableColumn.is_nullable,
                TableColumn.is_primary,
            )
            .filter(TableColumn.id.in_(column_ids))
            .order_by(order_case)
            .all()
        )

        return [
            {
                "id": str(col_id),
                "name": name,
                "data_type": data_type,
                "is_nullable": is_nullable,
                "is_primary": is_primary,
            }
            for col_id, name, data_type, is_nullable, is_primary in columns
        ]

    @staticmethod
    def get_table_by_id_orm(db, table_id: str) -> Optional[Dict[str, Any]]:
        """
        Get table information by ID (ORM version)

        Args:
            db: SQLAlchemy Session
            table_id: ID of the table (UUID string)

        Returns:
            Table record as dict or None
        """
        from app.models.orm import Table

        table = (
            db.query(Table.id, Table.name, Table.type, Table.project_id)
            .filter(Table.id == table_id)
            .first()
        )

        if not table:
            return None

        return {
            "id": str(table.id),
            "name": table.name,
            "type": table.type,
            "project_id": str(table.project_id),
        }

    @staticmethod
    def get_columns_for_validation_orm(db, column_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get columns for validation (includes table_id) (ORM version)

        Args:
            db: SQLAlchemy Session
            column_ids: List of column IDs (UUID strings)

        Returns:
            List of column records with table_id
        """
        from app.models.orm import TableColumn

        columns = (
            db.query(
                TableColumn.id,
                TableColumn.name,
                TableColumn.data_type,
                TableColumn.table_id,
                TableColumn.is_nullable,
            )
            .filter(TableColumn.id.in_(column_ids))
            .all()
        )

        return [
            {
                "id": str(col_id),
                "name": name,
                "data_type": data_type,
                "table_id": str(table_id),
                "is_nullable": is_nullable,
            }
            for col_id, name, data_type, table_id, is_nullable in columns
        ]

    @staticmethod
    def create_pk_constraint_orm(
        db,
        table_id: str,
        column_ids: List[str],
        constraint_name: Optional[str],
        now: datetime,
        pk_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a new primary key constraint (ORM version)

        Args:
            db: SQLAlchemy Session
            table_id: ID of the table (UUID string)
            column_ids: List of column IDs (UUID strings)
            constraint_name: Optional constraint name
            now: Timestamp for created_at/updated_at
            pk_id: Optional ID for the constraint (if None, auto-generated)

        Returns:
            Created constraint record as dict
        """
        from app.models.orm import PrimaryKeyConstraint
        from app.utils.orm_helpers import model_to_dict

        new_pk = PrimaryKeyConstraint(
            table_id=table_id,
            column_ids=column_ids,
            constraint_name=constraint_name,
            created_at=now,
            updated_at=now,
        )

        if pk_id is not None:
            new_pk.id = pk_id  # type: ignore[assignment]

        db.add(new_pk)
        db.flush()
        db.commit()
        db.refresh(new_pk)

        result = model_to_dict(new_pk)
        assert result is not None, "model_to_dict returned None for a non-None model"
        return result

    @staticmethod
    def update_pk_constraint_orm(
        db, table_id: str, column_ids: List[str], constraint_name: Optional[str], now: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing primary key constraint (ORM version)

        Args:
            db: SQLAlchemy Session
            table_id: ID of the table (UUID string)
            column_ids: List of column IDs (UUID strings)
            constraint_name: Optional constraint name
            now: Timestamp for updated_at

        Returns:
            Updated constraint record as dict or None
        """
        from app.models.orm import PrimaryKeyConstraint
        from app.utils.orm_helpers import model_to_dict

        result = (
            db.query(PrimaryKeyConstraint)
            .filter(PrimaryKeyConstraint.table_id == table_id)
            .update(
                {"column_ids": column_ids, "constraint_name": constraint_name, "updated_at": now},
                synchronize_session="fetch",
            )
        )

        db.commit()

        if result == 0:
            return None

        # Get updated constraint
        pk_constraint = (
            db.query(PrimaryKeyConstraint).filter(PrimaryKeyConstraint.table_id == table_id).first()
        )

        return model_to_dict(pk_constraint) if pk_constraint else None

    @staticmethod
    def update_columns_primary_flag_orm(
        db, table_id: str, column_ids: List[str], now: datetime
    ) -> None:
        """
        Update is_primary flag on columns (ORM version)
        Sets true for specified columns, false for others in the table

        Args:
            db: SQLAlchemy Session
            table_id: ID of the table (UUID string)
            column_ids: List of column IDs (UUID strings) that should be marked as primary
            now: Timestamp for updated_at
        """
        from sqlalchemy import case

        from app.models.orm import TableColumn

        # Update all columns for this table
        db.query(TableColumn).filter(TableColumn.table_id == table_id).update(
            {
                "is_primary": case((TableColumn.id.in_(column_ids), True), else_=False),
                "updated_at": now,
            },
            synchronize_session="fetch",
        )

        db.commit()

    @staticmethod
    def delete_pk_constraint_orm(db, table_id: str) -> None:
        """
        Delete primary key constraint for a table (ORM version)

        Args:
            db: SQLAlchemy Session
            table_id: ID of the table (UUID string)
        """
        from app.models.orm import PrimaryKeyConstraint

        db.query(PrimaryKeyConstraint).filter(PrimaryKeyConstraint.table_id == table_id).delete()

        db.commit()

    @staticmethod
    def clear_all_primary_flags_orm(db, table_id: str, now: datetime) -> None:
        """
        Set is_primary to false for all columns in a table (ORM version)

        Args:
            db: SQLAlchemy Session
            table_id: ID of the table (UUID string)
            now: Timestamp for updated_at
        """
        from app.models.orm import TableColumn

        db.query(TableColumn).filter(TableColumn.table_id == table_id).update(
            {"is_primary": False, "updated_at": now}, synchronize_session="fetch"
        )

        db.commit()

    @staticmethod
    def insert_audit_log_orm(
        db,
        action: str,
        table_id: str,
        old_value: Dict[str, Any],
        new_value: Dict[str, Any],
        user_id: str,
        timestamp: datetime,
    ) -> None:
        """
        Insert an audit log entry for PK operations (ORM version)

        Args:
            db: SQLAlchemy Session
            action: Action type (e.g., 'PK_CREATED', 'PK_UPDATED', 'PK_REMOVED')
            table_id: ID of the table (UUID string)
            old_value: Previous state
            new_value: New state
            user_id: UUID of the user performing the action
            timestamp: Timestamp of the action
        """
        from app.models.orm import MigrationAuditLog

        audit_log = MigrationAuditLog(
            migration_number="001",
            action=action,
            table_id=table_id,
            old_value=old_value,
            new_value=new_value,
            user_id=user_id,
            timestamp=timestamp,
        )

        db.add(audit_log)
        db.commit()

    @staticmethod
    def get_origin_tables_with_pks_orm(db, project_id: str) -> List[Dict[str, Any]]:
        """
        Get all origin tables with primary keys (ORM version)

        Args:
            db: SQLAlchemy Session
            project_id: UUID of the project

        Returns:
            List of origin tables with their PK column IDs
        """
        from app.models.orm import PrimaryKeyConstraint, Table

        results = (
            db.query(
                Table.id.label("table_id"),
                Table.name.label("table_name"),
                PrimaryKeyConstraint.column_ids,
            )
            .join(PrimaryKeyConstraint, PrimaryKeyConstraint.table_id == Table.id)
            .filter(Table.project_id == project_id, Table.type == "origin")
            .all()
        )

        return [
            {"table_id": str(table_id), "table_name": table_name, "column_ids": column_ids}
            for table_id, table_name, column_ids in results
        ]

    @staticmethod
    def count_column_mappings_orm(db, project_id: str, table_name: str, column_name: str) -> int:
        """
        Count mappings for a specific column (ORM version)

        Args:
            db: SQLAlchemy Session
            project_id: UUID of the project
            table_name: Name of the origin table
            column_name: Name of the origin column

        Returns:
            Count of mappings
        """
        from app.models.orm import Mapping

        count = (
            db.query(Mapping)
            .filter(
                Mapping.project_id == project_id,
                Mapping.origin_table == table_name,
                Mapping.origin_column == column_name,
            )
            .count()
        )

        return int(count)
