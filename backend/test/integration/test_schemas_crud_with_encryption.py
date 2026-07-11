# backend/test/integration/test_schemas_crud_with_encryption.py
"""
Tests de integración para operaciones CRUD de schemas (tablas y columnas) con encriptación

Cobertura:
- Crear/leer/actualizar/eliminar tablas con encriptación
- Crear/leer/actualizar/eliminar columnas con encriptación
- Validación de encryption_key requerida
- Roundtrip de encriptación/desencriptación
- Manejo de duplicados con nombres encriptados
- Búsqueda y filtrado de datos encriptados
"""

import pytest
from fastapi import HTTPException

from app.crud import master_key_crud, schemas_crud
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
# TESTS DE CREACIÓN DE TABLAS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_create_table_with_encryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Crear tabla con encriptación"""
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        name="users",
        type="origin",
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    assert table is not None
    assert table["name"] == "users"  # Nombre desencriptado en resultado
    assert table["is_encrypted"] is True
    assert table["name_encrypted"] is not None
    assert table["name_nonce"] is not None


@pytest.mark.integration
@pytest.mark.encryption
def test_create_table_without_key_fails(clean_db_session, encrypted_project):
    """Test: Crear tabla sin encryption_key en proyecto cifrado debe fallar"""
    with pytest.raises(HTTPException) as exc_info:
        schemas_crud.create_table_orm(
            clean_db_session,
            encrypted_project["id"],
            name="users",
            type="origin",
            user_id=encrypted_project["owner_id"],
            encryption_key=None,  # Sin clave
        )

    assert exc_info.value.status_code == 403
    assert "requiere encriptación" in exc_info.value.detail.lower()


@pytest.mark.integration
@pytest.mark.encryption
def test_create_table_duplicate_encrypted_names(
    clean_db_session, encrypted_project, encryption_key
):
    """Test: Crear tabla duplicada con nombre encriptado debe fallar"""
    # Crear primera tabla
    schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        name="users",
        type="origin",
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    # Intentar crear segunda tabla con mismo nombre
    with pytest.raises(HTTPException) as exc_info:
        schemas_crud.create_table_orm(
            clean_db_session,
            encrypted_project["id"],
            name="users",  # Mismo nombre
            type="origin",
            user_id=encrypted_project["owner_id"],
            encryption_key=encryption_key,
        )

    assert exc_info.value.status_code == 409
    assert "ya existe" in exc_info.value.detail.lower()


@pytest.mark.integration
@pytest.mark.encryption
def test_create_table_different_types_same_name(
    clean_db_session, encrypted_project, encryption_key
):
    """Test: Crear tablas con mismo nombre pero diferente tipo (origin/destination)"""
    # Crear tabla origin
    table1 = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        name="users",
        type="origin",
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    # Crear tabla destination con mismo nombre (debería permitirse)
    table2 = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        name="users",
        type="destination",
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    assert table1["name"] == "users"
    assert table2["name"] == "users"
    assert table1["type"] == "origin"
    assert table2["type"] == "destination"
    assert table1["id"] != table2["id"]


@pytest.mark.integration
@pytest.mark.encryption
def test_create_table_encrypted_name_is_base64(clean_db_session, encrypted_project, encryption_key):
    """Test: Nombre encriptado está en formato base64"""
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        name="users",
        type="origin",
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    import base64

    # Verificar que name_encrypted es base64 válido
    try:
        decoded = base64.b64decode(table["name_encrypted"])
        assert len(decoded) > 0
    except Exception:
        pytest.fail("name_encrypted no es base64 válido")


# ============================================================================
# TESTS DE LECTURA DE TABLAS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_get_tables_with_encryption_key(clean_db_session, encrypted_project, encryption_key):
    """Test: Leer tablas encriptadas con encryption_key"""
    # Crear 3 tablas
    schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )
    schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "products",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )
    schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "orders",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Leer todas las tablas
    tables = schemas_crud.get_tables_by_project_orm(
        clean_db_session,
        encrypted_project["id"],
        table_type="origin",
        encryption_key=encryption_key,
    )

    assert len(tables) == 3
    names = [t["name"] for t in tables]
    assert "users" in names
    assert "products" in names
    assert "orders" in names


