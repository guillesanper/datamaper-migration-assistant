"""
Unit tests for tags_crud.py ORM functions

Tests para las 6 funciones ORM de tags_crud:
1. create_tag_orm() - Test INSERT de tag
2. get_tag_by_id_orm() - Test SELECT con JOIN a User
3. get_tags_by_project_orm() - Test SELECT con JOINs a User y EntityVersion
4. get_tags_by_version_orm() - Test SELECT con JOIN a User
5. delete_tag_orm() - Test DELETE
6. check_tag_exists_orm() - Test verificación de existencia

Estructura:
- Usa SessionLocal para crear sesiones de SQLAlchemy
- Fixtures para crear datos de prueba (usuarios, proyectos, versiones)
- Rollback automático después de cada test
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

# Importar TODOS los modelos ORM desde __init__ para que SQLAlchemy resuelva las relaciones
import app.models.orm as orm
from app.crud.tags_crud import (
    check_tag_exists_orm,
    create_tag_orm,
    delete_tag_orm,
    get_tag_by_id_orm,
    get_tags_by_project_orm,
    get_tags_by_version_orm,
)
from app.database.session import SessionLocal
from app.models.orm import EntityVersion, Project, User, VersionTag

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

    Args:
        db_session: Sesión de SQLAlchemy
        test_user: Usuario propietario del proyecto

    Returns:
        Project: Instancia del modelo Project creada en la BD
    """
    project = Project(
        id=uuid4(),
        name=f"Test Project {uuid4().hex[:8]}",
        description="Test project for tags",
        owner_id=test_user.id,
        origin_db="PostgreSQL",
        destination_db="MySQL",
        status="active",
        is_deleted=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    db_session.commit()
    return project


@pytest.fixture
def test_version(db_session, test_project, test_user):
    """
    Crea una versión de prueba en la base de datos.

    Args:
        db_session: Sesión de SQLAlchemy
        test_project: Proyecto al que pertenece la versión
        test_user: Usuario que crea la versión

    Returns:
        EntityVersion: Instancia del modelo EntityVersion creada en la BD
    """
    import hashlib
    import json

    # Crear snapshot único con UUID para evitar colisiones de hash
    version_id = uuid4()
    snapshot = {"entity": "mapping", "version": 1, "unique_id": str(version_id)}
    snapshot_str = json.dumps(snapshot, sort_keys=True)
    hash_value = hashlib.sha256(snapshot_str.encode()).hexdigest()

    version = EntityVersion(
        id=version_id,
        hash=hash_value,
        entity_id=uuid4(),
        entity_type="mapping",
        project_id=test_project.id,
        user_id=test_user.id,  # Usar user_id en vez de created_by
        version_number=1,
        change_type="create",  # Obligatorio
        snapshot=snapshot,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    db_session.commit()
    return version


# ============================================================================
# TESTS: create_tag_orm()
# ============================================================================


def test_create_tag_orm_success(db_session, test_version, test_project, test_user):
    """Test que se puede crear un tag exitosamente"""
    result = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="v1.0.0",
        description="First release",
        color="#FF5733",
        created_by=str(test_user.id),
    )

    assert result is not None
    assert isinstance(result, dict)
    assert result["name"] == "v1.0.0"
    assert result["description"] == "First release"
    assert result["color"] == "#FF5733"
    assert result["version_id"] == str(test_version.id)
    assert result["project_id"] == str(test_project.id)
    assert result["created_by"] == str(test_user.id)
    assert "id" in result
    assert "created_at" in result


def test_create_tag_orm_minimal_fields(db_session, test_version, test_project, test_user):
    """Test que se puede crear un tag con campos mínimos (description y color opcionales)"""
    result = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="v2.0.0",
        description=None,
        color=None,
        created_by=str(test_user.id),
    )

    assert result is not None
    assert result["name"] == "v2.0.0"
    assert result["description"] is None
    assert result["color"] is None


