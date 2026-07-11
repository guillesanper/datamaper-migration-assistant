"""
Unit tests for versions_crud.py ORM functions

Tests para las 9 funciones ORM de versions_crud:
1. create_version_orm() - Test creación de versión con hash único
2. get_version_by_id_orm() - Test obtención por ID con JOIN
3. get_version_by_hash_orm() - Test obtención por hash (deduplicación)
4. get_version_history_orm() - Test historial con filtros y tags
5. get_project_versions_orm() - Test versiones de proyecto con filtros
6. get_next_version_number_orm() - Test cálculo de siguiente número
7. get_latest_version_orm() - Test obtención de versión más reciente
8. delete_version_orm() - Test eliminación de versión
9. get_versions_count_orm() - Test conteo de versiones

Estructura:
- Usa SessionLocal para crear sesiones de SQLAlchemy
- Fixtures para crear datos de prueba (usuarios, proyectos, entidades)
- Rollback automático después de cada test
- Snapshots únicos para evitar colisiones de hash
"""

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

# Importar TODOS los modelos ORM desde __init__ para que SQLAlchemy resuelva las relaciones
import app.models.orm as orm
from app.crud.versions_crud import (
    create_version_orm,
    delete_version_orm,
    get_latest_version_orm,
    get_next_version_number_orm,
    get_project_versions_orm,
    get_version_by_hash_orm,
    get_version_by_id_orm,
    get_version_history_orm,
    get_versions_count_orm,
)
from app.database.session import SessionLocal
from app.models.orm import EntityVersion, Project, User

# ============================================================================
# FIXTURES
# ============================================================================
# Nota: db_session fixture está definido en conftest.py


@pytest.fixture
def test_user(db_session):
    """
    Crea un usuario de prueba en la base de datos.

    Returns:
        User: Instancia del modelo User creada en la BD
    """
    user = User(
        id=uuid4(),
        username=f"test_user_{uuid4().hex[:8]}",
        email=f"test_{uuid4().hex[:8]}@example.com",
        password_hash="hashed_password_123",
        is_verified=True,
        is_deleted=False,
        failed_login_attempts=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_user2(db_session):
    """
    Crea un segundo usuario de prueba para tests con múltiples usuarios.

    Returns:
        User: Instancia del modelo User creada en la BD
    """
    user = User(
        id=uuid4(),
        username=f"test_user2_{uuid4().hex[:8]}",
        email=f"test2_{uuid4().hex[:8]}@example.com",
        password_hash="hashed_password_456",
        is_verified=True,
        is_deleted=False,
        failed_login_attempts=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_project(db_session, test_user):
    """
    Crea un proyecto de prueba en la base de datos.

    Returns:
        Project: Instancia del modelo Project creada en la BD
    """
    project = Project(
        id=uuid4(),
        name=f"Test Project {uuid4().hex[:8]}",
        description="Test project for versions",
        owner_id=test_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    db_session.commit()
    return project


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def generate_snapshot_hash(snapshot: dict) -> str:
    """
    Genera un hash SHA-256 de un snapshot para usar como hash único.

    Args:
        snapshot: Dict con los datos del snapshot

    Returns:
        str: Hash SHA-256 en hexadecimal
    """
    snapshot_json = json.dumps(snapshot, sort_keys=True)
    return hashlib.sha256(snapshot_json.encode()).hexdigest()


def create_unique_snapshot() -> dict:
    """
    Crea un snapshot único con timestamp para evitar colisiones de hash.

    Returns:
        dict: Snapshot único
    """
    return {
        "id": str(uuid4()),
        "name": f"Entity {uuid4().hex[:8]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"unique_value": uuid4().hex},
    }


# ============================================================================
# TESTS
# ============================================================================


def test_create_version_orm(db_session, test_user, test_project):
    """Test: create_version_orm crea una versión correctamente"""
    entity_id = str(uuid4())
    snapshot = create_unique_snapshot()
    hash_value = generate_snapshot_hash(snapshot)

    result = create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="mapping",
        user_id=str(test_user.id),
        version_number=1,
        change_type="create",
        snapshot=snapshot,
        hash=hash_value,
        message="Initial version",
    )

    assert result is not None
    assert result["entity_id"] == entity_id
    assert result["entity_type"] == "mapping"
    assert result["version_number"] == 1
    assert result["change_type"] == "create"
    assert result["hash"] == hash_value
    assert result["message"] == "Initial version"
    assert result["snapshot"] == snapshot


def test_create_version_with_diff_orm(db_session, test_user, test_project):
    """Test: create_version_orm con diff y parent_version_id"""
    entity_id = str(uuid4())

    # Crear versión inicial
    snapshot1 = create_unique_snapshot()
    hash1 = generate_snapshot_hash(snapshot1)

    version1 = create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="table",
        user_id=str(test_user.id),
        version_number=1,
        change_type="create",
        snapshot=snapshot1,
        hash=hash1,
    )

    # Crear versión 2 con diff
    snapshot2 = create_unique_snapshot()
    hash2 = generate_snapshot_hash(snapshot2)
    diff = {"changes": ["added field"]}

    version2 = create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="table",
        user_id=str(test_user.id),
        version_number=2,
        change_type="update",
        snapshot=snapshot2,
        hash=hash2,
        message="Updated table",
        diff=diff,
        parent_version_id=version1["id"],
    )

    assert version2 is not None
    assert version2["version_number"] == 2
    assert version2["diff"] == diff
    assert version2["parent_version_id"] == version1["id"]