@pytest.mark.integration
@pytest.mark.encryption
def test_get_tables_without_encryption_key(clean_db_session, encrypted_project):
    """Test: Leer tablas encriptadas sin encryption_key retorna datos cifrados"""
    encryption_key = EncryptionService.get_encryption_key(
        clean_db_session, encrypted_project["id"], encrypted_project["passphrase"]
    )

    # Crear tabla
    schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Leer sin encryption_key
    tables = schemas_crud.get_tables_by_project_orm(
        clean_db_session, encrypted_project["id"], table_type="origin", encryption_key=None
    )

    assert len(tables) == 1
    assert tables[0]["name"] is None  # Nombre no desencriptado
    assert tables[0]["name_encrypted"] is not None
    assert tables[0]["is_encrypted"] is True


@pytest.mark.integration
@pytest.mark.encryption
def test_get_table_by_id_with_decryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Obtener tabla por ID con desencriptación"""
    # Crear tabla
    created = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Obtener por ID con passphrase
    table = schemas_crud.get_table_by_id_orm(
        clean_db_session, created["id"], passphrase=encrypted_project["passphrase"]
    )

    assert table is not None
    assert table["name"] == "users"
    assert table["is_encrypted"] is True


# ============================================================================
# TESTS DE ACTUALIZACIÓN DE TABLAS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_update_table_with_encryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Actualizar nombre de tabla encriptada"""
    # Crear tabla
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Actualizar nombre
    updated = schemas_crud.update_table_orm(
        clean_db_session,
        table["id"],
        name="customers",
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    assert updated is not None
    assert updated["name"] == "customers"
    assert updated["is_encrypted"] is True
    assert updated["name_encrypted"] != table["name_encrypted"]  # Debe cambiar


@pytest.mark.integration
@pytest.mark.encryption
def test_update_table_roundtrip(clean_db_session, encrypted_project, encryption_key):
    """Test: Roundtrip de actualización (crear → actualizar → leer)"""
    # Crear
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Actualizar
    schemas_crud.update_table_orm(
        clean_db_session, table["id"], "customers", encrypted_project["owner_id"], encryption_key
    )

    # Leer
    tables = schemas_crud.get_tables_by_project_orm(
        clean_db_session, encrypted_project["id"], "origin", encryption_key
    )

    assert len(tables) == 1
    assert tables[0]["name"] == "customers"


# ============================================================================
# TESTS DE ELIMINACIÓN DE TABLAS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_delete_table_with_encryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Eliminar tabla encriptada"""
    # Crear tabla
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Eliminar
    deleted_info, column_names, mappings_count = schemas_crud.delete_table_orm(
        clean_db_session, table["id"], encrypted_project["owner_id"]
    )

    assert deleted_info is not None
    assert deleted_info["id"] == table["id"]

    # Verificar que ya no existe
    tables = schemas_crud.get_tables_by_project_orm(
        clean_db_session, encrypted_project["id"], "origin", encryption_key
    )
    assert len(tables) == 0


# ============================================================================
# TESTS DE CREACIÓN DE COLUMNAS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_create_column_with_encryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Crear columna con encriptación"""
    # Crear tabla primero
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Crear columna
    column = schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        name="email",
        data_type="VARCHAR(255)",
        table_type="origin",
        is_nullable=False,
        is_primary=False,
        is_autogenerated=False,
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    assert column is not None
    assert column["name"] == "email"
    assert column["data_type"] == "VARCHAR(255)"
    assert column["is_encrypted"] is True
    assert column["name_encrypted"] is not None
    assert column["data_type_encrypted"] is not None


@pytest.mark.integration
@pytest.mark.encryption
def test_create_column_without_key_fails(clean_db_session, encrypted_project, encryption_key):
    """Test: Crear columna sin encryption_key en tabla cifrada debe fallar"""
    # Crear tabla cifrada
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Intentar crear columna sin clave
    with pytest.raises(HTTPException) as exc_info:
        schemas_crud.create_column_orm(
            clean_db_session,
            table["id"],
            name="email",
            data_type="VARCHAR(255)",
            table_type="origin",
            is_nullable=True,
            is_primary=False,
            is_autogenerated=False,
            user_id=encrypted_project["owner_id"],
            encryption_key=None,  # Sin clave
        )

    assert exc_info.value.status_code == 403


@pytest.mark.integration
@pytest.mark.encryption
def test_create_multiple_columns_encrypted(clean_db_session, encrypted_project, encryption_key):
    """Test: Crear múltiples columnas encriptadas"""
    # Crear tabla
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Crear 3 columnas
    col1 = schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        "id",
        "INTEGER",
        "origin",
        False,
        True,
        False,
        encrypted_project["owner_id"],
        encryption_key,
    )
    col2 = schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        "email",
        "VARCHAR(255)",
        "origin",
        True,
        False,
        False,
        encrypted_project["owner_id"],
        encryption_key,
    )
    col3 = schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        "name",
        "VARCHAR(100)",
        "origin",
        True,
        False,
        False,
        encrypted_project["owner_id"],
        encryption_key,
    )

    assert col1["name"] == "id"
    assert col2["name"] == "email"
    assert col3["name"] == "name"

    # Verificar que todos tienen encriptación diferente
    assert col1["name_encrypted"] != col2["name_encrypted"]
    assert col2["name_encrypted"] != col3["name_encrypted"]