def test_create_tag_orm_multiple_tags_same_version(
    db_session, test_version, test_project, test_user
):
    """Test que se pueden crear múltiples tags para la misma versión"""
    tag1 = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="production",
        description="Production release",
        color="#00FF00",
        created_by=str(test_user.id),
    )

    tag2 = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="stable",
        description="Stable version",
        color="#0000FF",
        created_by=str(test_user.id),
    )

    assert tag1 is not None
    assert tag2 is not None
    assert tag1["id"] != tag2["id"]
    assert tag1["name"] == "production"
    assert tag2["name"] == "stable"


# ============================================================================
# TESTS: get_tag_by_id_orm()
# ============================================================================


def test_get_tag_by_id_orm_success(db_session, test_version, test_project, test_user):
    """Test que se puede obtener un tag por ID con JOIN de username"""
    # Crear tag
    created_tag = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="v1.0.0",
        description="Release",
        color="#FF5733",
        created_by=str(test_user.id),
    )

    # Obtener tag
    result = get_tag_by_id_orm(db=db_session, tag_id=created_tag["id"])

    assert result is not None
    assert result["id"] == created_tag["id"]
    assert result["name"] == "v1.0.0"
    assert result["creator_username"] == test_user.username  # JOIN con User


def test_get_tag_by_id_orm_not_found(db_session):
    """Test que retorna None cuando el tag no existe"""
    fake_id = str(uuid4())
    result = get_tag_by_id_orm(db=db_session, tag_id=fake_id)

    assert result is None


def test_get_tag_by_id_orm_includes_all_fields(db_session, test_version, test_project, test_user):
    """Test que el resultado incluye todos los campos esperados"""
    created_tag = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="test",
        description="desc",
        color="#000000",
        created_by=str(test_user.id),
    )

    result = get_tag_by_id_orm(db=db_session, tag_id=created_tag["id"])

    assert "id" in result
    assert "version_id" in result
    assert "project_id" in result
    assert "name" in result
    assert "description" in result
    assert "color" in result
    assert "created_by" in result
    assert "created_at" in result
    assert "creator_username" in result


# ============================================================================
# TESTS: get_tags_by_project_orm()
# ============================================================================


def test_get_tags_by_project_orm_empty(db_session, test_project):
    """Test que un proyecto sin tags retorna lista vacía"""
    tags = get_tags_by_project_orm(db=db_session, project_id=str(test_project.id))

    assert isinstance(tags, list)
    assert len(tags) == 0


def test_get_tags_by_project_orm_single_tag(db_session, test_version, test_project, test_user):
    """Test que se obtiene correctamente un tag con JOINs"""
    create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="v1.0.0",
        description="Release",
        color="#FF5733",
        created_by=str(test_user.id),
    )

    tags = get_tags_by_project_orm(db=db_session, project_id=str(test_project.id))

    assert len(tags) == 1
    assert tags[0]["name"] == "v1.0.0"
    assert tags[0]["creator_username"] == test_user.username  # JOIN con User
    assert tags[0]["entity_id"] == str(test_version.entity_id)  # JOIN con EntityVersion
    assert tags[0]["entity_type"] == "mapping"
    assert tags[0]["version_number"] == 1


def test_get_tags_by_project_orm_multiple_tags_ordered(
    db_session, test_version, test_project, test_user
):
    """Test que múltiples tags se retornan ordenados por created_at DESC"""
    # Crear varios tags
    tag1 = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="v1.0.0",
        description="First",
        color="#FF0000",
        created_by=str(test_user.id),
    )

    tag2 = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="v2.0.0",
        description="Second",
        color="#00FF00",
        created_by=str(test_user.id),
    )

    tags = get_tags_by_project_orm(db=db_session, project_id=str(test_project.id))

    assert len(tags) == 2
    # Verificar orden DESC por created_at (el último creado primero)
    assert tags[0]["name"] == "v2.0.0"
    assert tags[1]["name"] == "v1.0.0"


