# backend/app/crud/schemas_crud.py
"""
CRUD operations for tables and columns (schemas)
Pure database operations without business logic
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from psycopg2.extras import RealDictCursor


def create_table(
    db, project_id: str, name: str, type: str, user_id: str, encryption_key: Optional[bytes] = None
) -> Dict[str, Any]:
    """
    Create a new table

    Args:
        db: Database connection
        project_id: Project ID
        name: Table name
        type: Table type ('origin' or 'destination')
        user_id: User ID creating the table
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Created table as dict

    Raises:
        HTTPException 409: If table already exists
        HTTPException 403: If project requires encryption but no key provided
    """
    from app.crud import master_key_crud

    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        table_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Check if project has encryption enabled
        config = master_key_crud.get_project_encryption(db, project_id)

        # ✅ VALIDACIÓN ESTRICTA: Rechazar si proyecto requiere encriptación pero no hay clave
        if config and config["encryption_enabled"] and not encryption_key:
            raise HTTPException(
                status_code=403,
                detail="El proyecto requiere encriptación. Por favor, desbloquea el proyecto antes de crear tablas.",
            )

        # ✅ VALIDACIÓN DE DUPLICADOS: Verificar si la tabla ya existe
        if config and config["encryption_enabled"] and encryption_key:
            # Para proyectos encriptados, cargar y desencriptar todas las tablas del tipo
            existing_tables = get_tables_by_project(db, project_id, type, encryption_key)
            if any(t.get("name") == name for t in existing_tables):
                raise HTTPException(
                    status_code=409, detail=f"La tabla '{name}' ({type}) ya existe en este proyecto"
                )
        else:
            # Para proyectos sin encriptación, consultar directamente
            cursor.execute(
                """
                SELECT 1 FROM tables
                WHERE project_id = %s AND name = %s AND type = %s
                LIMIT 1
            """,
                (project_id, name, type),
            )
            if cursor.fetchone():
                raise HTTPException(
                    status_code=409, detail=f"La tabla '{name}' ({type}) ya existe en este proyecto"
                )

        if config and config["encryption_enabled"] and encryption_key:
            # Encrypt table name
            name_encrypted, name_nonce = master_key_crud.encrypt_table_name(name, encryption_key)

            # Insert with encrypted data
            cursor.execute(
                """
                INSERT INTO tables (
                    id, project_id, name_encrypted, name_nonce,
                    is_encrypted, type, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, TRUE, %s, %s, %s)
                RETURNING *
            """,
                (table_id, project_id, name_encrypted, name_nonce, type, now, now),
            )
        else:
            # Insert without encryption (legacy or no session)
            cursor.execute(
                """
                INSERT INTO tables (id, project_id, name, type, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
            """,
                (table_id, project_id, name, type, now, now),
            )

        result = cursor.fetchone()
        db.commit()

        # If encrypted, add decrypted name to result for immediate use
        result_dict = dict(result)
        if result_dict.get("is_encrypted"):
            result_dict["name"] = name  # Already have the plaintext

        return result_dict
    finally:
        cursor.close()


def update_table(
    db, table_id: str, name: str, user_id: str, encryption_key: Optional[bytes] = None
) -> Optional[Dict[str, Any]]:
    """
    Update a table's name

    Args:
        db: Database connection
        table_id: Table ID to update
        name: New table name
        user_id: User ID performing the update
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Updated table as dict

    Raises:
        psycopg2.errors.UniqueViolation: If new name conflicts
    """
    from app.crud import master_key_crud

    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Get table's encryption status
        cursor.execute(
            """
            SELECT is_encrypted
            FROM tables
            WHERE id = %s
        """,
            (table_id,),
        )
        table_info = cursor.fetchone()

        if not table_info:
            return None

        is_encrypted = table_info.get("is_encrypted", False)

        if is_encrypted and encryption_key:
            # Encrypt new name
            name_encrypted, name_nonce = master_key_crud.encrypt_table_name(name, encryption_key)

            # Update with encrypted data
            cursor.execute(
                """
                UPDATE tables
                SET name_encrypted = %s, name_nonce = %s, updated_at = %s
                WHERE id = %s
                RETURNING *
            """,
                (name_encrypted, name_nonce, now, table_id),
            )
        else:
            # Update without encryption (legacy or no session)
            cursor.execute(
                """
                UPDATE tables
                SET name = %s, updated_at = %s
                WHERE id = %s
                RETURNING *
            """,
                (name, now, table_id),
            )

        result = cursor.fetchone()
        db.commit()

        # If encrypted, add decrypted name to result
        result_dict = dict(result) if result else None
        if result_dict and result_dict.get("is_encrypted"):
            result_dict["name"] = name  # Already have the plaintext

        return result_dict
    finally:
        cursor.close()


def delete_table(
    db, table_id: str, user_id: str
) -> Tuple[Optional[Dict[str, Any]], List[str], int]:
    """
    Delete a table and all its columns and related mappings

    Args:
        db: Database connection
        table_id: Table ID to delete
        user_id: User ID performing the deletion

    Returns:
        Tuple of (deleted_table_info, column_names, mappings_deleted_count)
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Get table info first
        cursor.execute(
            """
            SELECT id, project_id, name, type
            FROM tables
            WHERE id = %s
        """,
            (table_id,),
        )
        table = cursor.fetchone()

        if not table:
            return None, [], 0

        table_dict = dict(table)
        table_name = table_dict["name"]
        table_type = table_dict["type"]
        project_id = table_dict["project_id"]

        # Get column names
        cursor.execute(
            """
            SELECT name FROM columns WHERE table_id = %s
        """,
            (table_id,),
        )
        column_names = [row["name"] for row in cursor.fetchall()]

        # Delete related mappings
        mappings_deleted = 0
        if column_names:
            if table_type == "origin":
                cursor.execute(
                    """
                    DELETE FROM mappings
                    WHERE project_id = %s
                      AND origin_table = %s
                      AND origin_column = ANY(%s)
                """,
                    (project_id, table_name, column_names),
                )
            else:
                cursor.execute(
                    """
                    DELETE FROM mappings
                    WHERE project_id = %s
                      AND destination_table = %s
                      AND destination_column = ANY(%s)
                """,
                    (project_id, table_name, column_names),
                )
            mappings_deleted = cursor.rowcount or 0

        # Delete columns
        cursor.execute("DELETE FROM columns WHERE table_id = %s", (table_id,))

        # Delete table
        cursor.execute("DELETE FROM tables WHERE id = %s", (table_id,))

        db.commit()
        return table_dict, column_names, mappings_deleted
    finally:
        cursor.close()


def get_table_by_id(
    db, table_id: str, passphrase: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get a table by its ID

    Args:
        db: Database connection
        table_id: Table ID
        passphrase: Optional passphrase for decryption

    Returns:
        Table dict with decrypted data if passphrase provided
    """
    from app.crud import master_key_crud
    from app.services.encryption_service import EncryptionService

    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT id, project_id, name, type, created_at, updated_at,
                   name_encrypted, name_nonce, is_encrypted
            FROM tables
            WHERE id = %s
        """,
            (table_id,),
        )

        result = cursor.fetchone()
        if not result:
            return None

        result_dict = dict(result)

        # Decrypt if encrypted and passphrase provided
        if result_dict.get("is_encrypted") and passphrase:
            encryption_key = EncryptionService.get_encryption_key(
                db, result_dict["project_id"], passphrase
            )

            if (
                encryption_key
                and result_dict.get("name_encrypted")
                and result_dict.get("name_nonce")
            ):
                try:
                    result_dict["name"] = master_key_crud.decrypt_table_name(
                        result_dict["name_encrypted"], result_dict["name_nonce"], encryption_key
                    )
                except Exception:
                    # If decryption fails, keep encrypted data
                    pass

        return result_dict
    finally:
        cursor.close()


def get_table_by_name(db, project_id: str, name: str, type: str) -> Optional[Dict[str, Any]]:
    """Get a table by project, name and type"""
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT id, project_id, name, type, created_at, updated_at
            FROM tables
            WHERE project_id = %s AND name = %s AND type = %s
        """,
            (project_id, name, type),
        )

        result = cursor.fetchone()
        return dict(result) if result else None
    finally:
        cursor.close()


def check_table_limits(db, project_id: str) -> Tuple[bool, int, int]:
    """
    Check if project can add more tables based on plan limits

    Returns:
        Tuple of (has_pro, current_count, max_allowed)
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Check if has Pro plan
        cursor.execute(
            """
            SELECT 1
            FROM subscriptions
            WHERE project_id = %s
              AND LOWER(status) IN ('active','trialing')
              AND plan_id = 'pro'
            LIMIT 1
        """,
            (project_id,),
        )
        has_pro = bool(cursor.fetchone())

        # Get current table count
        cursor.execute(
            """
            SELECT COUNT(*) AS c
            FROM tables
            WHERE project_id = %s
        """,
            (project_id,),
        )
        row = cursor.fetchone()
        current_count = int(row["c"] if row else 0)

        max_allowed = 140 if has_pro else 20

        return has_pro, current_count, max_allowed
    finally:
        cursor.close()


def create_column(
    db,
    table_id: str,
    name: str,
    data_type: str,
    table_type: str,
    is_nullable: bool,
    is_primary: bool,
    is_autogenerated: bool,
    user_id: str,
    encryption_key: Optional[bytes] = None,
) -> Dict[str, Any]:
    """
    Create a new column

    Args:
        db: Database connection
        table_id: Table ID
        name: Column name
        data_type: Data type (TEXT, INTEGER, etc.)
        table_type: Table type ('origin' or 'destination')
        is_nullable: Whether column can be null
        is_primary: Whether column is primary key
        is_autogenerated: Whether column is autogenerated (destination only)
        user_id: User ID creating the column
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Created column as dict

    Raises:
        psycopg2.errors.UniqueViolation: If column already exists
    """
    from app.crud import master_key_crud

    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        column_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Force is_autogenerated to False for origin tables
        if table_type == "origin":
            is_autogenerated = False

        # Get table's project_id to check encryption config
        cursor.execute("SELECT project_id FROM tables WHERE id = %s", (table_id,))
        table_row = cursor.fetchone()

        if not table_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Table {table_id} not found"
            )

        project_id = table_row["project_id"]

        # Check if project has encryption enabled
        config = master_key_crud.get_project_encryption(db, project_id)

        # ✅ VALIDACIÓN ESTRICTA: Rechazar si proyecto requiere encriptación pero no hay clave
        if config and config["encryption_enabled"] and not encryption_key:
            raise HTTPException(
                status_code=403,
                detail="El proyecto requiere encriptación. Por favor, desbloquea el proyecto antes de crear columnas.",
            )

        if config and config["encryption_enabled"] and encryption_key:
            # Encrypt column name and data type
            name_encrypted, name_nonce = master_key_crud.encrypt_column_name(name, encryption_key)
            data_type_encrypted, data_type_nonce = master_key_crud.encrypt_column_type(
                data_type, encryption_key
            )

            # Insert with encrypted data
            cursor.execute(
                """
                INSERT INTO columns (
                    id, table_id, name_encrypted, name_nonce,
                    data_type_encrypted, data_type_nonce,
                    is_encrypted, table_type,
                    is_nullable, is_primary, is_autogenerated,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """,
                (
                    column_id,
                    table_id,
                    name_encrypted,
                    name_nonce,
                    data_type_encrypted,
                    data_type_nonce,
                    table_type,
                    is_nullable,
                    is_primary,
                    is_autogenerated,
                    now,
                    now,
                ),
            )
        else:
            # Insert without encryption (legacy or no session)
            cursor.execute(
                """
                INSERT INTO columns (
                    id, table_id, name, data_type, table_type,
                    is_nullable, is_primary, is_autogenerated,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """,
                (
                    column_id,
                    table_id,
                    name,
                    data_type,
                    table_type,
                    is_nullable,
                    is_primary,
                    is_autogenerated,
                    now,
                    now,
                ),
            )

        result = cursor.fetchone()
        db.commit()

        # If encrypted, add decrypted name and data_type to result for immediate use
        result_dict = dict(result)
        if result_dict.get("is_encrypted"):
            result_dict["name"] = name  # Already have the plaintext
            result_dict["data_type"] = data_type

        return result_dict
    finally:
        cursor.close()