# ============================================================================
# TESTS DE LECTURA DE COLUMNAS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_get_columns_with_encryption_key(clean_db_session, encrypted_project, encryption_key):
    """Test: Leer columnas encriptadas con encryption_key"""
    # Crear tabla y columnas
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        "id",
        "INTEGER",
        "origin",
        False,
        True,
        False,
        encrypted_project["owner_id"],
        encryption_key,
    )
    schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        "email",
        "VARCHAR(255)",
        "origin",
        True,
        False,
        False,
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Leer columnas
    columns = schemas_crud.get_columns_by_table_orm(
        clean_db_session, table["id"], encryption_key=encryption_key
    )

    assert len(columns) == 2
    names = [c["name"] for c in columns]
    assert "id" in names
    assert "email" in names


@pytest.mark.integration
@pytest.mark.encryption
def test_get_columns_without_encryption_key(clean_db_session, encrypted_project, encryption_key):
    """Test: Leer columnas encriptadas sin encryption_key retorna datos cifrados"""
    # Crear tabla y columna
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        "email",
        "VARCHAR(255)",
        "origin",
        True,
        False,
        False,
        encrypted_project["owner_id"],
        encryption_key,
    )

    # Leer sin encryption_key
    columns = schemas_crud.get_columns_by_table_orm(
        clean_db_session, table["id"], encryption_key=None
    )

    assert len(columns) == 1
    assert columns[0]["name"] is None  # No desencriptado
    assert columns[0]["data_type"] is None  # No desencriptado
    assert columns[0]["name_encrypted"] is not None
    assert columns[0]["is_encrypted"] is True