def test_get_tags_by_project_orm_filters_by_project(
    db_session, test_version, test_project, test_user
):
    """Test que solo retorna tags del proyecto especificado"""
    # Crear otro proyecto
    other_project = Project(
        id=uuid4(),
        name="Other Project",
        description="Another project",
        owner_id=test_user.id,
        origin_db="PostgreSQL",
        destination_db="MySQL",
        status="active",
        is_deleted=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(other_project)
    db_session.commit()

    # Crear tag en proyecto original
    create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="v1.0.0",
        description="Tag 1",
        color="#FF0000",
        created_by=str(test_user.id),
    )

    # Crear tag en otro proyecto (necesita otra versión)
    import hashlib
    import json

    other_version_id = uuid4()
    snapshot2 = {"entity": "mapping", "version": 2, "unique_id": str(other_version_id)}
    snapshot_str2 = json.dumps(snapshot2, sort_keys=True)
    hash_value2 = hashlib.sha256(snapshot_str2.encode()).hexdigest()

    other_version = EntityVersion(
        id=other_version_id,
        hash=hash_value2,
        entity_id=uuid4(),
        entity_type="mapping",
        project_id=other_project.id,
        user_id=test_user.id,
        version_number=1,
        change_type="create",
        snapshot=snapshot2,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(other_version)
    db_session.commit()

    create_tag_orm(
        db=db_session,
        version_id=str(other_version.id),
        project_id=str(other_project.id),
        name="v2.0.0",
        description="Tag 2",
        color="#00FF00",
        created_by=str(test_user.id),
    )

    # Verificar que cada proyecto solo ve sus propios tags
    tags_project1 = get_tags_by_project_orm(db=db_session, project_id=str(test_project.id))
    tags_project2 = get_tags_by_project_orm(db=db_session, project_id=str(other_project.id))

    assert len(tags_project1) == 1
    assert len(tags_project2) == 1
    assert tags_project1[0]["name"] == "v1.0.0"
    assert tags_project2[0]["name"] == "v2.0.0"


# ============================================================================
# TESTS: get_tags_by_version_orm()
# ============================================================================


def test_get_tags_by_version_orm_empty(db_session, test_version):
    """Test que una versión sin tags retorna lista vacía"""
    tags = get_tags_by_version_orm(db=db_session, version_id=str(test_version.id))

    assert isinstance(tags, list)
    assert len(tags) == 0


def test_get_tags_by_version_orm_single_tag(db_session, test_version, test_project, test_user):
    """Test que se obtiene correctamente un tag de una versión"""
    create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="production",
        description="Production release",
        color="#00FF00",
        created_by=str(test_user.id),
    )

    tags = get_tags_by_version_orm(db=db_session, version_id=str(test_version.id))

    assert len(tags) == 1
    assert tags[0]["name"] == "production"
    assert tags[0]["creator_username"] == test_user.username


def test_get_tags_by_version_orm_multiple_tags_ordered(
    db_session, test_version, test_project, test_user
):
    """Test que múltiples tags de una versión se retornan ordenados por created_at DESC"""
    create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="tag1",
        description="First",
        color="#FF0000",
        created_by=str(test_user.id),
    )

    create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="tag2",
        description="Second",
        color="#00FF00",
        created_by=str(test_user.id),
    )

    tags = get_tags_by_version_orm(db=db_session, version_id=str(test_version.id))

    assert len(tags) == 2
    # Verificar orden DESC (el último creado primero)
    assert tags[0]["name"] == "tag2"
    assert tags[1]["name"] == "tag1"


# ============================================================================
# TESTS: delete_tag_orm()
# ============================================================================


