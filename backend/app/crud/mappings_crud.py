# backend/app/crud/mappings_crud.py
"""
CRUD operations for mappings
Pure database operations without business logic
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.utils.error_codes import ErrorCode, make_error


# ========================================================================
# SQLALCHEMY ORM VERSIONS - Funciones con sufijo _orm
# ========================================================================


def create_mapping_orm(
    db,
    project_id: str,
    origin_table: str,
    origin_column: str,
    destination_table: str,
    destination_column: str,
    user_id: str,
    encryption_key: Optional[bytes] = None,
    origin_source_type: str = "import",
    destination_source_type: str = "import",
    origin_session_id: Optional[str] = None,
    destination_session_id: Optional[str] = None,
    origin_table_id: Optional[str] = None,
    destination_table_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new mapping with automatic encryption support and hybrid mode (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: Project ID
        origin_table: Origin table name
        origin_column: Origin column name
        destination_table: Destination table name
        destination_column: Destination column name
        user_id: User ID creating the mapping
        encryption_key: Optional encryption key from session (bytes)
        origin_source_type: Origin source type ('import' or 'connector')
        destination_source_type: Destination source type ('import' or 'connector')
        origin_session_id: Redis session ID for origin (if connector mode)
        destination_session_id: Redis session ID for destination (if connector mode)
        origin_table_id: FK to imported table (if import mode)
        destination_table_id: FK to imported table (if import mode)

    Returns:
        Created mapping as dict

    Raises:
        HTTPException 403: If project requires encryption but no key provided
    """
    import uuid

    from app.crud import master_key_crud
    from app.models.orm import Mapping, ProjectEncryption

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

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

        # VALIDACIÓN ESTRICTA - CRÍTICO
        if config and config["encryption_enabled"] and not encryption_key:
            raise HTTPException(
                status_code=403,
                detail="El proyecto requiere encriptación. Por favor, desbloquea el proyecto primero.",
            )

        # ============================================================================
        # PROCESAMIENTO DE ORIGEN SEGÚN MODO
        # ============================================================================
        origin_table_hash = None
        origin_column_hash = None
        origin_table_enc = None
        origin_table_nonce = None
        origin_column_enc = None
        origin_column_nonce = None

        if origin_source_type == "connector":
            # Modo connector: hashear con SHA-256 (one-way)
            origin_table_hash = hashlib.sha256(origin_table.encode()).hexdigest()
            origin_column_hash = hashlib.sha256(origin_column.encode()).hexdigest()
            # NO cifrar en modo connector
        elif origin_source_type == "import":
            # Modo import: cifrar con AES-256-GCM si encryption está habilitado
            if config and config["encryption_enabled"] and encryption_key:
                origin_table_enc, origin_table_nonce = master_key_crud.encrypt_mapping_field(
                    origin_table, encryption_key
                )
                origin_column_enc, origin_column_nonce = master_key_crud.encrypt_mapping_field(
                    origin_column, encryption_key
                )
            # NO hashear en modo import

        # ============================================================================
        # PROCESAMIENTO DE DESTINO SEGÚN MODO
        # ============================================================================
        destination_table_hash = None
        destination_column_hash = None
        destination_table_enc = None
        destination_table_nonce = None
        destination_column_enc = None
        destination_column_nonce = None

        if destination_source_type == "connector":
            # Modo connector: hashear con SHA-256 (one-way)
            destination_table_hash = hashlib.sha256(destination_table.encode()).hexdigest()
            destination_column_hash = hashlib.sha256(destination_column.encode()).hexdigest()
            # NO cifrar en modo connector
        elif destination_source_type == "import":
            # Modo import: cifrar con AES-256-GCM si encryption está habilitado
            if config and config["encryption_enabled"] and encryption_key:
                destination_table_enc, destination_table_nonce = (
                    master_key_crud.encrypt_mapping_field(destination_table, encryption_key)
                )
                destination_column_enc, destination_column_nonce = (
                    master_key_crud.encrypt_mapping_field(destination_column, encryption_key)
                )
            # NO hashear en modo import

        # ============================================================================
        # CREAR MAPPING CON TODOS LOS CAMPOS
        # ============================================================================
        is_encrypted = (config and config["encryption_enabled"] and encryption_key) and (
            origin_source_type == "import" or destination_source_type == "import"
        )

        mapping_id = uuid.uuid4()

        new_mapping = Mapping(
            id=mapping_id,
            project_id=project_id,
            origin_source_type=origin_source_type,
            destination_source_type=destination_source_type,
            # Origen - import mode (plaintext o encrypted)
            origin_table=(
                origin_table
                if origin_source_type == "import" and not (config and config["encryption_enabled"])
                else None
            ),
            origin_column=(
                origin_column
                if origin_source_type == "import" and not (config and config["encryption_enabled"])
                else None
            ),
            origin_table_encrypted=origin_table_enc,
            origin_table_nonce=origin_table_nonce,
            origin_column_encrypted=origin_column_enc,
            origin_column_nonce=origin_column_nonce,
            # Origen - connector mode (hashes)
            origin_table_hash=origin_table_hash,
            origin_column_hash=origin_column_hash,
            origin_session_id=origin_session_id,
            origin_table_id=origin_table_id,
            # Destino - import mode (plaintext o encrypted)
            destination_table=(
                destination_table
                if destination_source_type == "import"
                and not (config and config["encryption_enabled"])
                else None
            ),
            destination_column=(
                destination_column
                if destination_source_type == "import"
                and not (config and config["encryption_enabled"])
                else None
            ),
            destination_table_encrypted=destination_table_enc,
            destination_table_nonce=destination_table_nonce,
            destination_column_encrypted=destination_column_enc,
            destination_column_nonce=destination_column_nonce,
            # Destino - connector mode (hashes)
            destination_table_hash=destination_table_hash,
            destination_column_hash=destination_column_hash,
            destination_session_id=destination_session_id,
            destination_table_id=destination_table_id,
            # Metadata
            is_encrypted=is_encrypted,
            created_at=now,
            updated_at=now,
        )

        db.add(new_mapping)
        db.commit()
        db.refresh(new_mapping)

        # Convert to dict
        result_dict = {
            "id": str(new_mapping.id),
            "project_id": str(new_mapping.project_id),
            "origin_source_type": new_mapping.origin_source_type,
            "destination_source_type": new_mapping.destination_source_type,
            "origin_table": new_mapping.origin_table,
            "origin_column": new_mapping.origin_column,
            "destination_table": new_mapping.destination_table,
            "destination_column": new_mapping.destination_column,
            "origin_table_hash": new_mapping.origin_table_hash,
            "origin_column_hash": new_mapping.origin_column_hash,
            "destination_table_hash": new_mapping.destination_table_hash,
            "destination_column_hash": new_mapping.destination_column_hash,
            "origin_table_encrypted": new_mapping.origin_table_encrypted,
            "origin_table_nonce": new_mapping.origin_table_nonce,
            "origin_column_encrypted": new_mapping.origin_column_encrypted,
            "origin_column_nonce": new_mapping.origin_column_nonce,
            "destination_table_encrypted": new_mapping.destination_table_encrypted,
            "destination_table_nonce": new_mapping.destination_table_nonce,
            "destination_column_encrypted": new_mapping.destination_column_encrypted,
            "destination_column_nonce": new_mapping.destination_column_nonce,
            "transformation_logic_encrypted": new_mapping.transformation_logic_encrypted,
            "transformation_logic_nonce": new_mapping.transformation_logic_nonce,
            "origin_session_id": (
                str(new_mapping.origin_session_id) if new_mapping.origin_session_id else None
            ),
            "destination_session_id": (
                str(new_mapping.destination_session_id)
                if new_mapping.destination_session_id
                else None
            ),
            "origin_table_id": (
                str(new_mapping.origin_table_id) if new_mapping.origin_table_id else None
            ),
            "destination_table_id": (
                str(new_mapping.destination_table_id) if new_mapping.destination_table_id else None
            ),
            "is_encrypted": new_mapping.is_encrypted,
            "created_at": new_mapping.created_at,
            "updated_at": new_mapping.updated_at,
        }

        # Add decrypted values to result for immediate use
        if origin_source_type == "import":
            result_dict["origin_table"] = origin_table
            result_dict["origin_column"] = origin_column
        if destination_source_type == "import":
            result_dict["destination_table"] = destination_table
            result_dict["destination_column"] = destination_column

        return result_dict

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise


def get_mappings_by_project_orm(
    db, project_id: str, encryption_key: Optional[bytes] = None
) -> List[Dict[str, Any]]:
    """
    Get all mappings for a project with hybrid mode support (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: Project ID
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        List of mapping dicts with decrypted data (import mode) or hashes (connector mode)
    """
    from app.crud import master_key_crud
    from app.models.orm import Mapping

    try:
        mappings_objs = (
            db.query(Mapping)
            .filter(Mapping.project_id == project_id)
            .order_by(Mapping.created_at)
            .all()
        )

        mappings = []

        for mapping in mappings_objs:
            result_dict = {
                "id": str(mapping.id),
                "project_id": str(mapping.project_id),
                "origin_source_type": mapping.origin_source_type,
                "destination_source_type": mapping.destination_source_type,
                "origin_table": mapping.origin_table,
                "origin_column": mapping.origin_column,
                "destination_table": mapping.destination_table,
                "destination_column": mapping.destination_column,
                "origin_table_encrypted": mapping.origin_table_encrypted,
                "origin_table_nonce": mapping.origin_table_nonce,
                "origin_column_encrypted": mapping.origin_column_encrypted,
                "origin_column_nonce": mapping.origin_column_nonce,
                "destination_table_encrypted": mapping.destination_table_encrypted,
                "destination_table_nonce": mapping.destination_table_nonce,
                "destination_column_encrypted": mapping.destination_column_encrypted,
                "destination_column_nonce": mapping.destination_column_nonce,
                "origin_table_hash": mapping.origin_table_hash,
                "origin_column_hash": mapping.origin_column_hash,
                "destination_table_hash": mapping.destination_table_hash,
                "destination_column_hash": mapping.destination_column_hash,
                "origin_session_id": (
                    str(mapping.origin_session_id) if mapping.origin_session_id else None
                ),
                "destination_session_id": (
                    str(mapping.destination_session_id) if mapping.destination_session_id else None
                ),
                "origin_table_id": (
                    str(mapping.origin_table_id) if mapping.origin_table_id else None
                ),
                "destination_table_id": (
                    str(mapping.destination_table_id) if mapping.destination_table_id else None
                ),
                # Texto plano (proyectos sin cifrado); si está cifrado se descifra abajo
                "transformation_logic": mapping.transformation_logic,
                "transformation_logic_encrypted": mapping.transformation_logic_encrypted,
                "transformation_logic_nonce": mapping.transformation_logic_nonce,
                "is_encrypted": mapping.is_encrypted,
                "created_at": mapping.created_at,
                "updated_at": mapping.updated_at,
            }

            # ============================================================================
            # DESCIFRADO CONDICIONAL PARA ORIGEN
            # ============================================================================
            if result_dict.get("origin_source_type") == "import" and encryption_key:
                # Modo import: descifrar si está cifrado
                try:
                    if result_dict.get("origin_table_encrypted") and result_dict.get(
                        "origin_table_nonce"
                    ):
                        result_dict["origin_table"] = master_key_crud.decrypt_mapping_field(
                            result_dict["origin_table_encrypted"],
                            result_dict["origin_table_nonce"],
                            encryption_key,
                        )

                    if result_dict.get("origin_column_encrypted") and result_dict.get(
                        "origin_column_nonce"
                    ):
                        result_dict["origin_column"] = master_key_crud.decrypt_mapping_field(
                            result_dict["origin_column_encrypted"],
                            result_dict["origin_column_nonce"],
                            encryption_key,
                        )
                except Exception:
                    # If decryption fails, keep encrypted values
                    pass
            elif result_dict.get("origin_source_type") == "connector":
                # Modo connector: dejar hashes tal cual (el frontend los resolverá con la sesión Redis)
                pass

            # ============================================================================
            # DESCIFRADO CONDICIONAL PARA DESTINO
            # ============================================================================
            if result_dict.get("destination_source_type") == "import" and encryption_key:
                # Modo import: descifrar si está cifrado
                try:
                    if result_dict.get("destination_table_encrypted") and result_dict.get(
                        "destination_table_nonce"
                    ):
                        result_dict["destination_table"] = master_key_crud.decrypt_mapping_field(
                            result_dict["destination_table_encrypted"],
                            result_dict["destination_table_nonce"],
                            encryption_key,
                        )

                    if result_dict.get("destination_column_encrypted") and result_dict.get(
                        "destination_column_nonce"
                    ):
                        result_dict["destination_column"] = master_key_crud.decrypt_mapping_field(
                            result_dict["destination_column_encrypted"],
                            result_dict["destination_column_nonce"],
                            encryption_key,
                        )
                except Exception:
                    # If decryption fails, keep encrypted values
                    pass
            elif result_dict.get("destination_source_type") == "connector":
                # Modo connector: dejar hashes tal cual
                pass

            # ============================================================================
            # DESCIFRAR TRANSFORMATION LOGIC SI ESTÁ CIFRADO
            # ============================================================================
            if (
                result_dict.get("transformation_logic_encrypted")
                and result_dict.get("transformation_logic_nonce")
                and encryption_key
            ):
                try:
                    result_dict["transformation_logic"] = master_key_crud.decrypt_mapping_field(
                        result_dict["transformation_logic_encrypted"],
                        result_dict["transformation_logic_nonce"],
                        encryption_key,
                    )
                except Exception:
                    # If decryption fails, skip
                    pass

            mappings.append(result_dict)

        return mappings

    except Exception as e:
        raise


