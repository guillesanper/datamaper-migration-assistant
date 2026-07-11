# backend/test/integration/test_mappings_crud_with_encryption.py
"""
Tests de integración para operaciones CRUD de mappings con encriptación

Cobertura:
- Crear/leer/actualizar/eliminar mappings con encriptación
- Validación de encryption_key requerida
- Encriptación de todos los campos (origin_table, origin_column, destination_table, destination_column, transformation_logic)
- Roundtrip de encriptación/desencriptación
- Lectura sin encryption_key retorna datos cifrados
"""

import pytest
from fastapi import HTTPException

from app.crud import mappings_crud, schemas_crud
from app.services.encryption_service import EncryptionService

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def encrypted_project(clean_db_session, test_user):
    """Proyecto con cifrado configurado"""
    from app.crud.project_crud import ProjectCRUD

    project = ProjectCRUD.create_project_orm(
        clean_db_session,
        test_user["id"],
        "Encrypted Project",
        "Project with encryption",
        "PostgreSQL",
        "MySQL",
        "active",
    )

    # Setup encryption
    passphrase = "SecurePass123!@#"
    EncryptionService.setup_project_encryption(
        clean_db_session, project["id"], passphrase, test_user["id"]
    )

    return {**project, "passphrase": passphrase}


@pytest.fixture
def encryption_key(clean_db_session, encrypted_project):
    """Encryption key para usar en tests"""
    return EncryptionService.get_encryption_key(
        clean_db_session, encrypted_project["id"], encrypted_project["passphrase"]
    )


# ============================================================================
# TESTS DE CREACIÓN DE MAPPINGS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_create_mapping_with_encryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Crear mapping con encriptación"""
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        origin_table="users",
        origin_column="id",
        destination_table="customers",
        destination_column="customer_id",
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    assert mapping is not None
    assert mapping["origin_table"] == "users"
    assert mapping["origin_column"] == "id"
    assert mapping["destination_table"] == "customers"
    assert mapping["destination_column"] == "customer_id"
    assert mapping["is_encrypted"] is True
    assert mapping["origin_table_encrypted"] is not None
    assert mapping["origin_table_nonce"] is not None


@pytest.mark.integration
@pytest.mark.encryption
def test_create_mapping_without_key_fails(clean_db_session, encrypted_project):
    """Test: Crear mapping sin encryption_key en proyecto cifrado debe fallar"""
    with pytest.raises(HTTPException) as exc_info:
        mappings_crud.create_mapping_orm(
            clean_db_session,
            encrypted_project["id"],
            origin_table="users",
            origin_column="id",
            destination_table="customers",
            destination_column="customer_id",
            user_id=encrypted_project["owner_id"],
            encryption_key=None,  # Sin clave
        )

    assert exc_info.value.status_code == 403
    assert "requiere encriptación" in exc_info.value.detail.lower()


@pytest.mark.integration
@pytest.mark.encryption
def test_create_mapping_all_fields_encrypted(clean_db_session, encrypted_project, encryption_key):
    """Test: Todos los campos del mapping se encriptan"""
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        origin_table="users",
        origin_column="email",
        destination_table="customers",
        destination_column="customer_email",
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    # Verificar que todos los campos tienen versión encriptada
    assert mapping["origin_table_encrypted"] is not None
    assert mapping["origin_table_nonce"] is not None
    assert mapping["origin_column_encrypted"] is not None
    assert mapping["origin_column_nonce"] is not None
    assert mapping["destination_table_encrypted"] is not None
    assert mapping["destination_table_nonce"] is not None
    assert mapping["destination_column_encrypted"] is not None
    assert mapping["destination_column_nonce"] is not None


@pytest.mark.integration
@pytest.mark.encryption
def test_create_multiple_mappings_encrypted(clean_db_session, encrypted_project, encryption_key):
    """Test: Crear múltiples mappings encriptados"""
    mapping1 = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    mapping2 = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "email",
        "customers",
        "customer_email",
        encrypted_project["owner_id"],
        encryption_key,
    )

    mapping3 = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "products",
        "id",
        "items",
        "item_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Verificar que todos son diferentes
    assert mapping1["id"] != mapping2["id"]
    assert mapping2["id"] != mapping3["id"]

    # Verificar que los datos encriptados son diferentes
    assert mapping1["origin_table_encrypted"] != mapping2["origin_table_encrypted"]
    assert mapping2["origin_table_encrypted"] != mapping3["origin_table_encrypted"]


# ============================================================================
# TESTS DE LECTURA DE MAPPINGS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_get_mappings_with_encryption_key(clean_db_session, encrypted_project, encryption_key):
    """Test: Leer mappings encriptados con encryption_key"""
    # Crear 3 mappings
    mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )
    mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "email",
        "customers",
        "customer_email",
        encrypted_project["owner_id"],
        encryption_key,
    )
    mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "products",
        "id",
        "items",
        "item_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Leer todos los mappings
    mappings = mappings_crud.get_mappings_by_project_orm(
        clean_db_session, encrypted_project["id"], encryption_key=encryption_key
    )

    assert len(mappings) == 3

    # Verificar que están desencriptados
    origin_tables = [m["origin_table"] for m in mappings]
    assert "users" in origin_tables
    assert "products" in origin_tables


@pytest.mark.integration
@pytest.mark.encryption
def test_get_mappings_without_encryption_key(clean_db_session, encrypted_project, encryption_key):
    """Test: Leer mappings encriptados sin encryption_key retorna datos cifrados"""
    # Crear mapping
    mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Leer sin encryption_key
    mappings = mappings_crud.get_mappings_by_project_orm(
        clean_db_session, encrypted_project["id"], encryption_key=None
    )

    assert len(mappings) == 1
    mapping = mappings[0]

    # Verificar que los datos NO están desencriptados
    assert mapping["origin_table"] is None
    assert mapping["origin_column"] is None
    assert mapping["destination_table"] is None
    assert mapping["destination_column"] is None

    # Pero sí tiene las versiones encriptadas
    assert mapping["origin_table_encrypted"] is not None
    assert mapping["is_encrypted"] is True


@pytest.mark.integration
@pytest.mark.encryption
def test_get_mapping_by_id_with_decryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Obtener mapping por ID con desencriptación"""
    # Crear mapping
    created = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Obtener por ID
    mapping = mappings_crud.get_mapping_by_id_orm(
        clean_db_session, created["id"], encryption_key=encryption_key
    )

    assert mapping is not None
    assert mapping["origin_table"] == "users"
    assert mapping["origin_column"] == "id"
    assert mapping["destination_table"] == "customers"
    assert mapping["destination_column"] == "customer_id"


# ============================================================================
# TESTS DE ACTUALIZACIÓN DE MAPPINGS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_update_mapping_with_encryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Actualizar mapping encriptado"""
    # Crear mapping
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Actualizar
    updated = mappings_crud.update_mapping_orm(
        clean_db_session,
        mapping["id"],
        origin_table="people",
        origin_column="person_id",
        destination_table="clients",
        destination_column="client_id",
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    assert updated is not None
    assert updated["origin_table"] == "people"
    assert updated["origin_column"] == "person_id"
    assert updated["destination_table"] == "clients"
    assert updated["destination_column"] == "client_id"
    assert updated["is_encrypted"] is True


@pytest.mark.integration
@pytest.mark.encryption
def test_update_mapping_changes_encrypted_values(
    clean_db_session, encrypted_project, encryption_key
):
    """Test: Actualizar mapping cambia valores encriptados"""
    # Crear mapping
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    old_encrypted = mapping["origin_table_encrypted"]

    # Actualizar
    updated = mappings_crud.update_mapping_orm(
        clean_db_session,
        mapping["id"],
        "people",
        "person_id",
        "clients",
        "client_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Verificar que el valor encriptado cambió
    assert updated["origin_table_encrypted"] != old_encrypted


# ============================================================================
# TESTS DE ELIMINACIÓN DE MAPPINGS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_delete_mapping_with_encryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Eliminar mapping encriptado"""
    # Crear mapping
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Eliminar
    deleted_info = mappings_crud.delete_mapping_orm(
        clean_db_session, mapping["id"], encrypted_project["owner_id"]
    )

    assert deleted_info is not None
    assert deleted_info["id"] == mapping["id"]

    # Verificar que ya no existe
    mappings = mappings_crud.get_mappings_by_project_orm(
        clean_db_session, encrypted_project["id"], encryption_key
    )
    assert len(mappings) == 0


# ============================================================================
# TESTS DE TRANSFORMATION LOGIC
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
@pytest.mark.skip(reason="update_mapping_transformation no está implementada aún")
def test_update_mapping_with_transformation_logic(
    clean_db_session, encrypted_project, encryption_key
):
    """Test: Actualizar mapping con transformation_logic encriptado"""
    # Crear mapping básico
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "email",
        "customers",
        "customer_email",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Actualizar con transformation_logic
    transformation_logic = "LOWER(TRIM(email))"
    updated = mappings_crud.update_mapping_transformation_orm(
        clean_db_session,
        mapping["id"],
        transformation_logic=transformation_logic,
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    assert updated is not None
    assert updated["transformation_logic_encrypted"] is not None
    assert updated["transformation_logic_nonce"] is not None

    # Leer de vuelta
    mapping_read = mappings_crud.get_mapping_by_id_orm(
        clean_db_session, mapping["id"], encryption_key
    )

    assert mapping_read.get("transformation_logic") == transformation_logic


# ============================================================================
# TESTS DE ROUNDTRIP
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_full_roundtrip_mapping(clean_db_session, encrypted_project, encryption_key):
    """Test: Roundtrip completo de mapping"""
    # 1. Crear mapping
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    assert mapping["origin_table"] == "users"
    assert mapping["origin_column"] == "id"

    # 2. Leer mapping
    mappings = mappings_crud.get_mappings_by_project_orm(
        clean_db_session, encrypted_project["id"], encryption_key
    )

    assert len(mappings) == 1
    assert mappings[0]["origin_table"] == "users"
    assert mappings[0]["destination_table"] == "customers"

    # 3. Actualizar mapping
    mappings_crud.update_mapping_orm(
        clean_db_session,
        mapping["id"],
        "people",
        "person_id",
        "clients",
        "client_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # 4. Leer de nuevo
    mappings = mappings_crud.get_mappings_by_project_orm(
        clean_db_session, encrypted_project["id"], encryption_key
    )

    assert len(mappings) == 1
    assert mappings[0]["origin_table"] == "people"
    assert mappings[0]["destination_table"] == "clients"

    # 5. Eliminar
    mappings_crud.delete_mapping_orm(clean_db_session, mapping["id"], encrypted_project["owner_id"])

    # 6. Verificar eliminación
    mappings = mappings_crud.get_mappings_by_project_orm(
        clean_db_session, encrypted_project["id"], encryption_key
    )
    assert len(mappings) == 0


# ============================================================================
# TESTS DE EDGE CASES
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_create_mapping_with_special_characters(
    clean_db_session, encrypted_project, encryption_key
):
    """Test: Crear mapping con caracteres especiales"""
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "user_data.table",
        "user.id",
        "customer-data",
        "customer@id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    assert mapping["origin_table"] == "user_data.table"
    assert mapping["origin_column"] == "user.id"
    assert mapping["destination_table"] == "customer-data"
    assert mapping["destination_column"] == "customer@id"


@pytest.mark.integration
@pytest.mark.encryption
def test_create_mapping_with_unicode(clean_db_session, encrypted_project, encryption_key):
    """Test: Crear mapping con caracteres Unicode"""
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "usuarios",
        "identificación",
        "clientes",
        "客户ID",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Leer de vuelta
    mappings = mappings_crud.get_mappings_by_project_orm(
        clean_db_session, encrypted_project["id"], encryption_key
    )

    assert len(mappings) == 1
    assert mappings[0]["origin_table"] == "usuarios"
    assert mappings[0]["origin_column"] == "identificación"
    assert mappings[0]["destination_column"] == "客户ID"


@pytest.mark.integration
@pytest.mark.encryption
def test_create_mapping_with_long_text(clean_db_session, encrypted_project, encryption_key):
    """Test: Crear mapping con textos largos"""
    long_table_name = "a" * 200
    long_column_name = "b" * 200

    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        long_table_name,
        long_column_name,
        "destination",
        "dest_col",
        encrypted_project["owner_id"],
        encryption_key,
    )

    assert mapping["origin_table"] == long_table_name
    assert mapping["origin_column"] == long_column_name


@pytest.mark.integration
@pytest.mark.encryption
def test_multiple_mappings_same_tables(clean_db_session, encrypted_project, encryption_key):
    """Test: Múltiples mappings entre las mismas tablas (diferentes columnas)"""
    # Crear 3 mappings entre users y customers
    m1 = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    m2 = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "email",
        "customers",
        "customer_email",
        encrypted_project["owner_id"],
        encryption_key,
    )

    m3 = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "name",
        "customers",
        "customer_name",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Todos deben existir
    assert m1["id"] != m2["id"]
    assert m2["id"] != m3["id"]

    # Leer todos
    mappings = mappings_crud.get_mappings_by_project_orm(
        clean_db_session, encrypted_project["id"], encryption_key
    )

    assert len(mappings) == 3


@pytest.mark.integration
@pytest.mark.encryption
def test_mapping_encrypted_fields_not_visible_without_key(
    clean_db_session, encrypted_project, encryption_key
):
    """Test: Los campos encriptados no son visibles sin encryption_key"""
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Leer sin encryption_key
    mappings = mappings_crud.get_mappings_by_project_orm(
        clean_db_session, encrypted_project["id"], encryption_key=None
    )

    # Campos sensibles no deben estar visibles
    assert mappings[0]["origin_table"] is None
    assert mappings[0]["origin_column"] is None
    assert mappings[0]["destination_table"] is None
    assert mappings[0]["destination_column"] is None
    assert mappings[0]["is_encrypted"] is True


@pytest.mark.integration
@pytest.mark.encryption
def test_encrypted_fields_are_base64(clean_db_session, encrypted_project, encryption_key):
    """Test: Campos encriptados están en formato base64"""
    mapping = mappings_crud.create_mapping_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "id",
        "customers",
        "customer_id",
        encrypted_project["owner_id"],
        encryption_key,
    )

    import base64

    # Verificar que todos los campos encriptados son base64 válidos
    encrypted_fields = [
        "origin_table_encrypted",
        "origin_column_encrypted",
        "destination_table_encrypted",
        "destination_column_encrypted",
    ]

    for field in encrypted_fields:
        value = mapping.get(field)
        assert value is not None

        try:
            decoded = base64.b64decode(value)
            assert len(decoded) > 0
        except Exception:
            pytest.fail(f"{field} no es base64 válido")