def update_column(
    db,
    column_id: str,
    name: str,
    data_type: str,
    table_type: str,
    is_nullable: bool,
    is_primary: bool,
    is_autogenerated: bool,
    user_id: str,
    encryption_key: Optional[bytes] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], int]:
    """
    Update a column and rename related mappings if name changed

    Args:
        db: Database connection
        column_id: Column ID to update
        name: New column name
        data_type: New data type
        table_type: Table type
        is_nullable: Whether column can be null
        is_primary: Whether column is primary key
        is_autogenerated: Whether column is autogenerated
        user_id: User ID performing the update
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Tuple of (old_column_data, new_column_data, mappings_renamed_count)
    """
    from app.crud import master_key_crud

    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Get current column data
        cursor.execute(
            """
            SELECT c.*, t.name as table_name, t.project_id
            FROM columns c
            JOIN tables t ON c.table_id = t.id
            WHERE c.id = %s
        """,
            (column_id,),
        )
        old_column = cursor.fetchone()

        if not old_column:
            return None, None, 0

        old_column_dict = dict(old_column)
        is_encrypted = old_column_dict.get("is_encrypted", False)

        # Decrypt old name if encrypted
        if is_encrypted and encryption_key:
            if old_column_dict.get("name_encrypted") and old_column_dict.get("name_nonce"):
                old_name = master_key_crud.decrypt_column_name(
                    old_column_dict["name_encrypted"], old_column_dict["name_nonce"], encryption_key
                )
            else:
                old_name = old_column_dict.get("name", "")
        else:
            old_name = old_column_dict.get("name", "")

        table_name = old_column_dict["table_name"]
        project_id = old_column_dict["project_id"]

        # Force is_autogenerated to False for origin tables
        if table_type == "origin":
            is_autogenerated = False

        # Update column
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if is_encrypted and encryption_key:
            # Encrypt new name and data type
            name_encrypted, name_nonce = master_key_crud.encrypt_column_name(name, encryption_key)
            data_type_encrypted, data_type_nonce = master_key_crud.encrypt_column_type(
                data_type, encryption_key
            )

            # Update with encrypted data
            cursor.execute(
                """
                UPDATE columns
                SET name_encrypted = %s, name_nonce = %s,
                    data_type_encrypted = %s, data_type_nonce = %s,
                    is_nullable = %s, is_primary = %s, is_autogenerated = %s,
                    updated_at = %s
                WHERE id = %s
                RETURNING *
            """,
                (
                    name_encrypted,
                    name_nonce,
                    data_type_encrypted,
                    data_type_nonce,
                    is_nullable,
                    is_primary,
                    is_autogenerated,
                    now,
                    column_id,
                ),
            )
        else:
            # Update without encryption (legacy or no session)
            cursor.execute(
                """
                UPDATE columns
                SET name = %s, data_type = %s, is_nullable = %s,
                    is_primary = %s, is_autogenerated = %s, updated_at = %s
                WHERE id = %s
                RETURNING *
            """,
                (name, data_type, is_nullable, is_primary, is_autogenerated, now, column_id),
            )

        new_column = cursor.fetchone()
        new_column_dict = dict(new_column) if new_column else None

        # Add table info to new_column_dict
        if new_column_dict:
            new_column_dict["table_name"] = table_name
            new_column_dict["project_id"] = project_id
            new_column_dict["table_type"] = table_type

            # If encrypted, add decrypted values
            if new_column_dict.get("is_encrypted"):
                new_column_dict["name"] = name
                new_column_dict["data_type"] = data_type

        # Rename mappings if name changed
        mappings_renamed = 0
        if name != old_name:
            if table_type == "origin":
                cursor.execute(
                    """
                    UPDATE mappings
                    SET origin_column = %s
                    WHERE project_id = %s
                      AND origin_table = %s
                      AND origin_column = %s
                """,
                    (name, project_id, table_name, old_name),
                )
            else:
                cursor.execute(
                    """
                    UPDATE mappings
                    SET destination_column = %s
                    WHERE project_id = %s
                      AND destination_table = %s
                      AND destination_column = %s
                """,
                    (name, project_id, table_name, old_name),
                )
            mappings_renamed = cursor.rowcount or 0

        db.commit()
        return old_column_dict, new_column_dict, mappings_renamed
    finally:
        cursor.close()


