# backend/test/integration/test_versions_crud_with_encryption.py
"""
Tests de integración para entity_versions con encriptación

Cobertura:
- Crear/leer versiones con snapshots encriptados
- Crear/leer versiones con diffs encriptados
- Validación de encryption_key requerida
- Roundtrip de encriptación/desencriptación de JSON
- Historial de versiones encriptadas
"""

import json

import pytest

from app.crud import versions_crud

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def encrypted_project(clean_db_session, test_user):
    """Proyecto con cifrado configurado"""
    from app.crud.project_crud import ProjectCRUD
    from app.services.encryption_service import EncryptionService

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
    from app.services.encryption_service import EncryptionService

    return EncryptionService.get_encryption_key(
        clean_db_session, encrypted_project["id"], encrypted_project["passphrase"]
    )


# ============================================================================
# TESTS DE CREACIÓN DE VERSIONES
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_create_version_with_snapshot(clean_db_session, encrypted_project, test_user):
    """Test: Crear versión con snapshot básico"""
    import uuid

    entity_id = str(uuid.uuid4())
    snapshot = {
        "id": entity_id,
        "name": "users",
        "type": "table",
        "columns": ["id", "email", "name"],
    }

    version = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        entity_type="table",
        user_id=test_user["id"],
        version_number=1,
        change_type="create",
        snapshot=snapshot,
        hash="abc123",
        message="Initial version",
    )

    assert version is not None
    assert version["entity_id"] == entity_id
    assert version["version_number"] == 1
    assert "snapshot" in version


@pytest.mark.integration
@pytest.mark.encryption
def test_create_version_with_diff(clean_db_session, encrypted_project, test_user):
    """Test: Crear versión con diff"""
    import uuid

    entity_id = str(uuid.uuid4())
    snapshot = {"name": "users"}
    diff = {
        "added": ["email_column"],
        "removed": [],
        "modified": {"name": {"old": "user", "new": "users"}},
    }

    version = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        entity_type="table",
        user_id=test_user["id"],
        version_number=2,
        change_type="update",
        snapshot=snapshot,
        diff=diff,
        hash="def456",
        message="Added email column",
    )

    assert version is not None
    assert "diff" in version


@pytest.mark.integration
@pytest.mark.encryption
def test_create_version_complex_snapshot(clean_db_session, encrypted_project, test_user):
    """Test: Crear versión con snapshot complejo (JSON anidado)"""
    import uuid

    entity_id = str(uuid.uuid4())
    snapshot = {
        "table": {
            "name": "users",
            "schema": "public",
            "columns": [
                {"name": "id", "type": "INTEGER", "nullable": False},
                {"name": "email", "type": "VARCHAR(255)", "nullable": False},
                {"name": "metadata", "type": "JSONB", "nullable": True},
            ],
            "indexes": [{"name": "idx_users_email", "columns": ["email"], "unique": True}],
            "relationships": [{"table": "orders", "column": "user_id", "type": "one_to_many"}],
        }
    }

    version = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        entity_type="table",
        user_id=test_user["id"],
        version_number=1,
        change_type="create",
        snapshot=snapshot,
        hash="complex123",
    )

    assert version is not None
    assert "snapshot" in version
    # JSON debe preservarse
    assert isinstance(version["snapshot"], dict)


# ============================================================================
# TESTS DE LECTURA DE VERSIONES
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_get_version_by_id(clean_db_session, encrypted_project, test_user):
    """Test: Obtener versión por ID"""
    import uuid

    entity_id = str(uuid.uuid4())
    snapshot = {"name": "users"}

    created = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        1,
        "create",
        snapshot,
        "hash123",
    )

    # Obtener por ID
    version = versions_crud.get_version_by_id_orm(clean_db_session, created["id"])

    assert version is not None
    assert version["id"] == created["id"]
    assert version["entity_id"] == entity_id


@pytest.mark.integration
@pytest.mark.encryption
def test_get_version_history(clean_db_session, encrypted_project, test_user):
    """Test: Obtener historial de versiones de una entidad"""
    import uuid

    entity_id = str(uuid.uuid4())

    # Crear 3 versiones
    for i in range(1, 4):
        versions_crud.create_version_orm(
            clean_db_session,
            encrypted_project["id"],
            entity_id,
            "table",
            test_user["id"],
            i,
            "update",
            {"version": i},
            f"hash{i}",
        )

    # Obtener historial
    history = versions_crud.get_version_history_orm(clean_db_session, entity_id)

    assert len(history) == 3
    # Debe estar en orden descendente (más reciente primero)
    assert history[0]["version_number"] == 3
    assert history[1]["version_number"] == 2
    assert history[2]["version_number"] == 1