def test_get_version_by_id_orm(db_session, test_user, test_project):
    """Test: get_version_by_id_orm devuelve versión con datos de usuario"""
    entity_id = str(uuid4())
    snapshot = create_unique_snapshot()
    hash_value = generate_snapshot_hash(snapshot)

    # Crear versión
    created = create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="column",
        user_id=str(test_user.id),
        version_number=1,
        change_type="create",
        snapshot=snapshot,
        hash=hash_value,
    )

    # Obtener por ID
    result = get_version_by_id_orm(db_session, created["id"])

    assert result is not None
    assert result["id"] == created["id"]
    assert result["entity_id"] == entity_id
    assert result["username"] == test_user.username
    assert result["user_email"] == test_user.email


def test_get_version_by_id_not_found_orm(db_session):
    """Test: get_version_by_id_orm devuelve None si no existe"""
    result = get_version_by_id_orm(db_session, str(uuid4()))
    assert result is None


def test_get_version_by_hash_orm(db_session, test_user, test_project):
    """Test: get_version_by_hash_orm encuentra versión por hash (deduplicación)"""
    entity_id = str(uuid4())
    snapshot = create_unique_snapshot()
    hash_value = generate_snapshot_hash(snapshot)

    # Crear versión
    created = create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="mapping",
        user_id=str(test_user.id),
        version_number=1,
        change_type="create",
        snapshot=snapshot,
        hash=hash_value,
    )

    # Buscar por hash
    result = get_version_by_hash_orm(db_session, hash_value)

    assert result is not None
    assert result["id"] == created["id"]
    assert result["hash"] == hash_value


def test_get_version_by_hash_not_found_orm(db_session):
    """Test: get_version_by_hash_orm devuelve None si hash no existe"""
    result = get_version_by_hash_orm(db_session, "nonexistent_hash")
    assert result is None


def test_get_version_history_orm(db_session, test_user, test_project):
    """Test: get_version_history_orm devuelve historial ordenado"""
    entity_id = str(uuid4())

    # Crear 3 versiones
    versions = []
    for i in range(1, 4):
        snapshot = create_unique_snapshot()
        hash_value = generate_snapshot_hash(snapshot)

        version = create_version_orm(
            db=db_session,
            project_id=str(test_project.id),
            entity_id=entity_id,
            entity_type="mapping",
            user_id=str(test_user.id),
            version_number=i,
            change_type="update" if i > 1 else "create",
            snapshot=snapshot,
            hash=hash_value,
            message=f"Version {i}",
        )
        versions.append(version)

    # Obtener historial
    result = get_version_history_orm(db_session, entity_id)

    assert len(result) == 3
    # Debe estar ordenado por created_at DESC
    assert result[0]["version_number"] == 3
    assert result[1]["version_number"] == 2
    assert result[2]["version_number"] == 1

    # Verificar que incluye username
    assert result[0]["username"] == test_user.username


def test_get_version_history_with_filters_orm(db_session, test_user, test_user2, test_project):
    """Test: get_version_history_orm con filtros de change_type y user_id"""
    entity_id = str(uuid4())

    # Crear versiones con diferentes change_type y users
    snapshot1 = create_unique_snapshot()
    hash1 = generate_snapshot_hash(snapshot1)
    create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="table",
        user_id=str(test_user.id),
        version_number=1,
        change_type="create",
        snapshot=snapshot1,
        hash=hash1,
    )

    snapshot2 = create_unique_snapshot()
    hash2 = generate_snapshot_hash(snapshot2)
    create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="table",
        user_id=str(test_user2.id),
        version_number=2,
        change_type="update",
        snapshot=snapshot2,
        hash=hash2,
    )

    snapshot3 = create_unique_snapshot()
    hash3 = generate_snapshot_hash(snapshot3)
    create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="table",
        user_id=str(test_user.id),
        version_number=3,
        change_type="update",
        snapshot=snapshot3,
        hash=hash3,
    )

    # Filtrar por change_type='update'
    updates = get_version_history_orm(db_session, entity_id, change_type="update")
    assert len(updates) == 2

    # Filtrar por user_id
    user1_versions = get_version_history_orm(db_session, entity_id, user_id=str(test_user.id))
    assert len(user1_versions) == 2