def delete_column(db, column_id: str, user_id: str) -> Tuple[Optional[Dict[str, Any]], int]:
    """
    Delete a column and its related mappings

    Args:
        db: Database connection
        column_id: Column ID to delete
        user_id: User ID performing the deletion

    Returns:
        Tuple of (deleted_column_info, mappings_deleted_count)
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Get column info
        cursor.execute(
            """
            SELECT c.*, t.name as table_name, t.project_id, t.type as table_type
            FROM columns c
            JOIN tables t ON c.table_id = t.id
            WHERE c.id = %s
        """,
            (column_id,),
        )
        column = cursor.fetchone()

        if not column:
            return None, 0

        column_dict = dict(column)
        column_name = column_dict["name"]
        table_name = column_dict["table_name"]
        table_type = column_dict["table_type"]
        project_id = column_dict["project_id"]

        # Delete related mappings
        mappings_deleted = 0
        if table_type == "origin":
            cursor.execute(
                """
                DELETE FROM mappings
                WHERE project_id = %s
                  AND origin_table = %s
                  AND origin_column = %s
            """,
                (project_id, table_name, column_name),
            )
            mappings_deleted = cursor.rowcount or 0
        elif table_type == "destination":
            cursor.execute(
                """
                DELETE FROM mappings
                WHERE project_id = %s
                  AND destination_table = %s
                  AND destination_column = %s
            """,
                (project_id, table_name, column_name),
            )
            mappings_deleted = cursor.rowcount or 0

        # Delete column
        cursor.execute("DELETE FROM columns WHERE id = %s", (column_id,))

        db.commit()
        return column_dict, mappings_deleted
    finally:
        cursor.close()


def get_column_by_id(
    db, column_id: str, encryption_key: Optional[bytes] = None
) -> Optional[Dict[str, Any]]:
    """
    Get a column by its ID with table info

    Args:
        db: Database connection
        column_id: Column ID
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Column dict with decrypted data if encryption_key provided
    """
    from app.crud import master_key_crud

    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT c.*, t.name as table_name, t.type as table_type, t.project_id
            FROM columns c
            JOIN tables t ON c.table_id = t.id
            WHERE c.id = %s
        """,
            (column_id,),
        )

        result = cursor.fetchone()
        if not result:
            return None

        result_dict = dict(result)

        # Decrypt if encrypted and encryption_key provided
        if result_dict.get("is_encrypted") and encryption_key:
            try:
                if result_dict.get("name_encrypted") and result_dict.get("name_nonce"):
                    result_dict["name"] = master_key_crud.decrypt_column_name(
                        result_dict["name_encrypted"], result_dict["name_nonce"], encryption_key
                    )
                if result_dict.get("data_type_encrypted") and result_dict.get("data_type_nonce"):
                    result_dict["data_type"] = master_key_crud.decrypt_column_type(
                        result_dict["data_type_encrypted"],
                        result_dict["data_type_nonce"],
                        encryption_key,
                    )
            except Exception:
                # If decryption fails, leave encrypted (column might be inaccessible)
                pass

        return result_dict
    finally:
        cursor.close()