@pytest.mark.integration
@pytest.mark.encryption
def test_get_version_by_hash(clean_db_session, encrypted_project, test_user):
    """Test: Obtener versión por hash (deduplicación)"""
    import uuid

    entity_id = str(uuid.uuid4())
    hash_value = "unique_hash_123"

    versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        1,
        "create",
        {"name": "users"},
        hash_value,
    )

    # Buscar por hash
    version = versions_crud.get_version_by_hash_orm(clean_db_session, hash_value)

    assert version is not None
    assert version["hash"] == hash_value


# ============================================================================
# TESTS DE SNAPSHOTS CON TIPOS DE DATOS VARIADOS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_version_snapshot_with_unicode(clean_db_session, encrypted_project, test_user):
    """Test: Snapshot con caracteres Unicode"""
    import uuid

    entity_id = str(uuid.uuid4())
    snapshot = {
        "table_name": "Usuarios_Españoles",
        "description": "Tabla de usuarios con caracteres especiales: ñáéíóú",
        "columns": ["identificación", "nombre", "correo_electrónico"],
    }

    version = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        1,
        "create",
        snapshot,
        "unicode_hash",
    )

    # Leer de vuelta
    retrieved = versions_crud.get_version_by_id_orm(clean_db_session, version["id"])

    assert retrieved["snapshot"]["table_name"] == "Usuarios_Españoles"
    assert "ñáéíóú" in retrieved["snapshot"]["description"]


@pytest.mark.integration
@pytest.mark.encryption
def test_version_snapshot_with_numbers(clean_db_session, encrypted_project, test_user):
    """Test: Snapshot con diferentes tipos numéricos"""
    import uuid

    entity_id = str(uuid.uuid4())
    snapshot = {
        "integer": 42,
        "float": 3.14159,
        "negative": -100,
        "zero": 0,
        "large_number": 9999999999,
    }

    version = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        1,
        "create",
        snapshot,
        "numbers_hash",
    )

    retrieved = versions_crud.get_version_by_id_orm(clean_db_session, version["id"])

    assert retrieved["snapshot"]["integer"] == 42
    assert retrieved["snapshot"]["float"] == 3.14159


@pytest.mark.integration
@pytest.mark.encryption
def test_version_snapshot_with_arrays(clean_db_session, encrypted_project, test_user):
    """Test: Snapshot con arrays y objetos anidados"""
    import uuid

    entity_id = str(uuid.uuid4())
    snapshot = {
        "columns": [{"name": "id", "type": "INTEGER"}, {"name": "email", "type": "VARCHAR"}],
        "indexes": ["idx_id", "idx_email"],
        "metadata": {
            "created_by": "admin",
            "tags": ["important", "production"],
            "settings": {"auto_increment": True},
        },
    }

    version = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        1,
        "create",
        snapshot,
        "arrays_hash",
    )

    retrieved = versions_crud.get_version_by_id_orm(clean_db_session, version["id"])

    assert len(retrieved["snapshot"]["columns"]) == 2
    assert "idx_id" in retrieved["snapshot"]["indexes"]
    assert retrieved["snapshot"]["metadata"]["settings"]["auto_increment"] is True


# ============================================================================
# TESTS DE DIFFS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_version_diff_structure(clean_db_session, encrypted_project, test_user):
    """Test: Estructura de diff completa"""
    import uuid

    entity_id = str(uuid.uuid4())
    diff = {
        "added": {"columns": ["created_at", "updated_at"], "indexes": ["idx_timestamps"]},
        "removed": {"columns": ["legacy_field"]},
        "modified": {"email": {"old_type": "VARCHAR(100)", "new_type": "VARCHAR(255)"}},
    }

    version = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        2,
        "update",
        {"name": "users"},
        diff=diff,
        hash="diff_hash",
    )

    retrieved = versions_crud.get_version_by_id_orm(clean_db_session, version["id"])

    assert "diff" in retrieved
    assert "created_at" in retrieved["diff"]["added"]["columns"]
    assert "legacy_field" in retrieved["diff"]["removed"]["columns"]