def test_get_version_history_pagination_orm(db_session, test_user, test_project):
    """Test: get_version_history_orm con limit y offset"""
    entity_id = str(uuid4())

    # Crear 5 versiones
    for i in range(1, 6):
        snapshot = create_unique_snapshot()
        hash_value = generate_snapshot_hash(snapshot)
        create_version_orm(
            db=db_session,
            project_id=str(test_project.id),
            entity_id=entity_id,
            entity_type="column",
            user_id=str(test_user.id),
            version_number=i,
            change_type="update",
            snapshot=snapshot,
            hash=hash_value,
        )

    # Primera página (2 items)
    page1 = get_version_history_orm(db_session, entity_id, limit=2, offset=0)
    assert len(page1) == 2
    assert page1[0]["version_number"] == 5  # Más reciente

    # Segunda página
    page2 = get_version_history_orm(db_session, entity_id, limit=2, offset=2)
    assert len(page2) == 2
    assert page2[0]["version_number"] == 3


def test_get_project_versions_orm(db_session, test_user, test_project):
    """Test: get_project_versions_orm devuelve todas las versiones del proyecto"""
    # Crear versiones para diferentes entidades
    for i in range(3):
        entity_id = str(uuid4())
        snapshot = create_unique_snapshot()
        hash_value = generate_snapshot_hash(snapshot)

        create_version_orm(
            db=db_session,
            project_id=str(test_project.id),
            entity_id=entity_id,
            entity_type="mapping",
            user_id=str(test_user.id),
            version_number=1,
            change_type="create",
            snapshot=snapshot,
            hash=hash_value,
        )

    # Obtener todas las versiones del proyecto
    result = get_project_versions_orm(db_session, str(test_project.id))

    assert len(result) == 3
    assert all(v["project_id"] == str(test_project.id) for v in result)


def test_get_project_versions_with_filters_orm(db_session, test_user, test_project):
    """Test: get_project_versions_orm con filtros de entity_type, change_type y user_id"""
    # Crear versiones con diferentes entity_type
    entity_id1 = str(uuid4())
    snapshot1 = create_unique_snapshot()
    hash1 = generate_snapshot_hash(snapshot1)
    create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id1,
        entity_type="mapping",
        user_id=str(test_user.id),
        version_number=1,
        change_type="create",
        snapshot=snapshot1,
        hash=hash1,
    )

    entity_id2 = str(uuid4())
    snapshot2 = create_unique_snapshot()
    hash2 = generate_snapshot_hash(snapshot2)
    create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id2,
        entity_type="table",
        user_id=str(test_user.id),
        version_number=1,
        change_type="create",
        snapshot=snapshot2,
        hash=hash2,
    )

    # Filtrar por entity_type
    mappings = get_project_versions_orm(db_session, str(test_project.id), entity_type="mapping")
    assert len(mappings) == 1
    assert mappings[0]["entity_type"] == "mapping"

    tables = get_project_versions_orm(db_session, str(test_project.id), entity_type="table")
    assert len(tables) == 1
    assert tables[0]["entity_type"] == "table"


def test_get_next_version_number_orm(db_session, test_user, test_project):
    """Test: get_next_version_number_orm calcula el siguiente número correctamente"""
    entity_id = str(uuid4())

    # Sin versiones previas, debe retornar 1
    next_num = get_next_version_number_orm(db_session, entity_id)
    assert next_num == 1

    # Crear versión 1
    snapshot1 = create_unique_snapshot()
    hash1 = generate_snapshot_hash(snapshot1)
    create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="mapping",
        user_id=str(test_user.id),
        version_number=1,
        change_type="create",
        snapshot=snapshot1,
        hash=hash1,
    )

    # Debe retornar 2
    next_num = get_next_version_number_orm(db_session, entity_id)
    assert next_num == 2

    # Crear versión 2
    snapshot2 = create_unique_snapshot()
    hash2 = generate_snapshot_hash(snapshot2)
    create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="mapping",
        user_id=str(test_user.id),
        version_number=2,
        change_type="update",
        snapshot=snapshot2,
        hash=hash2,
    )

    # Debe retornar 3
    next_num = get_next_version_number_orm(db_session, entity_id)
    assert next_num == 3