def check_column_limits(db, table_id: str) -> Tuple[bool, int, int]:
    """
    Check if table can add more columns based on plan limits

    Returns:
        Tuple of (has_pro, current_count, max_allowed)
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Get project_id from table
        cursor.execute(
            """
            SELECT project_id FROM tables WHERE id = %s
        """,
            (table_id,),
        )
        table = cursor.fetchone()

        if not table:
            return False, 0, 0

        project_id = table["project_id"]

        # Check if has Pro plan
        cursor.execute(
            """
            SELECT 1
            FROM subscriptions
            WHERE project_id = %s
              AND LOWER(status) IN ('active','trialing')
              AND plan_id = 'pro'
            LIMIT 1
        """,
            (project_id,),
        )
        has_pro = bool(cursor.fetchone())

        # Get current column count for this table
        cursor.execute(
            """
            SELECT COUNT(*) AS c
            FROM columns
            WHERE table_id = %s
        """,
            (table_id,),
        )
        row = cursor.fetchone()
        current_count = int(row["c"] if row else 0)

        max_allowed = 200 if has_pro else 60

        return has_pro, current_count, max_allowed
    finally:
        cursor.close()


def get_tables_by_project(
    db, project_id: str, table_type: str, encryption_key: Optional[bytes] = None
) -> List[Dict[str, Any]]:
    """
    Get all tables for a project filtered by type

    Args:
        db: Database connection
        project_id: Project ID
        table_type: Table type ('origin' or 'destination')
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        List of table dicts with decrypted data if encryption_key provided
    """
    from app.crud import master_key_crud

    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT id, project_id, name, type, created_at, updated_at,
                   name_encrypted, name_nonce, is_encrypted
            FROM tables
            WHERE project_id = %s AND type = %s
            ORDER BY created_at
        """,
            (project_id, table_type),
        )

        results = cursor.fetchall()
        tables = []

        for result in results:
            result_dict = dict(result)

            # Decrypt if encrypted and encryption_key provided
            if result_dict.get("is_encrypted") and encryption_key:
                if result_dict.get("name_encrypted") and result_dict.get("name_nonce"):
                    try:
                        result_dict["name"] = master_key_crud.decrypt_table_name(
                            result_dict["name_encrypted"], result_dict["name_nonce"], encryption_key
                        )
                    except Exception:
                        # If decryption fails, skip this table or keep encrypted
                        pass

            tables.append(result_dict)

        return tables
    finally:
        cursor.close()


