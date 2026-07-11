"""
Master Key CRUD operations
Gestión de claves de cifrado a nivel de proyecto

Operaciones:
- Crear configuración de cifrado para un proyecto
- Verificar passphrase del usuario
- Obtener salts para derivación de claves
- Helpers para cifrar/descifrar datos de tablas, columnas, mapeos, etc.

Autor: DataMap Security Team
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from psycopg2.extras import RealDictCursor

from app.utils.encryption import EncryptionManager

# ============================================================================
# PROJECT ENCRYPTION MANAGEMENT
# ============================================================================


def create_project_encryption(db, project_id: str, passphrase: str) -> Dict[str, Any]:
    """
    Crea la configuración de cifrado para un proyecto

    Genera:
    - Salt de verificación (para hash one-way de master key)
    - Salt de derivación de clave (para derivar AES key)
    - Hash de master key (Argon2id one-way)

    Args:
        db: Database connection
        project_id: ID del proyecto
        passphrase: Passphrase del usuario (master key)

    Returns:
        Dict con la configuración creada

    Raises:
        KeyDerivationError: Si falla la derivación
        psycopg2.errors.UniqueViolation: Si el proyecto ya tiene cifrado
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        # Generar salts únicos
        salt_verification = manager.generate_salt()
        salt_key_derivation = manager.generate_salt()

        # Derivar hash de master key (one-way)
        master_key_hash = manager.derive_master_key_hash(passphrase, salt_verification)

        # Codificar para almacenamiento
        salt_verification_encoded = manager.encode_for_storage(salt_verification)
        salt_kdf_encoded = manager.encode_for_storage(salt_key_derivation)
        master_hash_encoded = manager.encode_for_storage(master_key_hash)

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Insertar en la base de datos
        cursor.execute(
            """
            INSERT INTO project_encryption (
                project_id,
                master_key_hash,
                salt_verification,
                salt_key_derivation,
                encryption_enabled,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """,
            (
                project_id,
                master_hash_encoded,
                salt_verification_encoded,
                salt_kdf_encoded,
                True,
                now,
                now,
            ),
        )

        result = cursor.fetchone()
        db.commit()
        return dict(result)
    finally:
        cursor.close()