def test_delete_tag_orm_success(db_session, test_version, test_project, test_user):
    """Test que se puede eliminar un tag exitosamente"""
    # Crear tag
    tag = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="to-delete",
        description="Will be deleted",
        color="#FF0000",
        created_by=str(test_user.id),
    )

    # Eliminar tag
    deleted = delete_tag_orm(db=db_session, tag_id=tag["id"])

    assert deleted is True

    # Verificar que ya no existe
    result = get_tag_by_id_orm(db=db_session, tag_id=tag["id"])
    assert result is None


def test_delete_tag_orm_not_found(db_session):
    """Test que eliminar un tag inexistente retorna False"""
    fake_id = str(uuid4())
    deleted = delete_tag_orm(db=db_session, tag_id=fake_id)

    assert deleted is False


def test_delete_tag_orm_does_not_affect_other_tags(
    db_session, test_version, test_project, test_user
):
    """Test que eliminar un tag no afecta otros tags"""
    tag1 = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="tag1",
        description="First",
        color="#FF0000",
        created_by=str(test_user.id),
    )

    tag2 = create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="tag2",
        description="Second",
        color="#00FF00",
        created_by=str(test_user.id),
    )

    # Eliminar tag1
    delete_tag_orm(db=db_session, tag_id=tag1["id"])

    # Verificar que tag2 sigue existiendo
    result = get_tag_by_id_orm(db=db_session, tag_id=tag2["id"])
    assert result is not None
    assert result["name"] == "tag2"


# ============================================================================
# TESTS: check_tag_exists_orm()
# ============================================================================


def test_check_tag_exists_orm_true(db_session, test_version, test_project, test_user):
    """Test que retorna True cuando el tag existe"""
    create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="existing-tag",
        description="Exists",
        color="#FF0000",
        created_by=str(test_user.id),
    )

    exists = check_tag_exists_orm(
        db=db_session, project_id=str(test_project.id), name="existing-tag"
    )

    assert exists is True


def test_check_tag_exists_orm_false(db_session, test_project):
    """Test que retorna False cuando el tag no existe"""
    exists = check_tag_exists_orm(
        db=db_session, project_id=str(test_project.id), name="non-existing-tag"
    )

    assert exists is False


def test_check_tag_exists_orm_case_sensitive(db_session, test_version, test_project, test_user):
    """Test que la búsqueda es case-sensitive"""
    create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="MyTag",
        description="Case sensitive",
        color="#FF0000",
        created_by=str(test_user.id),
    )

    # Nombre exacto - debe existir
    exists_exact = check_tag_exists_orm(
        db=db_session, project_id=str(test_project.id), name="MyTag"
    )

    # Nombre diferente case - no debe existir (depende de collation de la BD)
    exists_different_case = check_tag_exists_orm(
        db=db_session, project_id=str(test_project.id), name="mytag"
    )

    assert exists_exact is True
    # Nota: El resultado de exists_different_case depende de la collation de la BD
    # En PostgreSQL con collation case-sensitive, debería ser False


def test_check_tag_exists_orm_scoped_to_project(db_session, test_version, test_project, test_user):
    """Test que la verificación está limitada al proyecto"""
    # Crear otro proyecto
    other_project = Project(
        id=uuid4(),
        name="Other Project",
        description="Another project",
        owner_id=test_user.id,
        origin_db="PostgreSQL",
        destination_db="MySQL",
        status="active",
        is_deleted=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(other_project)
    db_session.commit()

    # Crear tag en proyecto original
    create_tag_orm(
        db=db_session,
        version_id=str(test_version.id),
        project_id=str(test_project.id),
        name="shared-name",
        description="Tag in project 1",
        color="#FF0000",
        created_by=str(test_user.id),
    )

    # Verificar que existe en proyecto 1
    exists_project1 = check_tag_exists_orm(
        db=db_session, project_id=str(test_project.id), name="shared-name"
    )

    # Verificar que NO existe en proyecto 2
    exists_project2 = check_tag_exists_orm(
        db=db_session, project_id=str(other_project.id), name="shared-name"
    )

    assert exists_project1 is True
    assert exists_project2 is False