def get_columns_by_table(
    db, table_id: str, encryption_key: Optional[bytes] = None
) -> List[Dict[str, Any]]:
    """
    Get all columns for a table

    Args:
        db: Database connection
        table_id: Table ID
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        List of column dicts with decrypted data if encryption_key provided
    """
    from app.crud import master_key_crud

    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT c.*, t.name as table_name, t.type as table_type, t.project_id
            FROM columns c
            JOIN tables t ON c.table_id = t.id
            WHERE c.table_id = %s
            ORDER BY c.created_at
        """,
            (table_id,),
        )

        results = cursor.fetchall()
        columns = []

        for result in results:
            result_dict = dict(result)

            # Decrypt if encrypted and encryption_key provided
            if result_dict.get("is_encrypted") and encryption_key:
                try:
                    if result_dict.get("name_encrypted") and result_dict.get("name_nonce"):
                        result_dict["name"] = master_key_crud.decrypt_column_name(
                            result_dict["name_encrypted"], result_dict["name_nonce"], encryption_key
                        )
                    if result_dict.get("data_type_encrypted") and result_dict.get(
                        "data_type_nonce"
                    ):
                        result_dict["data_type"] = master_key_crud.decrypt_column_type(
                            result_dict["data_type_encrypted"],
                            result_dict["data_type_nonce"],
                            encryption_key,
                        )
                except Exception:
                    # If decryption fails, skip or keep encrypted
                    pass

            columns.append(result_dict)

        return columns
    finally:
        cursor.close()


# ========================================================================
# SQLALCHEMY ORM VERSIONS - Funciones con sufijo _orm
# ========================================================================


def create_table_orm(
    db, project_id: str, name: str, type: str, user_id: str, encryption_key: Optional[bytes] = None
) -> Dict[str, Any]:
    """
    Create a new table (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: Project ID
        name: Table name
        type: Table type ('origin' or 'destination')
        user_id: User ID creating the table
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Created table as dict

    Raises:
        HTTPException 409: If table already exists
        HTTPException 403: If project requires encryption but no key provided
    """
    from app.crud import master_key_crud
    from app.models.orm import ProjectEncryption, Table

    try:
        # 1. Verificar configuración de encriptación
        config_obj = (
            db.query(ProjectEncryption).filter(ProjectEncryption.project_id == project_id).first()
        )

        config = None
        if config_obj:
            config = {
                "encryption_enabled": config_obj.encryption_enabled,
                "project_id": str(config_obj.project_id),
            }

        # 2. VALIDACIÓN ESTRICTA - CRÍTICO
        if config and config["encryption_enabled"] and not encryption_key:
            raise HTTPException(
                status_code=403,
                detail="El proyecto requiere encriptación. Por favor, desbloquea el proyecto antes de crear tablas.",
            )

        # 3. Validar duplicados (para encriptados, cargar TODOS y descifrar)
        if config and config["encryption_enabled"] and encryption_key:
            existing = get_tables_by_project_orm(db, project_id, type, encryption_key)
            if any(t.get("name") == name for t in existing):
                raise HTTPException(
                    status_code=409, detail=f"La tabla '{name}' ({type}) ya existe en este proyecto"
                )
        else:
            # Sin encriptación - buscar directo
            existing = (
                db.query(Table)
                .filter(Table.project_id == project_id, Table.name == name, Table.type == type)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=409, detail=f"La tabla '{name}' ({type}) ya existe en este proyecto"
                )

        # 4. Crear tabla
        table_id = uuid.uuid4()
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if config and config["encryption_enabled"] and encryption_key:
            # CIFRAR usando helper EXACTO
            name_encrypted, name_nonce = master_key_crud.encrypt_table_name(name, encryption_key)

            new_table = Table(
                id=table_id,
                project_id=project_id,
                name=None,  # NULL cuando está encriptado
                name_encrypted=name_encrypted,
                name_nonce=name_nonce,
                is_encrypted=True,
                type=type,
                created_at=now,
                updated_at=now,
            )
        else:
            new_table = Table(
                id=table_id,
                project_id=project_id,
                name=name,
                type=type,
                is_encrypted=False,
                created_at=now,
                updated_at=now,
            )

        db.add(new_table)
        db.commit()
        db.refresh(new_table)

        # 5. Convertir a dict
        result_dict = {
            "id": str(new_table.id),
            "project_id": str(new_table.project_id),
            "name": new_table.name,
            "type": new_table.type,
            "is_encrypted": new_table.is_encrypted,
            "name_encrypted": new_table.name_encrypted,
            "name_nonce": new_table.name_nonce,
            "created_at": new_table.created_at,
            "updated_at": new_table.updated_at,
        }

        # 6. CRÍTICO: Agregar plaintext para uso inmediato
        if result_dict.get("is_encrypted"):
            result_dict["name"] = name

        return result_dict

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise


def get_tables_by_project_orm(
    db, project_id: str, table_type: str, encryption_key: Optional[bytes] = None
) -> List[Dict[str, Any]]:
    """
    Get all tables for a project filtered by type (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: Project ID
        table_type: Table type ('origin' or 'destination')
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        List of table dicts with decrypted data if encryption_key provided
    """
    from app.crud import master_key_crud
    from app.models.orm import Table

    try:
        tables = (
            db.query(Table)
            .filter(Table.project_id == project_id, Table.type == table_type)
            .order_by(Table.created_at)
            .all()
        )

        results = []
        for table in tables:
            table_dict = {
                "id": str(table.id),
                "project_id": str(table.project_id),
                "name": table.name,
                "name_encrypted": table.name_encrypted,
                "name_nonce": table.name_nonce,
                "type": table.type,
                "is_encrypted": table.is_encrypted,
                "created_at": table.created_at,
                "updated_at": table.updated_at,
            }

            # Descifrar si es necesario
            if table.is_encrypted and encryption_key:
                if table.name_encrypted and table.name_nonce:
                    try:
                        decrypted_name = master_key_crud.decrypt_table_name(
                            table.name_encrypted, table.name_nonce, encryption_key
                        )
                        table_dict["name"] = decrypted_name
                    except Exception:
                        # No pudo descifrar
                        table_dict["name"] = None

            results.append(table_dict)

        return results

    except Exception as e:
        raise


def update_table_orm(
    db, table_id: str, name: str, user_id: str, encryption_key: Optional[bytes] = None
) -> Optional[Dict[str, Any]]:
    """
    Update a table's name (ORM version)

    Args:
        db: SQLAlchemy Session
        table_id: Table ID to update
        name: New table name
        user_id: User ID performing the update
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Updated table as dict or None if not found
    """
    from app.crud import master_key_crud
    from app.models.orm import Table

    try:
        # Get table
        table = db.query(Table).filter(Table.id == table_id).first()
        if not table:
            return None

        is_encrypted = table.is_encrypted
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if is_encrypted and encryption_key:
            # Encrypt new name
            name_encrypted, name_nonce = master_key_crud.encrypt_table_name(name, encryption_key)

            # Update with encrypted data
            table.name_encrypted = name_encrypted
            table.name_nonce = name_nonce
            table.updated_at = now
        else:
            # Update without encryption (legacy or no session)
            table.name = name
            table.updated_at = now

        db.commit()
        db.refresh(table)

        # Convert to dict
        result_dict = {
            "id": str(table.id),
            "project_id": str(table.project_id),
            "name": table.name,
            "type": table.type,
            "is_encrypted": table.is_encrypted,
            "name_encrypted": table.name_encrypted,
            "name_nonce": table.name_nonce,
            "created_at": table.created_at,
            "updated_at": table.updated_at,
        }

        # If encrypted, add decrypted name to result
        if result_dict.get("is_encrypted"):
            result_dict["name"] = name

        return result_dict

    except Exception as e:
        db.rollback()
        raise


def delete_table_orm(
    db, table_id: str, user_id: str
) -> Tuple[Optional[Dict[str, Any]], List[str], int]:
    """
    Delete a table and all its columns and related mappings (ORM version)

    Args:
        db: SQLAlchemy Session
        table_id: Table ID to delete
        user_id: User ID performing the deletion

    Returns:
        Tuple of (deleted_table_info, column_names, mappings_deleted_count)
    """
    from app.models.orm import Mapping, Table, TableColumn

    try:
        # Get table info first
        table = db.query(Table).filter(Table.id == table_id).first()
        if not table:
            return None, [], 0

        table_dict = {
            "id": str(table.id),
            "project_id": str(table.project_id),
            "name": table.name,
            "type": table.type,
        }
        table_name = table.name
        table_type = table.type
        project_id = str(table.project_id)

        # Get column names
        columns = db.query(TableColumn).filter(TableColumn.table_id == table_id).all()
        column_names = [col.name for col in columns if col.name]

        # Delete related mappings
        mappings_deleted = 0
        if column_names:
            if table_type == "origin":
                mappings_deleted = (
                    db.query(Mapping)
                    .filter(
                        Mapping.project_id == project_id,
                        Mapping.origin_table == table_name,
                        Mapping.origin_column.in_(column_names),
                    )
                    .delete(synchronize_session=False)
                )
            else:
                mappings_deleted = (
                    db.query(Mapping)
                    .filter(
                        Mapping.project_id == project_id,
                        Mapping.destination_table == table_name,
                        Mapping.destination_column.in_(column_names),
                    )
                    .delete(synchronize_session=False)
                )

        # Delete columns (will cascade from table delete if configured, but explicit is better)
        db.query(TableColumn).filter(TableColumn.table_id == table_id).delete()

        # Delete table
        db.query(Table).filter(Table.id == table_id).delete()

        db.commit()
        return table_dict, column_names, mappings_deleted

    except Exception as e:
        db.rollback()
        raise


def get_table_by_id_orm(
    db, table_id: str, passphrase: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get a table by its ID (ORM version)

    Args:
        db: SQLAlchemy Session
        table_id: Table ID
        passphrase: Optional passphrase for decryption

    Returns:
        Table dict with decrypted data if passphrase provided
    """
    from app.crud import master_key_crud
    from app.models.orm import Table
    from app.services.encryption_service import EncryptionService

    try:
        table = db.query(Table).filter(Table.id == table_id).first()
        if not table:
            return None

        result_dict = {
            "id": str(table.id),
            "project_id": str(table.project_id),
            "name": table.name,
            "type": table.type,
            "created_at": table.created_at,
            "updated_at": table.updated_at,
            "name_encrypted": table.name_encrypted,
            "name_nonce": table.name_nonce,
            "is_encrypted": table.is_encrypted,
        }

        # Decrypt if encrypted and passphrase provided
        if result_dict.get("is_encrypted") and passphrase:
            encryption_key = EncryptionService.get_encryption_key(
                db, result_dict["project_id"], passphrase
            )

            if (
                encryption_key
                and result_dict.get("name_encrypted")
                and result_dict.get("name_nonce")
            ):
                try:
                    result_dict["name"] = master_key_crud.decrypt_table_name(
                        result_dict["name_encrypted"], result_dict["name_nonce"], encryption_key
                    )
                except Exception:
                    # If decryption fails, keep encrypted data
                    pass

        return result_dict

    except Exception as e:
        raise


def get_table_by_name_orm(db, project_id: str, name: str, type: str) -> Optional[Dict[str, Any]]:
    """
    Get a table by project, name and type (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: Project ID
        name: Table name
        type: Table type

    Returns:
        Table dict or None if not found
    """
    from app.models.orm import Table

    try:
        table = (
            db.query(Table)
            .filter(Table.project_id == project_id, Table.name == name, Table.type == type)
            .first()
        )

        if not table:
            return None

        return {
            "id": str(table.id),
            "project_id": str(table.project_id),
            "name": table.name,
            "type": table.type,
            "created_at": table.created_at,
            "updated_at": table.updated_at,
        }

    except Exception as e:
        raise


def check_table_limits_orm(db, project_id: str) -> Tuple[bool, int, int]:
    """
    Check if project can add more tables based on plan limits (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: Project ID

    Returns:
        Tuple of (has_pro, current_count, max_allowed)
    """
    from sqlalchemy import and_, func

    from app.models.orm import Subscription, Table

    try:
        # Check if has Pro plan
        has_pro_query = (
            db.query(Subscription)
            .filter(
                Subscription.project_id == project_id,
                func.lower(Subscription.status).in_(["active", "trialing"]),
                Subscription.plan_id == "pro",
            )
            .first()
        )
        has_pro = bool(has_pro_query)

        # Get current table count
        current_count = (
            db.query(func.count(Table.id)).filter(Table.project_id == project_id).scalar() or 0
        )

        max_allowed = 140 if has_pro else 20

        return has_pro, current_count, max_allowed

    except Exception as e:
        raise


def create_column_orm(
    db,
    table_id: str,
    name: str,
    data_type: str,
    table_type: str,
    is_nullable: bool,
    is_primary: bool,
    is_autogenerated: bool,
    user_id: str,
    encryption_key: Optional[bytes] = None,
) -> Dict[str, Any]:
    """
    Create a new column (ORM version)

    Args:
        db: SQLAlchemy Session
        table_id: Table ID
        name: Column name
        data_type: Data type (TEXT, INTEGER, etc.)
        table_type: Table type ('origin' or 'destination')
        is_nullable: Whether column can be null
        is_primary: Whether column is primary key
        is_autogenerated: Whether column is autogenerated (destination only)
        user_id: User ID creating the column
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Created column as dict

    Raises:
        HTTPException 404: If table not found
        HTTPException 403: If project requires encryption but no key provided
    """
    from app.crud import master_key_crud
    from app.models.orm import ProjectEncryption, Table, TableColumn

    try:
        # Force is_autogenerated to False for origin tables
        if table_type == "origin":
            is_autogenerated = False

        # Get table's project_id to check encryption config
        table = db.query(Table).filter(Table.id == table_id).first()
        if not table:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Table {table_id} not found"
            )

        project_id = str(table.project_id)

        # Check if project has encryption enabled
        config_obj = (
            db.query(ProjectEncryption).filter(ProjectEncryption.project_id == project_id).first()
        )

        config = None
        if config_obj:
            config = {
                "encryption_enabled": config_obj.encryption_enabled,
                "project_id": str(config_obj.project_id),
            }

        # VALIDACIÓN ESTRICTA
        if config and config["encryption_enabled"] and not encryption_key:
            raise HTTPException(
                status_code=403,
                detail="El proyecto requiere encriptación. Por favor, desbloquea el proyecto antes de crear columnas.",
            )

        # Create column
        column_id = uuid.uuid4()
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if config and config["encryption_enabled"] and encryption_key:
            # Encrypt column name and data type
            name_encrypted, name_nonce = master_key_crud.encrypt_column_name(name, encryption_key)
            data_type_encrypted, data_type_nonce = master_key_crud.encrypt_column_type(
                data_type, encryption_key
            )

            new_column = TableColumn(
                id=column_id,
                table_id=table_id,
                name=None,  # NULL cuando está encriptado
                name_encrypted=name_encrypted,
                name_nonce=name_nonce,
                data_type=None,  # NULL cuando está encriptado
                data_type_encrypted=data_type_encrypted,
                data_type_nonce=data_type_nonce,
                is_encrypted=True,
                table_type=table_type,
                is_nullable=is_nullable,
                is_primary=is_primary,
                is_autogenerated=is_autogenerated,
                created_at=now,
                updated_at=now,
            )
        else:
            new_column = TableColumn(
                id=column_id,
                table_id=table_id,
                name=name,
                data_type=data_type,
                table_type=table_type,
                is_encrypted=False,
                is_nullable=is_nullable,
                is_primary=is_primary,
                is_autogenerated=is_autogenerated,
                created_at=now,
                updated_at=now,
            )

        db.add(new_column)
        db.commit()
        db.refresh(new_column)

        # Convert to dict
        result_dict = {
            "id": str(new_column.id),
            "table_id": str(new_column.table_id),
            "name": new_column.name,
            "data_type": new_column.data_type,
            "table_type": new_column.table_type,
            "is_encrypted": new_column.is_encrypted,
            "is_nullable": new_column.is_nullable,
            "is_primary": new_column.is_primary,
            "is_autogenerated": new_column.is_autogenerated,
            "name_encrypted": new_column.name_encrypted,
            "name_nonce": new_column.name_nonce,
            "data_type_encrypted": new_column.data_type_encrypted,
            "data_type_nonce": new_column.data_type_nonce,
            "created_at": new_column.created_at,
            "updated_at": new_column.updated_at,
        }

        # If encrypted, add decrypted values for immediate use
        if result_dict.get("is_encrypted"):
            result_dict["name"] = name
            result_dict["data_type"] = data_type

        return result_dict

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise


def update_column_orm(
    db,
    column_id: str,
    name: str,
    data_type: str,
    table_type: str,
    is_nullable: bool,
    is_primary: bool,
    is_autogenerated: bool,
    user_id: str,
    encryption_key: Optional[bytes] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], int]:
    """
    Update a column and rename related mappings if name changed (ORM version)

    Args:
        db: SQLAlchemy Session
        column_id: Column ID to update
        name: New column name
        data_type: New data type
        table_type: Table type
        is_nullable: Whether column can be null
        is_primary: Whether column is primary key
        is_autogenerated: Whether column is autogenerated
        user_id: User ID performing the update
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Tuple of (old_column_data, new_column_data, mappings_renamed_count)
    """
    from app.crud import master_key_crud
    from app.models.orm import Mapping, Table, TableColumn

    try:
        # Get current column data with table info
        result = (
            db.query(
                TableColumn, Table.name.label("table_name"), Table.project_id.label("project_id")
            )
            .join(Table, TableColumn.table_id == Table.id)
            .filter(TableColumn.id == column_id)
            .first()
        )

        if not result:
            return None, None, 0

        column, table_name, project_id = result

        old_column_dict = {
            "id": str(column.id),
            "table_id": str(column.table_id),
            "name": column.name,
            "data_type": column.data_type,
            "table_type": column.table_type,
            "is_encrypted": column.is_encrypted,
            "is_nullable": column.is_nullable,
            "is_primary": column.is_primary,
            "is_autogenerated": column.is_autogenerated,
            "created_at": column.created_at,
            "updated_at": column.updated_at,
            "table_name": table_name,
            "project_id": str(project_id),
        }

        is_encrypted = column.is_encrypted

        # Decrypt old name if encrypted
        if is_encrypted and encryption_key:
            if column.name_encrypted and column.name_nonce:
                old_name = master_key_crud.decrypt_column_name(
                    column.name_encrypted, column.name_nonce, encryption_key
                )
            else:
                old_name = column.name or ""
        else:
            old_name = column.name or ""

        # Force is_autogenerated to False for origin tables
        if table_type == "origin":
            is_autogenerated = False

        # Update column
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if is_encrypted and encryption_key:
            # Encrypt new name and data type
            name_encrypted, name_nonce = master_key_crud.encrypt_column_name(name, encryption_key)
            data_type_encrypted, data_type_nonce = master_key_crud.encrypt_column_type(
                data_type, encryption_key
            )

            column.name_encrypted = name_encrypted
            column.name_nonce = name_nonce
            column.data_type_encrypted = data_type_encrypted
            column.data_type_nonce = data_type_nonce
            column.is_nullable = is_nullable
            column.is_primary = is_primary
            column.is_autogenerated = is_autogenerated
            column.updated_at = now
        else:
            column.name = name
            column.data_type = data_type
            column.is_nullable = is_nullable
            column.is_primary = is_primary
            column.is_autogenerated = is_autogenerated
            column.updated_at = now

        db.commit()
        db.refresh(column)

        # Prepare new column dict
        new_column_dict = {
            "id": str(column.id),
            "table_id": str(column.table_id),
            "name": column.name,
            "data_type": column.data_type,
            "table_type": column.table_type,
            "is_encrypted": column.is_encrypted,
            "is_nullable": column.is_nullable,
            "is_primary": column.is_primary,
            "is_autogenerated": column.is_autogenerated,
            "created_at": column.created_at,
            "updated_at": column.updated_at,
            "table_name": table_name,
            "project_id": str(project_id),
        }

        # If encrypted, add decrypted values
        if new_column_dict.get("is_encrypted"):
            new_column_dict["name"] = name
            new_column_dict["data_type"] = data_type

        # Rename mappings if name changed
        mappings_renamed = 0
        if name != old_name:
            if table_type == "origin":
                mappings_renamed = (
                    db.query(Mapping)
                    .filter(
                        Mapping.project_id == str(project_id),
                        Mapping.origin_table == table_name,
                        Mapping.origin_column == old_name,
                    )
                    .update({Mapping.origin_column: name}, synchronize_session=False)
                )
            else:
                mappings_renamed = (
                    db.query(Mapping)
                    .filter(
                        Mapping.project_id == str(project_id),
                        Mapping.destination_table == table_name,
                        Mapping.destination_column == old_name,
                    )
                    .update({Mapping.destination_column: name}, synchronize_session=False)
                )
            db.commit()

        return old_column_dict, new_column_dict, mappings_renamed

    except Exception as e:
        db.rollback()
        raise


def delete_column_orm(db, column_id: str, user_id: str) -> Tuple[Optional[Dict[str, Any]], int]:
    """
    Delete a column and its related mappings (ORM version)

    Args:
        db: SQLAlchemy Session
        column_id: Column ID to delete
        user_id: User ID performing the deletion

    Returns:
        Tuple of (deleted_column_info, mappings_deleted_count)
    """
    from app.models.orm import Mapping, Table, TableColumn

    try:
        # Get column info with table info
        result = (
            db.query(
                TableColumn,
                Table.name.label("table_name"),
                Table.project_id.label("project_id"),
                Table.type.label("table_type"),
            )
            .join(Table, TableColumn.table_id == Table.id)
            .filter(TableColumn.id == column_id)
            .first()
        )

        if not result:
            return None, 0

        column, table_name, project_id, table_type = result

        column_dict = {
            "id": str(column.id),
            "table_id": str(column.table_id),
            "name": column.name,
            "data_type": column.data_type,
            "table_type": column.table_type,
            "table_name": table_name,
            "project_id": str(project_id),
        }

        column_name = column.name

        # Delete related mappings
        mappings_deleted = 0
        if table_type == "origin":
            mappings_deleted = (
                db.query(Mapping)
                .filter(
                    Mapping.project_id == str(project_id),
                    Mapping.origin_table == table_name,
                    Mapping.origin_column == column_name,
                )
                .delete(synchronize_session=False)
            )
        elif table_type == "destination":
            mappings_deleted = (
                db.query(Mapping)
                .filter(
                    Mapping.project_id == str(project_id),
                    Mapping.destination_table == table_name,
                    Mapping.destination_column == column_name,
                )
                .delete(synchronize_session=False)
            )

        # Delete column
        db.query(TableColumn).filter(TableColumn.id == column_id).delete()

        db.commit()
        return column_dict, mappings_deleted

    except Exception as e:
        db.rollback()
        raise