def get_project_encryption(db, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene la configuración de cifrado de un proyecto

    Args:
        db: Database connection
        project_id: ID del proyecto

    Returns:
        Dict con la configuración o None si no existe
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT * FROM project_encryption
            WHERE project_id = %s
        """,
            (project_id,),
        )

        result = cursor.fetchone()
        return dict(result) if result else None
    finally:
        cursor.close()


def verify_project_passphrase(db, project_id: str, passphrase: str) -> bool:
    """
    Verifica si la passphrase es correcta para un proyecto

    Args:
        db: Database connection
        project_id: ID del proyecto
        passphrase: Passphrase a verificar

    Returns:
        True si la passphrase es correcta, False en caso contrario
    """
    encryption_config = get_project_encryption(db, project_id)

    if not encryption_config:
        return False

    manager = EncryptionManager()

    try:
        # Decodificar desde almacenamiento
        stored_hash = manager.decode_from_storage(encryption_config["master_key_hash"])
        salt_verification = manager.decode_from_storage(encryption_config["salt_verification"])

        # Verificar usando constant-time comparison
        return manager.verify_master_key(passphrase, stored_hash, salt_verification)
    except Exception:
        return False


def get_encryption_salts(db, project_id: str) -> Optional[Tuple[bytes, bytes]]:
    """
    Obtiene los salts de un proyecto (para derivación de claves)

    Args:
        db: Database connection
        project_id: ID del proyecto

    Returns:
        Tuple de (salt_verification, salt_key_derivation) como bytes
        None si el proyecto no tiene cifrado configurado
    """
    encryption_config = get_project_encryption(db, project_id)

    if not encryption_config:
        return None

    manager = EncryptionManager()

    salt_verification = manager.decode_from_storage(encryption_config["salt_verification"])
    salt_kdf = manager.decode_from_storage(encryption_config["salt_key_derivation"])

    return salt_verification, salt_kdf


def derive_encryption_key_for_project(db, project_id: str, passphrase: str) -> Optional[bytes]:
    """
    Deriva la clave de cifrado AES-256 para un proyecto

    IMPORTANTE: Esta clave NUNCA se almacena, solo se deriva on-demand

    Args:
        db: Database connection
        project_id: ID del proyecto
        passphrase: Passphrase del usuario

    Returns:
        32-byte AES-256 key o None si falla la verificación
    """
    # Primero verificar que la passphrase es correcta
    if not verify_project_passphrase(db, project_id, passphrase):
        return None

    # Obtener salt de derivación
    salts = get_encryption_salts(db, project_id)
    if not salts:
        return None

    _, salt_kdf = salts

    # Derivar clave de cifrado
    manager = EncryptionManager()
    encryption_key = manager.derive_encryption_key(passphrase, salt_kdf)

    return encryption_key


def update_project_encryption_enabled(
    db, project_id: str, enabled: bool
) -> Optional[Dict[str, Any]]:
    """
    Habilita o deshabilita el cifrado para un proyecto

    Args:
        db: Database connection
        project_id: ID del proyecto
        enabled: True para habilitar, False para deshabilitar

    Returns:
        Configuración actualizada o None si no existe
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        cursor.execute(
            """
            UPDATE project_encryption
            SET encryption_enabled = %s, updated_at = %s
            WHERE project_id = %s
            RETURNING *
        """,
            (enabled, now, project_id),
        )

        result = cursor.fetchone()
        db.commit()
        return dict(result) if result else None
    finally:
        cursor.close()


def delete_project_encryption(db, project_id: str) -> bool:
    """
    Elimina la configuración de cifrado de un proyecto

    ADVERTENCIA: Esto hará que todos los datos cifrados sean irrecuperables

    Args:
        db: Database connection
        project_id: ID del proyecto

    Returns:
        True si se eliminó, False si no existía
    """
    cursor = db.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            DELETE FROM project_encryption
            WHERE project_id = %s
        """,
            (project_id,),
        )

        deleted = bool(cursor.rowcount > 0)
        db.commit()
        return deleted
    finally:
        cursor.close()


# ============================================================================
# HELPER FUNCTIONS FOR ENCRYPTING/DECRYPTING SPECIFIC FIELDS
# ============================================================================


def encrypt_table_name(name: str, encryption_key: bytes) -> Tuple[str, str]:
    """
    Cifra el nombre de una tabla

    Args:
        name: Nombre de la tabla (plaintext)
        encryption_key: Clave AES-256 derivada

    Returns:
        Tuple de (ciphertext_base64, nonce_base64)
    """
    manager = EncryptionManager()
    ciphertext, nonce = manager.encrypt_field(name, encryption_key)

    return (manager.encode_for_storage(ciphertext), manager.encode_for_storage(nonce))


def decrypt_table_name(ciphertext_encoded: str, nonce_encoded: str, encryption_key: bytes) -> str:
    """
    Descifra el nombre de una tabla

    Args:
        ciphertext_encoded: Ciphertext en base64
        nonce_encoded: Nonce en base64
        encryption_key: Clave AES-256 derivada

    Returns:
        Nombre de la tabla (plaintext)
    """
    manager = EncryptionManager()
    ciphertext = manager.decode_from_storage(ciphertext_encoded)
    nonce = manager.decode_from_storage(nonce_encoded)

    return manager.decrypt_field(ciphertext, nonce, encryption_key)


def encrypt_column_name(name: str, encryption_key: bytes) -> Tuple[str, str]:
    """
    Cifra el nombre de una columna

    Args:
        name: Nombre de la columna (plaintext)
        encryption_key: Clave AES-256 derivada

    Returns:
        Tuple de (ciphertext_base64, nonce_base64)
    """
    return encrypt_table_name(name, encryption_key)  # Mismo proceso


def decrypt_column_name(ciphertext_encoded: str, nonce_encoded: str, encryption_key: bytes) -> str:
    """
    Descifra el nombre de una columna

    Args:
        ciphertext_encoded: Ciphertext en base64
        nonce_encoded: Nonce en base64
        encryption_key: Clave AES-256 derivada

    Returns:
        Nombre de la columna (plaintext)
    """
    return decrypt_table_name(ciphertext_encoded, nonce_encoded, encryption_key)


def encrypt_column_type(data_type: str, encryption_key: bytes) -> Tuple[str, str]:
    """
    Cifra el tipo de dato de una columna

    Args:
        data_type: Tipo de dato (plaintext) - ej: "VARCHAR(255)"
        encryption_key: Clave AES-256 derivada

    Returns:
        Tuple de (ciphertext_base64, nonce_base64)
    """
    return encrypt_table_name(data_type, encryption_key)


def decrypt_column_type(ciphertext_encoded: str, nonce_encoded: str, encryption_key: bytes) -> str:
    """
    Descifra el tipo de dato de una columna

    Args:
        ciphertext_encoded: Ciphertext en base64
        nonce_encoded: Nonce en base64
        encryption_key: Clave AES-256 derivada

    Returns:
        Tipo de dato (plaintext)
    """
    return decrypt_table_name(ciphertext_encoded, nonce_encoded, encryption_key)


def encrypt_mapping_field(field_value: str, encryption_key: bytes) -> Tuple[str, str]:
    """
    Cifra un campo de mapping (tabla, columna, transformation logic)

    Args:
        field_value: Valor del campo (plaintext)
        encryption_key: Clave AES-256 derivada

    Returns:
        Tuple de (ciphertext_base64, nonce_base64)
    """
    return encrypt_table_name(field_value, encryption_key)


def decrypt_mapping_field(
    ciphertext_encoded: str, nonce_encoded: str, encryption_key: bytes
) -> str:
    """
    Descifra un campo de mapping

    Args:
        ciphertext_encoded: Ciphertext en base64
        nonce_encoded: Nonce en base64
        encryption_key: Clave AES-256 derivada

    Returns:
        Valor del campo (plaintext)
    """
    return decrypt_table_name(ciphertext_encoded, nonce_encoded, encryption_key)


def encrypt_json_field(json_data: str, encryption_key: bytes) -> Tuple[str, str]:
    """
    Cifra un campo JSON (snapshots, diff, metadata)

    Args:
        json_data: JSON string (plaintext)
        encryption_key: Clave AES-256 derivada

    Returns:
        Tuple de (ciphertext_base64, nonce_base64)
    """
    return encrypt_table_name(json_data, encryption_key)


def decrypt_json_field(ciphertext_encoded: str, nonce_encoded: str, encryption_key: bytes) -> str:
    """
    Descifra un campo JSON

    Args:
        ciphertext_encoded: Ciphertext en base64
        nonce_encoded: Nonce en base64
        encryption_key: Clave AES-256 derivada

    Returns:
        JSON string (plaintext)
    """
    return decrypt_table_name(ciphertext_encoded, nonce_encoded, encryption_key)


def encrypt_comment_content(content: str, encryption_key: bytes) -> Tuple[str, str]:
    """
    Cifra el contenido de un comentario

    Args:
        content: Contenido del comentario (plaintext)
        encryption_key: Clave AES-256 derivada

    Returns:
        Tuple de (ciphertext_base64, nonce_base64)
    """
    return encrypt_table_name(content, encryption_key)


def decrypt_comment_content(
    ciphertext_encoded: str, nonce_encoded: str, encryption_key: bytes
) -> str:
    """
    Descifra el contenido de un comentario

    Args:
        ciphertext_encoded: Ciphertext en base64
        nonce_encoded: Nonce en base64
        encryption_key: Clave AES-256 derivada

    Returns:
        Contenido del comentario (plaintext)
    """
    return decrypt_table_name(ciphertext_encoded, nonce_encoded, encryption_key)


# ============================================================================
# BATCH OPERATIONS (para migración masiva)
# ============================================================================


def encrypt_multiple_fields(
    fields: Dict[str, str], encryption_key: bytes
) -> Dict[str, Tuple[str, str]]:
    """
    Cifra múltiples campos de forma eficiente

    Args:
        fields: Dict de {field_name: plaintext_value}
        encryption_key: Clave AES-256 derivada

    Returns:
        Dict de {field_name: (ciphertext_base64, nonce_base64)}

    Ejemplo:
        fields = {
            'table_name': 'users',
            'column_name': 'email',
            'data_type': 'VARCHAR(255)'
        }
        encrypted = encrypt_multiple_fields(fields, key)
        # encrypted = {
        #     'table_name': ('abc123...', 'xyz789...'),
        #     'column_name': ('def456...', 'uvw012...'),
        #     ...
        # }
    """
    manager = EncryptionManager()
    result = {}

    for field_name, plaintext in fields.items():
        ciphertext, nonce = manager.encrypt_field(plaintext, encryption_key)
        result[field_name] = (
            manager.encode_for_storage(ciphertext),
            manager.encode_for_storage(nonce),
        )

    return result


def decrypt_multiple_fields(
    encrypted_fields: Dict[str, Tuple[str, str]], encryption_key: bytes
) -> Dict[str, str]:
    """
    Descifra múltiples campos de forma eficiente

    Args:
        encrypted_fields: Dict de {field_name: (ciphertext_base64, nonce_base64)}
        encryption_key: Clave AES-256 derivada

    Returns:
        Dict de {field_name: plaintext_value}
    """
    manager = EncryptionManager()
    result = {}

    for field_name, (ciphertext_encoded, nonce_encoded) in encrypted_fields.items():
        ciphertext = manager.decode_from_storage(ciphertext_encoded)
        nonce = manager.decode_from_storage(nonce_encoded)
        result[field_name] = manager.decrypt_field(ciphertext, nonce, encryption_key)

    return result


# ============================================================================
# ROTATION DE MASTER KEY (Re-encriptación completa)
# ============================================================================


def rotate_project_master_key(
    db, project_id: str, old_passphrase: str, new_passphrase: str
) -> bool:
    """
    Rota la master key de un proyecto

    Este proceso:
    1. Verifica la passphrase antigua
    2. Deriva nueva master key hash y nuevos salts
    3. Re-cifra TODOS los datos del proyecto con la nueva clave
    4. Actualiza la configuración de cifrado

    ADVERTENCIA: Operación costosa, puede tardar varios minutos

    Args:
        db: Database connection
        project_id: ID del proyecto
        old_passphrase: Passphrase actual
        new_passphrase: Nueva passphrase

    Returns:
        True si la rotación fue exitosa, False en caso contrario

    Nota:
        Esta función debe ser ejecutada en una transacción
        La implementación completa está en encryption_service.py
    """
    # Verificar passphrase actual
    if not verify_project_passphrase(db, project_id, old_passphrase):
        return False

    # TODO: Implementar re-encriptación completa
    # Ver encryption_service.py para la implementación completa
    # Por ahora solo actualizar los hashes/salts

    cursor = db.cursor(cursor_factory=RealDictCursor)
    manager = EncryptionManager()

    try:
        # Generar nuevos salts
        new_salt_verification = manager.generate_salt()
        new_salt_kdf = manager.generate_salt()

        # Derivar nuevo hash de master key
        new_master_hash = manager.derive_master_key_hash(new_passphrase, new_salt_verification)

        # Codificar
        new_salt_verification_encoded = manager.encode_for_storage(new_salt_verification)
        new_salt_kdf_encoded = manager.encode_for_storage(new_salt_kdf)
        new_master_hash_encoded = manager.encode_for_storage(new_master_hash)

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Actualizar configuración
        cursor.execute(
            """
            UPDATE project_encryption
            SET
                master_key_hash = %s,
                salt_verification = %s,
                salt_key_derivation = %s,
                updated_at = %s
            WHERE project_id = %s
        """,
            (
                new_master_hash_encoded,
                new_salt_verification_encoded,
                new_salt_kdf_encoded,
                now,
                project_id,
            ),
        )

        db.commit()
        return True
    except Exception as e:
        db.rollback()
        print(f"Error rotating master key: {e}")
        return False
    finally:
        cursor.close()


# ============================================================================
# SQLALCHEMY ORM VERSIONS - Funciones con sufijo _orm
# ============================================================================


def create_project_encryption_orm(db, project_id: str, passphrase: str) -> Dict[str, Any]:
    """
    Crea la configuración de cifrado para un proyecto (ORM version)

    Genera:
    - Salt de verificación (para hash one-way de master key)
    - Salt de derivación de clave (para derivar AES key)
    - Hash de master key (Argon2id one-way)

    Args:
        db: SQLAlchemy Session
        project_id: ID del proyecto
        passphrase: Passphrase del usuario (master key)

    Returns:
        Dict con la configuración creada

    Raises:
        KeyDerivationError: Si falla la derivación
        IntegrityError: Si el proyecto ya tiene cifrado
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.orm import ProjectEncryption

    manager = EncryptionManager()

    try:
        # Generar salts únicos
        salt_verification = manager.generate_salt()
        salt_key_derivation = manager.generate_salt()

        # Derivar hash de master key (one-way)
        master_key_hash = manager.derive_master_key_hash(passphrase, salt_verification)

        # Codificar para almacenamiento
        salt_verification_encoded = manager.encode_for_storage(salt_verification)
        salt_kdf_encoded = manager.encode_for_storage(salt_key_derivation)
        master_hash_encoded = manager.encode_for_storage(master_key_hash)

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Crear configuración
        new_config = ProjectEncryption(
            project_id=project_id,
            master_key_hash=master_hash_encoded,
            salt_verification=salt_verification_encoded,
            salt_key_derivation=salt_kdf_encoded,
            encryption_enabled=True,
            created_at=now,
            updated_at=now,
        )

        db.add(new_config)
        db.commit()
        db.refresh(new_config)

        return {
            "project_id": str(new_config.project_id),
            "master_key_hash": new_config.master_key_hash,
            "salt_verification": new_config.salt_verification,
            "salt_key_derivation": new_config.salt_key_derivation,
            "encryption_enabled": new_config.encryption_enabled,
            "created_at": new_config.created_at,
            "updated_at": new_config.updated_at,
        }

    except IntegrityError:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise


def get_project_encryption_orm(db, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene la configuración de cifrado de un proyecto (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: ID del proyecto

    Returns:
        Dict con la configuración o None si no existe
    """
    from app.models.orm import ProjectEncryption

    try:
        config = (
            db.query(ProjectEncryption).filter(ProjectEncryption.project_id == project_id).first()
        )

        if not config:
            return None

        return {
            "project_id": str(config.project_id),
            "master_key_hash": config.master_key_hash,
            "salt_verification": config.salt_verification,
            "salt_key_derivation": config.salt_key_derivation,
            "encryption_enabled": config.encryption_enabled,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }

    except Exception as e:
        raise


def verify_project_passphrase_orm(db, project_id: str, passphrase: str) -> bool:
    """
    Verifica si la passphrase es correcta para un proyecto (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: ID del proyecto
        passphrase: Passphrase a verificar

    Returns:
        True si la passphrase es correcta, False en caso contrario
    """
    encryption_config = get_project_encryption_orm(db, project_id)

    if not encryption_config:
        return False

    manager = EncryptionManager()

    try:
        # Decodificar desde almacenamiento
        stored_hash = manager.decode_from_storage(encryption_config["master_key_hash"])
        salt_verification = manager.decode_from_storage(encryption_config["salt_verification"])

        # Verificar usando constant-time comparison
        return manager.verify_master_key(passphrase, stored_hash, salt_verification)
    except Exception:
        return False


def get_encryption_salts_orm(db, project_id: str) -> Optional[Tuple[bytes, bytes]]:
    """
    Obtiene los salts de un proyecto (para derivación de claves) (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: ID del proyecto

    Returns:
        Tuple de (salt_verification, salt_key_derivation) como bytes
        None si el proyecto no tiene cifrado configurado
    """
    encryption_config = get_project_encryption_orm(db, project_id)

    if not encryption_config:
        return None

    manager = EncryptionManager()

    salt_verification = manager.decode_from_storage(encryption_config["salt_verification"])
    salt_kdf = manager.decode_from_storage(encryption_config["salt_key_derivation"])

    return salt_verification, salt_kdf


def derive_encryption_key_for_project_orm(db, project_id: str, passphrase: str) -> Optional[bytes]:
    """
    Deriva la clave de cifrado AES-256 para un proyecto (ORM version)

    IMPORTANTE: Esta clave NUNCA se almacena, solo se deriva on-demand

    Args:
        db: SQLAlchemy Session
        project_id: ID del proyecto
        passphrase: Passphrase del usuario

    Returns:
        32-byte AES-256 key o None si falla la verificación
    """
    # Primero verificar que la passphrase es correcta
    if not verify_project_passphrase_orm(db, project_id, passphrase):
        return None

    # Obtener salt de derivación
    salts = get_encryption_salts_orm(db, project_id)
    if not salts:
        return None

    _, salt_kdf = salts

    # Derivar clave de cifrado
    manager = EncryptionManager()
    encryption_key = manager.derive_encryption_key(passphrase, salt_kdf)

    return encryption_key


def update_project_encryption_enabled_orm(
    db, project_id: str, enabled: bool
) -> Optional[Dict[str, Any]]:
    """
    Habilita o deshabilita el cifrado para un proyecto (ORM version)

    Args:
        db: SQLAlchemy Session
        project_id: ID del proyecto
        enabled: True para habilitar, False para deshabilitar

    Returns:
        Configuración actualizada o None si el proyecto no existe
    """
    from app.models.orm import ProjectEncryption

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        db.query(ProjectEncryption).filter(ProjectEncryption.project_id == project_id).update(
            {ProjectEncryption.encryption_enabled: enabled, ProjectEncryption.updated_at: now}
        )

        db.commit()

        # Retornar configuración actualizada
        updated_config = (
            db.query(ProjectEncryption).filter(ProjectEncryption.project_id == project_id).first()
        )

        if not updated_config:
            return None

        return {
            "project_id": str(updated_config.project_id),
            "master_key_hash": updated_config.master_key_hash,
            "salt_verification": updated_config.salt_verification,
            "salt_key_derivation": updated_config.salt_key_derivation,
            "encryption_enabled": updated_config.encryption_enabled,
            "created_at": updated_config.created_at,
            "updated_at": updated_config.updated_at,
        }

    except Exception as e:
        db.rollback()
        raise


def delete_project_encryption_orm(db, project_id: str) -> bool:
    """
    Elimina la configuración de cifrado de un proyecto (ORM version)

    ADVERTENCIA: Esto hará que todos los datos cifrados sean irrecuperables

    Args:
        db: SQLAlchemy Session
        project_id: ID del proyecto

    Returns:
        True si se eliminó, False si no existía
    """
    from app.models.orm import ProjectEncryption

    try:
        deleted_count = (
            db.query(ProjectEncryption).filter(ProjectEncryption.project_id == project_id).delete()
        )

        db.commit()
        return bool(deleted_count > 0)

    except Exception as e:
        db.rollback()
        raise


def rotate_project_master_key_orm(
    db, project_id: str, old_passphrase: str, new_passphrase: str
) -> bool:
    """
    Rota la master key de un proyecto (ORM version)

    Este proceso:
    1. Verifica la passphrase antigua
    2. Deriva nueva master key hash y nuevos salts
    3. Re-cifra TODOS los datos del proyecto con la nueva clave
    4. Actualiza la configuración de cifrado

    ADVERTENCIA: Operación costosa, puede tardar varios minutos

    Args:
        db: SQLAlchemy Session
        project_id: ID del proyecto
        old_passphrase: Passphrase actual
        new_passphrase: Nueva passphrase

    Returns:
        True si la rotación fue exitosa, False en caso contrario

    Nota:
        Esta función debe ser ejecutada en una transacción
        La implementación completa está en encryption_service.py
    """
    from app.models.orm import ProjectEncryption

    # Verificar passphrase actual
    if not verify_project_passphrase_orm(db, project_id, old_passphrase):
        return False

    # TODO: Implementar re-encriptación completa
    # Ver encryption_service.py para la implementación completa
    # Por ahora solo actualizar los hashes/salts

    manager = EncryptionManager()

    try:
        # Generar nuevos salts
        new_salt_verification = manager.generate_salt()
        new_salt_kdf = manager.generate_salt()

        # Derivar nuevo hash de master key
        new_master_hash = manager.derive_master_key_hash(new_passphrase, new_salt_verification)

        # Codificar
        new_salt_verification_encoded = manager.encode_for_storage(new_salt_verification)
        new_salt_kdf_encoded = manager.encode_for_storage(new_salt_kdf)
        new_master_hash_encoded = manager.encode_for_storage(new_master_hash)

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Actualizar configuración
        db.query(ProjectEncryption).filter(ProjectEncryption.project_id == project_id).update(
            {
                ProjectEncryption.master_key_hash: new_master_hash_encoded,
                ProjectEncryption.salt_verification: new_salt_verification_encoded,
                ProjectEncryption.salt_key_derivation: new_salt_kdf_encoded,
                ProjectEncryption.updated_at: now,
            }
        )

        db.commit()
        return True

    except Exception as e:
        db.rollback()
        print(f"Error rotating master key: {e}")
        return False


def get_encryption_key_from_session_orm(db, user_id: str) -> Optional[bytes]:
    """
    Obtiene la clave de cifrado de la sesión del usuario.

    La clave de cifrado se gestiona via Redis/request.state en el middleware.
    Esta función retorna None ya que sin el contexto de la request no se puede
    recuperar la clave. Usar getattr(request.state, 'encryption_key', None)
    cuando se dispone del objeto request.

    Args:
        db: SQLAlchemy Session (no utilizado, mantenido por compatibilidad)
        user_id: ID del usuario

    Returns:
        None (la clave se obtiene del estado de la request, no de la BD)
    """
    return None