def test_get_latest_version_orm(db_session, test_user, test_project):
    """Test: get_latest_version_orm devuelve la versión más reciente"""
    entity_id = str(uuid4())

    # Sin versiones, debe retornar None
    result = get_latest_version_orm(db_session, entity_id)
    assert result is None

    # Crear 3 versiones
    versions = []
    for i in range(1, 4):
        snapshot = create_unique_snapshot()
        hash_value = generate_snapshot_hash(snapshot)

        version = create_version_orm(
            db=db_session,
            project_id=str(test_project.id),
            entity_id=entity_id,
            entity_type="table",
            user_id=str(test_user.id),
            version_number=i,
            change_type="update" if i > 1 else "create",
            snapshot=snapshot,
            hash=hash_value,
        )
        versions.append(version)

    # Obtener la más reciente
    latest = get_latest_version_orm(db_session, entity_id)

    assert latest is not None
    assert latest["version_number"] == 3
    assert latest["id"] == versions[2]["id"]
    assert latest["username"] == test_user.username


def test_delete_version_orm(db_session, test_user, test_project):
    """Test: delete_version_orm elimina versión correctamente"""
    entity_id = str(uuid4())
    snapshot = create_unique_snapshot()
    hash_value = generate_snapshot_hash(snapshot)

    # Crear versión
    version = create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="column",
        user_id=str(test_user.id),
        version_number=1,
        change_type="create",
        snapshot=snapshot,
        hash=hash_value,
    )

    # Verificar que existe
    found = get_version_by_id_orm(db_session, version["id"])
    assert found is not None

    # Eliminar
    deleted = delete_version_orm(db_session, version["id"])
    assert deleted is True

    # Verificar que ya no existe
    not_found = get_version_by_id_orm(db_session, version["id"])
    assert not_found is None


def test_delete_version_not_found_orm(db_session):
    """Test: delete_version_orm retorna False si versión no existe"""
    deleted = delete_version_orm(db_session, str(uuid4()))
    assert deleted is False


def test_get_versions_count_orm(db_session, test_user, test_project):
    """Test: get_versions_count_orm cuenta versiones correctamente"""
    entity_id = str(uuid4())

    # Sin versiones, debe retornar 0
    count = get_versions_count_orm(db_session, entity_id)
    assert count == 0

    # Crear 5 versiones
    for i in range(1, 6):
        snapshot = create_unique_snapshot()
        hash_value = generate_snapshot_hash(snapshot)
        create_version_orm(
            db=db_session,
            project_id=str(test_project.id),
            entity_id=entity_id,
            entity_type="mapping",
            user_id=str(test_user.id),
            version_number=i,
            change_type="update",
            snapshot=snapshot,
            hash=hash_value,
        )

    # Debe contar 5
    count = get_versions_count_orm(db_session, entity_id)
    assert count == 5


def test_get_versions_count_different_entities_orm(db_session, test_user, test_project):
    """Test: get_versions_count_orm cuenta solo versiones de la entidad especificada"""
    entity_id1 = str(uuid4())
    entity_id2 = str(uuid4())

    # Crear 3 versiones para entity_id1
    for i in range(1, 4):
        snapshot = create_unique_snapshot()
        hash_value = generate_snapshot_hash(snapshot)
        create_version_orm(
            db=db_session,
            project_id=str(test_project.id),
            entity_id=entity_id1,
            entity_type="table",
            user_id=str(test_user.id),
            version_number=i,
            change_type="update",
            snapshot=snapshot,
            hash=hash_value,
        )

    # Crear 2 versiones para entity_id2
    for i in range(1, 3):
        snapshot = create_unique_snapshot()
        hash_value = generate_snapshot_hash(snapshot)
        create_version_orm(
            db=db_session,
            project_id=str(test_project.id),
            entity_id=entity_id2,
            entity_type="column",
            user_id=str(test_user.id),
            version_number=i,
            change_type="update",
            snapshot=snapshot,
            hash=hash_value,
        )

    # Contar para cada entidad
    count1 = get_versions_count_orm(db_session, entity_id1)
    count2 = get_versions_count_orm(db_session, entity_id2)

    assert count1 == 3
    assert count2 == 2


def test_version_hash_uniqueness_orm(db_session, test_user, test_project):
    """Test: El hash debe ser único - no se puede crear versión con hash duplicado"""
    entity_id = str(uuid4())
    snapshot = create_unique_snapshot()
    hash_value = generate_snapshot_hash(snapshot)

    # Crear primera versión
    version1 = create_version_orm(
        db=db_session,
        project_id=str(test_project.id),
        entity_id=entity_id,
        entity_type="mapping",
        user_id=str(test_user.id),
        version_number=1,
        change_type="create",
        snapshot=snapshot,
        hash=hash_value,
    )

    assert version1 is not None

    # Intentar crear segunda versión con mismo hash (debe fallar)
    with pytest.raises(Exception):  # SQLAlchemy lanzará IntegrityError
        create_version_orm(
            db=db_session,
            project_id=str(test_project.id),
            entity_id=str(uuid4()),  # Diferente entity
            entity_type="mapping",
            user_id=str(test_user.id),
            version_number=1,
            change_type="create",
            snapshot=snapshot,
            hash=hash_value,  # Mismo hash - debe fallar
        )