def get_column_by_id_orm(
    db, column_id: str, encryption_key: Optional[bytes] = None
) -> Optional[Dict[str, Any]]:
    """
    Get a column by its ID with table info (ORM version)

    Args:
        db: SQLAlchemy Session
        column_id: Column ID
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Column dict with decrypted data if encryption_key provided
    """
    from app.crud import master_key_crud
    from app.models.orm import Table, TableColumn

    try:
        result = (
            db.query(
                TableColumn,
                Table.name.label("table_name"),
                Table.type.label("table_type"),
                Table.project_id.label("project_id"),
            )
            .join(Table, TableColumn.table_id == Table.id)
            .filter(TableColumn.id == column_id)
            .first()
        )

        if not result:
            return None

        column, table_name, table_type, project_id = result

        result_dict = {
            "id": str(column.id),
            "table_id": str(column.table_id),
            "name": column.name,
            "data_type": column.data_type,
            "table_type": column.table_type,
            "is_encrypted": column.is_encrypted,
            "is_nullable": column.is_nullable,
            "is_primary": column.is_primary,
            "is_autogenerated": column.is_autogenerated,
            "created_at": column.created_at,
            "updated_at": column.updated_at,
            "table_name": table_name,
            "project_id": str(project_id),
        }

        # Decrypt if encrypted and encryption_key provided
        if result_dict.get("is_encrypted") and encryption_key:
            try:
                if column.name_encrypted and column.name_nonce:
                    result_dict["name"] = master_key_crud.decrypt_column_name(
                        column.name_encrypted, column.name_nonce, encryption_key
                    )
                if column.data_type_encrypted and column.data_type_nonce:
                    result_dict["data_type"] = master_key_crud.decrypt_column_type(
                        column.data_type_encrypted, column.data_type_nonce, encryption_key
                    )
            except Exception:
                # If decryption fails, leave encrypted
                pass

        return result_dict

    except Exception as e:
        raise


def get_columns_by_table_orm(
    db, table_id: str, encryption_key: Optional[bytes] = None
) -> List[Dict[str, Any]]:
    """
    Get all columns for a table (ORM version)

    Args:
        db: SQLAlchemy Session
        table_id: Table ID
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        List of column dicts with decrypted data if encryption_key provided
    """
    from app.crud import master_key_crud
    from app.models.orm import Table, TableColumn

    try:
        results = (
            db.query(
                TableColumn,
                Table.name.label("table_name"),
                Table.type.label("table_type"),
                Table.project_id.label("project_id"),
            )
            .join(Table, TableColumn.table_id == Table.id)
            .filter(TableColumn.table_id == table_id)
            .order_by(TableColumn.created_at)
            .all()
        )

        columns = []
        for column, table_name, table_type, project_id in results:
            result_dict = {
                "id": str(column.id),
                "table_id": str(column.table_id),
                "name": column.name,
                "data_type": column.data_type,
                "table_type": column.table_type,
                "is_encrypted": column.is_encrypted,
                "is_nullable": column.is_nullable,
                "is_primary": column.is_primary,
                "is_autogenerated": column.is_autogenerated,
                "name_encrypted": column.name_encrypted,
                "name_nonce": column.name_nonce,
                "data_type_encrypted": column.data_type_encrypted,
                "data_type_nonce": column.data_type_nonce,
                "created_at": column.created_at,
                "updated_at": column.updated_at,
                "table_name": table_name,
                "project_id": str(project_id),
            }

            # Decrypt if encrypted and encryption_key provided
            if result_dict.get("is_encrypted") and encryption_key:
                try:
                    if column.name_encrypted and column.name_nonce:
                        result_dict["name"] = master_key_crud.decrypt_column_name(
                            column.name_encrypted, column.name_nonce, encryption_key
                        )
                    if column.data_type_encrypted and column.data_type_nonce:
                        result_dict["data_type"] = master_key_crud.decrypt_column_type(
                            column.data_type_encrypted, column.data_type_nonce, encryption_key
                        )
                except Exception:
                    # If decryption fails, skip or keep encrypted
                    pass

            columns.append(result_dict)

        return columns

    except Exception as e:
        raise


def check_column_limits_orm(db, table_id: str) -> Tuple[bool, int, int]:
    """
    Check if table can add more columns based on plan limits (ORM version)

    Args:
        db: SQLAlchemy Session
        table_id: Table ID

    Returns:
        Tuple of (has_pro, current_count, max_allowed)
    """
    from sqlalchemy import func

    from app.models.orm import Subscription, Table, TableColumn

    try:
        # Get project_id from table
        table = db.query(Table).filter(Table.id == table_id).first()
        if not table:
            return False, 0, 0

        project_id = str(table.project_id)

        # Check if has Pro plan
        has_pro_query = (
            db.query(Subscription)
            .filter(
                Subscription.project_id == project_id,
                func.lower(Subscription.status).in_(["active", "trialing"]),
                Subscription.plan_id == "pro",
            )
            .first()
        )
        has_pro = bool(has_pro_query)

        # Get current column count for this table
        current_count = (
            db.query(func.count(TableColumn.id)).filter(TableColumn.table_id == table_id).scalar()
            or 0
        )

        max_allowed = 200 if has_pro else 60

        return has_pro, current_count, max_allowed

    except Exception as e:
        raise