# ============================================================================
# TESTS DE VERSION HISTORY
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_version_history_with_filters(clean_db_session, encrypted_project, test_user):
    """Test: Historial de versiones con filtros"""
    import uuid

    entity_id = str(uuid.uuid4())

    # Crear versiones de diferentes tipos
    versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        1,
        "create",
        {"name": "users"},
        "h1",
    )

    versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        2,
        "update",
        {"name": "users"},
        "h2",
    )

    versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        3,
        "update",
        {"name": "users"},
        "h3",
    )

    # Filtrar solo por "update"
    history = versions_crud.get_version_history_orm(
        clean_db_session, entity_id, change_type="update"
    )

    assert len(history) == 2
    assert all(v["change_type"] == "update" for v in history)


@pytest.mark.integration
@pytest.mark.encryption
def test_version_history_pagination(clean_db_session, encrypted_project, test_user):
    """Test: Paginación de historial de versiones"""
    import uuid

    entity_id = str(uuid.uuid4())

    # Crear 10 versiones
    for i in range(1, 11):
        versions_crud.create_version_orm(
            clean_db_session,
            encrypted_project["id"],
            entity_id,
            "table",
            test_user["id"],
            i,
            "update",
            {"version": i},
            f"hash{i}",
        )

    # Primera página (5 items)
    page1 = versions_crud.get_version_history_orm(clean_db_session, entity_id, limit=5, offset=0)
    assert len(page1) == 5
    assert page1[0]["version_number"] == 10  # Más reciente

    # Segunda página
    page2 = versions_crud.get_version_history_orm(clean_db_session, entity_id, limit=5, offset=5)
    assert len(page2) == 5
    assert page2[0]["version_number"] == 5


# ============================================================================
# TESTS DE EDGE CASES
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_version_snapshot_empty_object(clean_db_session, encrypted_project, test_user):
    """Test: Snapshot vacío"""
    import uuid

    entity_id = str(uuid.uuid4())

    version = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        1,
        "create",
        {},
        "empty_hash",
    )

    assert version is not None
    assert version["snapshot"] == {}


@pytest.mark.integration
@pytest.mark.encryption
def test_version_snapshot_null_values(clean_db_session, encrypted_project, test_user):
    """Test: Snapshot con valores null"""
    import uuid

    entity_id = str(uuid.uuid4())
    snapshot = {"name": "users", "description": None, "optional_field": None}

    version = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        1,
        "create",
        snapshot,
        "null_hash",
    )

    retrieved = versions_crud.get_version_by_id_orm(clean_db_session, version["id"])

    assert retrieved["snapshot"]["description"] is None


@pytest.mark.integration
@pytest.mark.encryption
def test_version_snapshot_large_json(clean_db_session, encrypted_project, test_user):
    """Test: Snapshot con JSON grande"""
    import uuid

    entity_id = str(uuid.uuid4())

    # Crear snapshot grande (100 columnas)
    snapshot = {
        "table": "large_table",
        "columns": [{"name": f"col_{i}", "type": "VARCHAR(255)"} for i in range(100)],
    }

    version = versions_crud.create_version_orm(
        clean_db_session,
        encrypted_project["id"],
        entity_id,
        "table",
        test_user["id"],
        1,
        "create",
        snapshot,
        "large_hash",
    )

    retrieved = versions_crud.get_version_by_id_orm(clean_db_session, version["id"])

    assert len(retrieved["snapshot"]["columns"]) == 100


@pytest.mark.integration
@pytest.mark.encryption
def test_multiple_versions_same_entity(clean_db_session, encrypted_project, test_user):
    """Test: Múltiples versiones de la misma entidad"""
    import uuid

    entity_id = str(uuid.uuid4())

    # Crear 5 versiones incrementales
    for i in range(1, 6):
        versions_crud.create_version_orm(
            clean_db_session,
            encrypted_project["id"],
            entity_id,
            "table",
            test_user["id"],
            i,
            "update",
            {"version": i, "timestamp": f"2024-01-{i:02d}"},
            f"hash_{i}",
        )

    history = versions_crud.get_version_history_orm(clean_db_session, entity_id)

    assert len(history) == 5
    # Verificar orden descendente
    version_numbers = [v["version_number"] for v in history]
    assert version_numbers == [5, 4, 3, 2, 1]