def get_mapping_by_id_orm(
    db, mapping_id: str, encryption_key: Optional[bytes] = None
) -> Optional[Dict[str, Any]]:
    """
    Get a specific mapping by ID (ORM version)

    Args:
        db: SQLAlchemy Session
        mapping_id: Mapping ID
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Mapping dict with decrypted data if encryption_key provided, or None if not found
    """
    from app.crud import master_key_crud
    from app.models.orm import Mapping

    try:
        mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()

        if not mapping:
            return None

        result_dict = {
            "id": str(mapping.id),
            "project_id": str(mapping.project_id),
            "origin_table": mapping.origin_table,
            "origin_column": mapping.origin_column,
            "destination_table": mapping.destination_table,
            "destination_column": mapping.destination_column,
            "origin_table_encrypted": mapping.origin_table_encrypted,
            "origin_table_nonce": mapping.origin_table_nonce,
            "origin_column_encrypted": mapping.origin_column_encrypted,
            "origin_column_nonce": mapping.origin_column_nonce,
            "destination_table_encrypted": mapping.destination_table_encrypted,
            "destination_table_nonce": mapping.destination_table_nonce,
            "destination_column_encrypted": mapping.destination_column_encrypted,
            "destination_column_nonce": mapping.destination_column_nonce,
            "transformation_logic_encrypted": mapping.transformation_logic_encrypted,
            "transformation_logic_nonce": mapping.transformation_logic_nonce,
            "is_encrypted": mapping.is_encrypted,
            "created_at": mapping.created_at,
            "updated_at": mapping.updated_at,
        }

        # Decrypt if encrypted and encryption_key provided
        if result_dict.get("is_encrypted") and encryption_key:
            try:
                if result_dict.get("origin_table_encrypted") and result_dict.get(
                    "origin_table_nonce"
                ):
                    result_dict["origin_table"] = master_key_crud.decrypt_mapping_field(
                        result_dict["origin_table_encrypted"],
                        result_dict["origin_table_nonce"],
                        encryption_key,
                    )

                if result_dict.get("origin_column_encrypted") and result_dict.get(
                    "origin_column_nonce"
                ):
                    result_dict["origin_column"] = master_key_crud.decrypt_mapping_field(
                        result_dict["origin_column_encrypted"],
                        result_dict["origin_column_nonce"],
                        encryption_key,
                    )

                if result_dict.get("destination_table_encrypted") and result_dict.get(
                    "destination_table_nonce"
                ):
                    result_dict["destination_table"] = master_key_crud.decrypt_mapping_field(
                        result_dict["destination_table_encrypted"],
                        result_dict["destination_table_nonce"],
                        encryption_key,
                    )

                if result_dict.get("destination_column_encrypted") and result_dict.get(
                    "destination_column_nonce"
                ):
                    result_dict["destination_column"] = master_key_crud.decrypt_mapping_field(
                        result_dict["destination_column_encrypted"],
                        result_dict["destination_column_nonce"],
                        encryption_key,
                    )

                if result_dict.get("transformation_logic_encrypted") and result_dict.get(
                    "transformation_logic_nonce"
                ):
                    result_dict["transformation_logic"] = master_key_crud.decrypt_mapping_field(
                        result_dict["transformation_logic_encrypted"],
                        result_dict["transformation_logic_nonce"],
                        encryption_key,
                    )
            except Exception:
                # If decryption fails, keep encrypted values
                pass

        return result_dict

    except Exception as e:
        raise