# ============================================================================
# TESTS DE ACTUALIZACIÓN DE COLUMNAS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_update_column_with_encryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Actualizar columna encriptada"""
    # Crear tabla y columna
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    column = schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        name="email",
        data_type="VARCHAR(255)",
        table_type="origin",
        is_nullable=True,
        is_primary=False,
        is_autogenerated=False,
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    # Actualizar
    old_column_data, updated, mappings_renamed = schemas_crud.update_column_orm(
        clean_db_session,
        column["id"],
        name="user_email",
        data_type="TEXT",
        table_type="origin",
        is_nullable=True,
        is_primary=False,
        is_autogenerated=False,
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    assert updated is not None
    assert updated["name"] == "user_email"
    assert updated["data_type"] == "TEXT"
    assert updated["is_encrypted"] is True

    # old_column_data must carry the pre-update state (regression for missing fields)
    assert old_column_data is not None
    assert old_column_data["is_nullable"] is True
    assert old_column_data["is_primary"] is False
    assert old_column_data["is_autogenerated"] is False
    assert "created_at" in old_column_data
    assert "updated_at" in old_column_data


# ============================================================================
# TESTS DE ELIMINACIÓN DE COLUMNAS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_delete_column_with_encryption(clean_db_session, encrypted_project, encryption_key):
    """Test: Eliminar columna encriptada"""
    # Crear tabla y columna
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    column = schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        name="email",
        data_type="VARCHAR(255)",
        table_type="origin",
        is_nullable=True,
        is_primary=False,
        is_autogenerated=False,
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    # Eliminar
    deleted_info, mappings_deleted = schemas_crud.delete_column_orm(
        clean_db_session, column["id"], encrypted_project["owner_id"]
    )

    assert deleted_info is not None
    assert deleted_info["id"] == column["id"]

    # Verificar que ya no existe
    columns = schemas_crud.get_columns_by_table_orm(clean_db_session, table["id"], encryption_key)
    assert len(columns) == 0


# ============================================================================
# TESTS DE ROUNDTRIP
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_full_roundtrip_table_and_columns(clean_db_session, encrypted_project, encryption_key):
    """Test: Roundtrip completo de tabla y columnas"""
    # 1. Crear tabla
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )
    assert table["name"] == "users"

    # 2. Crear columnas
    col1 = schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        name="id",
        data_type="INTEGER",
        table_type="origin",
        is_nullable=False,
        is_primary=True,
        is_autogenerated=False,
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )
    col2 = schemas_crud.create_column_orm(
        clean_db_session,
        table["id"],
        name="email",
        data_type="VARCHAR(255)",
        table_type="origin",
        is_nullable=True,
        is_primary=False,
        is_autogenerated=False,
        user_id=encrypted_project["owner_id"],
        encryption_key=encryption_key,
    )

    # 3. Leer tabla
    tables = schemas_crud.get_tables_by_project_orm(
        clean_db_session, encrypted_project["id"], "origin", encryption_key
    )
    assert len(tables) == 1
    assert tables[0]["name"] == "users"

    # 4. Leer columnas
    columns = schemas_crud.get_columns_by_table_orm(clean_db_session, table["id"], encryption_key)
    assert len(columns) == 2
    column_names = [c["name"] for c in columns]
    assert "id" in column_names
    assert "email" in column_names

    # 5. Actualizar tabla
    schemas_crud.update_table_orm(
        clean_db_session, table["id"], "customers", encrypted_project["owner_id"], encryption_key
    )

    # 6. Verificar actualización
    tables = schemas_crud.get_tables_by_project_orm(
        clean_db_session, encrypted_project["id"], "origin", encryption_key
    )
    assert tables[0]["name"] == "customers"


# ============================================================================
# TESTS DE EDGE CASES
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_create_table_with_special_characters(clean_db_session, encrypted_project, encryption_key):
    """Test: Crear tabla con caracteres especiales en el nombre"""
    special_names = ["user_data", "User-Profile", "user.table", "users@2024", "Usuarios_Españoles"]

    for name in special_names:
        table = schemas_crud.create_table_orm(
            clean_db_session,
            encrypted_project["id"],
            name,
            "origin",
            encrypted_project["owner_id"],
            encryption_key,
        )
        assert table["name"] == name


@pytest.mark.integration
@pytest.mark.encryption
def test_create_column_with_complex_data_types(clean_db_session, encrypted_project, encryption_key):
    """Test: Crear columnas con tipos de datos complejos"""
    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        encrypted_project["owner_id"],
        encryption_key,
    )

    complex_types = [
        "VARCHAR(255)",
        "DECIMAL(10, 2)",
        "TIMESTAMP WITH TIME ZONE",
        "ARRAY[INTEGER]",
        "JSONB",
    ]

    for i, data_type in enumerate(complex_types):
        column = schemas_crud.create_column_orm(
            clean_db_session,
            table["id"],
            name=f"col_{i}",
            data_type=data_type,
            table_type="origin",
            is_nullable=True,
            is_primary=False,
            is_autogenerated=False,
            user_id=encrypted_project["owner_id"],
            encryption_key=encryption_key,
        )
        assert column["data_type"] == data_type


@pytest.mark.integration
@pytest.mark.encryption
def test_encryption_preserves_unicode(clean_db_session, encrypted_project, encryption_key):
    """Test: Encriptación preserva caracteres Unicode"""
    unicode_names = ["Usuarios", "日本語テーブル", "Таблица", "🔐secure_table"]

    for name in unicode_names:
        table = schemas_crud.create_table_orm(
            clean_db_session,
            encrypted_project["id"],
            name,
            "origin",
            encrypted_project["owner_id"],
            encryption_key,
        )

        # Leer de vuelta
        tables = schemas_crud.get_tables_by_project_orm(
            clean_db_session, encrypted_project["id"], "origin", encryption_key
        )

        # Verificar que el nombre se preserva correctamente
        assert name in [t["name"] for t in tables]
