"""
CRUD operations for Primary Key constraints
Handles all database queries related to primary keys
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from psycopg2.extras import Json, RealDictCursor, RealDictRow


class PrimaryKeyCRUD:
    """CRUD operations for Primary Key constraints"""

    @staticmethod
    def get_pk_constraint_by_table_id(
        cursor: RealDictCursor, table_id: int
    ) -> Optional[RealDictRow]:
        """
        Get primary key constraint for a table

        Args:
            cursor: Database cursor
            table_id: ID of the table (integer)

        Returns:
            Primary key constraint record or None
        """
        cursor.execute(
            """
            SELECT *
            FROM primary_key_constraints
            WHERE table_id = %s
        """,
            (table_id,),
        )
        return cursor.fetchone()

    @staticmethod
    def get_legacy_pk_columns(cursor: RealDictCursor, table_id: int) -> List[RealDictRow]:
        """
        Get columns marked as primary key (legacy approach)

        Args:
            cursor: Database cursor
            table_id: ID of the table (integer)

        Returns:
            List of columns with is_primary=true
        """
        cursor.execute(
            """
            SELECT id, name, data_type, is_nullable
            FROM columns
            WHERE table_id = %s AND is_primary = true
            ORDER BY id
        """,
            (table_id,),
        )
        return list(cursor.fetchall())

    @staticmethod
    def get_columns_by_ids(cursor: RealDictCursor, column_ids: List[int]) -> List[RealDictRow]:
        """
        Get column details by their IDs, preserving order

        Args:
            cursor: Database cursor
            column_ids: List of column IDs (integers)

        Returns:
            List of column records in the specified order
        """
        if not column_ids:
            return []

        cursor.execute(
            """
            SELECT id, name, data_type, is_nullable, is_primary
            FROM columns
            WHERE id = ANY(%s::uuid[])
            ORDER BY array_position(%s::uuid[], id)
        """,
            (column_ids, column_ids),
        )
        return list(cursor.fetchall())

    @staticmethod
    def get_table_by_id(cursor: RealDictCursor, table_id: int) -> Optional[RealDictRow]:
        """
        Get table information by ID

        Args:
            cursor: Database cursor
            table_id: ID of the table (integer)

        Returns:
            Table record or None
        """
        cursor.execute(
            """
            SELECT id, name, type, project_id
            FROM tables
            WHERE id = %s
        """,
            (table_id,),
        )
        return cursor.fetchone()

    @staticmethod
    def get_columns_for_validation(
        cursor: RealDictCursor, column_ids: List[int]
    ) -> List[RealDictRow]:
        """
        Get columns for validation (includes table_id)

        Args:
            cursor: Database cursor
            column_ids: List of column IDs (integers)

        Returns:
            List of column records with table_id
        """
        cursor.execute(
            """
            SELECT id, name, data_type, table_id, is_nullable
            FROM columns
            WHERE id = ANY(%s::uuid[])
        """,
            (column_ids,),
        )
        return list(cursor.fetchall())

    @staticmethod
    def create_pk_constraint(
        cursor: RealDictCursor,
        pk_id: Optional[int],
        table_id: int,
        column_ids: List[int],
        constraint_name: Optional[str],
        now: datetime,
    ) -> RealDictRow:
        """
        Create a new primary key constraint

        Args:
            cursor: Database cursor
            pk_id: ID for the new constraint (None for auto-generate)
            table_id: ID of the table (integer)
            column_ids: List of column IDs (integers)
            constraint_name: Optional constraint name
            now: Timestamp for created_at/updated_at

        Returns:
            Created constraint record
        """
        if pk_id is None:
            # Let database auto-generate the ID
            cursor.execute(
                """
                INSERT INTO primary_key_constraints (
                    table_id, column_ids, constraint_name, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
            """,
                (table_id, column_ids, constraint_name, now, now),
            )
        else:
            cursor.execute(
                """
                INSERT INTO primary_key_constraints (
                    id, table_id, column_ids, constraint_name, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
            """,
                (pk_id, table_id, column_ids, constraint_name, now, now),
            )
        result = cursor.fetchone()
        assert result is not None, "INSERT RETURNING returned None"
        return result

    @staticmethod
    def update_pk_constraint(
        cursor: RealDictCursor,
        table_id: int,
        column_ids: List[int],
        constraint_name: Optional[str],
        now: datetime,
    ) -> RealDictRow:
        """
        Update an existing primary key constraint

        Args:
            cursor: Database cursor
            table_id: ID of the table (integer)
            column_ids: List of column IDs (integers)
            constraint_name: Optional constraint name
            now: Timestamp for updated_at

        Returns:
            Updated constraint record
        """
        cursor.execute(
            """
            UPDATE primary_key_constraints
            SET column_ids = %s,
                constraint_name = %s,
                updated_at = %s
            WHERE table_id = %s
            RETURNING *
        """,
            (column_ids, constraint_name, now, table_id),
        )
        result = cursor.fetchone()
        assert result is not None, "UPDATE RETURNING returned None"
        return result

    @staticmethod
    def update_columns_primary_flag(
        cursor: RealDictCursor, table_id: int, column_ids: List[int], now: datetime
    ) -> None:
        """
        Update is_primary flag on columns
        Sets true for specified columns, false for others in the table

        Args:
            cursor: Database cursor
            table_id: ID of the table (integer)
            column_ids: List of column IDs (integers) that should be marked as primary
            now: Timestamp for updated_at
        """
        cursor.execute(
            """
            UPDATE columns
            SET is_primary = CASE
                WHEN id = ANY(%s::uuid[]) THEN true
                ELSE false
            END,
            updated_at = %s
            WHERE table_id = %s
        """,
            (column_ids, now, table_id),
        )

    @staticmethod
    def delete_pk_constraint(cursor: RealDictCursor, table_id: int) -> None:
        """
        Delete primary key constraint for a table

        Args:
            cursor: Database cursor
            table_id: ID of the table (integer)
        """
        cursor.execute(
            """
            DELETE FROM primary_key_constraints WHERE table_id = %s
        """,
            (table_id,),
        )

    @staticmethod
    def clear_all_primary_flags(cursor: RealDictCursor, table_id: int, now: datetime) -> None:
        """
        Set is_primary to false for all columns in a table

        Args:
            cursor: Database cursor
            table_id: ID of the table (integer)
            now: Timestamp for updated_at
        """
        cursor.execute(
            """
            UPDATE columns
            SET is_primary = false, updated_at = %s
            WHERE table_id = %s
        """,
            (now, table_id),
        )

    @staticmethod
    def insert_audit_log(
        cursor: RealDictCursor,
        action: str,
        table_id: int,
        old_value: Dict[str, Any],
        new_value: Dict[str, Any],
        user_id: str,
        timestamp: datetime,
    ) -> None:
        """
        Insert an audit log entry for PK operations

        Args:
            cursor: Database cursor
            action: Action type (e.g., 'PK_CREATED', 'PK_UPDATED', 'PK_REMOVED')
            table_id: ID of the table (integer)
            old_value: Previous state
            new_value: New state
            user_id: UUID of the user performing the action
            timestamp: Timestamp of the action
        """
        cursor.execute(
            """
            INSERT INTO migration_audit_log (
                migration_number, action, table_id,
                old_value, new_value, user_id, timestamp
            )
            VALUES ('001', %s, %s, %s, %s, %s, %s)
        """,
            (action, table_id, Json(old_value), Json(new_value), user_id, timestamp),
        )

    @staticmethod
    def get_origin_tables_with_pks(cursor: RealDictCursor, project_id: str) -> List[RealDictRow]:
        """
        Get all origin tables with primary keys

        Args:
            cursor: Database cursor
            project_id: UUID of the project

        Returns:
            List of origin tables with their PK column IDs
        """
        cursor.execute(
            """
            SELECT
                t.id as table_id,
                t.name as table_name,
                pk.column_ids
            FROM tables t
            JOIN primary_key_constraints pk ON pk.table_id = t.id
            WHERE t.project_id = %s AND t.type = 'origin'
        """,
            (project_id,),
        )
        return list(cursor.fetchall())

    @staticmethod
    def count_column_mappings(
        cursor: RealDictCursor, project_id: str, table_name: str, column_name: str
    ) -> int:
        """
        Count mappings for a specific column

        Args:
            cursor: Database cursor
            project_id: UUID of the project
            table_name: Name of the origin table
            column_name: Name of the origin column

        Returns:
            Count of mappings
        """
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM mappings
            WHERE project_id = %s
              AND origin_table = %s
              AND origin_column = %s
        """,
            (project_id, table_name, column_name),
        )
        result = cursor.fetchone()
        return int(result["count"]) if result else 0

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