def delete_mapping_orm(db, mapping_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Delete a mapping (ORM version)

    Args:
        db: SQLAlchemy Session
        mapping_id: Mapping ID to delete
        user_id: User ID performing the deletion

    Returns:
        Deleted mapping info or None if not found
    """
    from app.models.orm import Mapping

    try:
        # Get mapping info first
        mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()

        if not mapping:
            return None

        mapping_dict = {
            "id": str(mapping.id),
            "project_id": str(mapping.project_id),
            "origin_table": mapping.origin_table,
            "destination_table": mapping.destination_table,
        }

        # Delete the mapping
        db.query(Mapping).filter(Mapping.id == mapping_id).delete()
        db.commit()

        return mapping_dict

    except Exception as e:
        db.rollback()
        raise


def update_mapping_orm(
    db,
    mapping_id: str,
    origin_table: Optional[str] = None,
    origin_column: Optional[str] = None,
    destination_table: Optional[str] = None,
    destination_column: Optional[str] = None,
    user_id: Optional[str] = None,
    encryption_key: Optional[bytes] = None,
) -> Dict[str, Any]:
    """
    Update a mapping with encryption support (ORM version)

    Args:
        db: SQLAlchemy Session
        mapping_id: Mapping ID to update
        origin_table: New origin table name (optional)
        origin_column: New origin column name (optional)
        destination_table: New destination table name (optional)
        destination_column: New destination column name (optional)
        user_id: User ID performing the update
        encryption_key: Optional encryption key from session (bytes)

    Returns:
        Updated mapping as dict
    """
    from app.crud import master_key_crud
    from app.models.orm import Mapping, ProjectEncryption

    try:
        # Get current mapping to check encryption status and get project_id
        mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()

        if not mapping:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=make_error(ErrorCode.MAPPING_NOT_FOUND))

        project_id = str(mapping.project_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

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

        # Update fields with encryption if applicable
        if config and config["encryption_enabled"] and encryption_key:
            # Update with encryption
            if origin_table is not None:
                enc, nonce = master_key_crud.encrypt_mapping_field(origin_table, encryption_key)
                mapping.origin_table_encrypted = enc
                mapping.origin_table_nonce = nonce
                mapping.origin_table = None  # NULL when encrypted

            if origin_column is not None:
                enc, nonce = master_key_crud.encrypt_mapping_field(origin_column, encryption_key)
                mapping.origin_column_encrypted = enc
                mapping.origin_column_nonce = nonce
                mapping.origin_column = None  # NULL when encrypted

            if destination_table is not None:
                enc, nonce = master_key_crud.encrypt_mapping_field(
                    destination_table, encryption_key
                )
                mapping.destination_table_encrypted = enc
                mapping.destination_table_nonce = nonce
                mapping.destination_table = None  # NULL when encrypted

            if destination_column is not None:
                enc, nonce = master_key_crud.encrypt_mapping_field(
                    destination_column, encryption_key
                )
                mapping.destination_column_encrypted = enc
                mapping.destination_column_nonce = nonce
                mapping.destination_column = None  # NULL when encrypted

            mapping.is_encrypted = True
        else:
            # Update without encryption
            if origin_table is not None:
                mapping.origin_table = origin_table

            if origin_column is not None:
                mapping.origin_column = origin_column

            if destination_table is not None:
                mapping.destination_table = destination_table

            if destination_column is not None:
                mapping.destination_column = destination_column

        mapping.updated_at = now

        db.commit()
        db.refresh(mapping)

        # Convert to dict
        result_dict = {
            "id": str(mapping.id),
            "project_id": str(mapping.project_id),
            "origin_table": mapping.origin_table,
            "origin_column": mapping.origin_column,
            "destination_table": mapping.destination_table,
            "destination_column": mapping.destination_column,
            "origin_table_encrypted": mapping.origin_table_encrypted,
            "origin_table_nonce": mapping.origin_table_nonce,
            "origin_column_encrypted": mapping.origin_column_encrypted,
            "origin_column_nonce": mapping.origin_column_nonce,
            "destination_table_encrypted": mapping.destination_table_encrypted,
            "destination_table_nonce": mapping.destination_table_nonce,
            "destination_column_encrypted": mapping.destination_column_encrypted,
            "destination_column_nonce": mapping.destination_column_nonce,
            "is_encrypted": mapping.is_encrypted,
            "created_at": mapping.created_at,
            "updated_at": mapping.updated_at,
        }

        # If encrypted, add decrypted values to result for immediate use
        if result_dict.get("is_encrypted") and encryption_key:
            if origin_table is not None:
                result_dict["origin_table"] = origin_table
            if origin_column is not None:
                result_dict["origin_column"] = origin_column
            if destination_table is not None:
                result_dict["destination_table"] = destination_table
            if destination_column is not None:
                result_dict["destination_column"] = destination_column

        return result_dict

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise


def delete_all_mappings_orm(db, project_id: str) -> int:
    """
    Elimina todos los mappings de un proyecto (ORM version)

    Usado al restaurar versión de proyecto

    Args:
        db: SQLAlchemy session
        project_id: ID del proyecto

    Returns:
        int: Número de mappings eliminados
    """
    from app.models.orm.mapping import Mapping

    # Delete all mappings for project
    count = (
        db.query(Mapping)
        .filter(Mapping.project_id == project_id)
        .delete(synchronize_session="fetch")
    )

    db.commit()

    return int(count)


def bulk_create_mappings_orm(
    db, project_id: str, mappings: list, encryption_key: Optional[bytes] = None
) -> list:
    """
    Inserta múltiples mappings en una transacción (ORM version)

    Usado al restaurar versión de proyecto

    Args:
        db: SQLAlchemy session
        project_id: ID del proyecto
        mappings: Lista de dicts con datos de mappings
        encryption_key: Clave de encriptación (si proyecto encriptado)

    Returns:
        List[Dict]: Lista de mappings creados (con valores decifrados)

    Raises:
        HTTPException 403: Si proyecto requiere encriptación y no se provee key

    Note:
        Si encryption_key provisto, cifra campos sensibles según source_type
    """
    import hashlib
    import uuid
    from datetime import datetime, timezone

    from fastapi import HTTPException

    from app.crud import master_key_crud
    from app.models.orm.mapping import Mapping
    from app.utils.orm_helpers import model_to_dict

    # Check encryption requirements
    config = master_key_crud.get_project_encryption_orm(db, project_id)
    if config and config["encryption_enabled"] and not encryption_key:
        raise HTTPException(
            status_code=403,
            detail="El proyecto requiere encriptación. Por favor, desbloquea el proyecto primero.",
        )

    mapping_objects = []

    try:
        for mapping_data in mappings:
            # Extract fields
            origin_table = mapping_data.get("origin_table")
            origin_column = mapping_data.get("origin_column")
            destination_table = mapping_data.get("destination_table")
            destination_column = mapping_data.get("destination_column")
            origin_source_type = mapping_data.get("origin_source_type")
            destination_source_type = mapping_data.get("destination_source_type")

            # Initialize encryption fields
            origin_table_encrypted = None
            origin_table_nonce = None
            origin_table_hash = None
            origin_column_encrypted = None
            origin_column_nonce = None
            destination_table_encrypted = None
            destination_table_nonce = None
            destination_table_hash = None
            destination_column_encrypted = None
            destination_column_nonce = None

            # Handle origin encryption/hashing
            if origin_source_type == "connector":
                # Connector mode: SHA-256 hashing
                origin_table_hash = (
                    hashlib.sha256(origin_table.encode()).hexdigest() if origin_table else None
                )
            elif (
                origin_source_type == "import"
                and config
                and config["encryption_enabled"]
                and encryption_key
            ):
                # Import mode with encryption
                if origin_table:
                    origin_table_encrypted, origin_table_nonce = (
                        master_key_crud.encrypt_mapping_field(origin_table, encryption_key)
                    )
                if origin_column:
                    origin_column_encrypted, origin_column_nonce = (
                        master_key_crud.encrypt_mapping_field(origin_column, encryption_key)
                    )

            # Handle destination encryption/hashing
            if destination_source_type == "connector":
                destination_table_hash = (
                    hashlib.sha256(destination_table.encode()).hexdigest()
                    if destination_table
                    else None
                )
            elif (
                destination_source_type == "import"
                and config
                and config["encryption_enabled"]
                and encryption_key
            ):
                if destination_table:
                    destination_table_encrypted, destination_table_nonce = (
                        master_key_crud.encrypt_mapping_field(destination_table, encryption_key)
                    )
                if destination_column:
                    destination_column_encrypted, destination_column_nonce = (
                        master_key_crud.encrypt_mapping_field(destination_column, encryption_key)
                    )

            # Create mapping object
            new_mapping = Mapping(
                id=uuid.uuid4(),
                project_id=uuid.UUID(project_id),
                origin_table=(
                    origin_table
                    if origin_source_type != "import"
                    or not config
                    or not config["encryption_enabled"]
                    else None
                ),
                origin_column=(
                    origin_column if not config or not config["encryption_enabled"] else None
                ),
                destination_table=(
                    destination_table
                    if destination_source_type != "import"
                    or not config
                    or not config["encryption_enabled"]
                    else None
                ),
                destination_column=(
                    destination_column if not config or not config["encryption_enabled"] else None
                ),
                origin_source_type=origin_source_type,
                destination_source_type=destination_source_type,
                origin_table_encrypted=origin_table_encrypted,
                origin_table_nonce=origin_table_nonce,
                origin_column_encrypted=origin_column_encrypted,
                origin_column_nonce=origin_column_nonce,
                origin_table_hash=origin_table_hash,
                destination_table_encrypted=destination_table_encrypted,
                destination_table_nonce=destination_table_nonce,
                destination_column_encrypted=destination_column_encrypted,
                destination_column_nonce=destination_column_nonce,
                destination_table_hash=destination_table_hash,
                is_encrypted=bool(config and config["encryption_enabled"]),
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )

            mapping_objects.append(new_mapping)

        # Bulk insert
        db.add_all(mapping_objects)
        db.commit()

        # Refresh all objects
        for obj in mapping_objects:
            db.refresh(obj)

        # Convert to dicts with decrypted values
        results = []
        for mapping in mapping_objects:
            mapping_dict = model_to_dict(mapping)
            assert mapping_dict is not None

            # Decrypt fields if needed for response
            if mapping.origin_table_encrypted and encryption_key:
                mapping_dict["origin_table"] = master_key_crud.decrypt_mapping_field(
                    str(mapping.origin_table_encrypted),
                    str(mapping.origin_table_nonce),
                    encryption_key,
                )

            if mapping.origin_column_encrypted and encryption_key:
                mapping_dict["origin_column"] = master_key_crud.decrypt_mapping_field(
                    str(mapping.origin_column_encrypted),
                    str(mapping.origin_column_nonce),
                    encryption_key,
                )

            if mapping.destination_table_encrypted and encryption_key:
                mapping_dict["destination_table"] = master_key_crud.decrypt_mapping_field(
                    str(mapping.destination_table_encrypted),
                    str(mapping.destination_table_nonce),
                    encryption_key,
                )

            if mapping.destination_column_encrypted and encryption_key:
                mapping_dict["destination_column"] = master_key_crud.decrypt_mapping_field(
                    str(mapping.destination_column_encrypted),
                    str(mapping.destination_column_nonce),
                    encryption_key,
                )

            results.append(mapping_dict)

        return results

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise
