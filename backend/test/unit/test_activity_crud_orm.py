"""
Unit tests for activity_crud.py ORM functions

Tests para las 6 funciones ORM de activity_crud:
1. create_activity_log_orm() - Test INSERT con campo especial activity_metadata
2. get_project_activity_orm() - Test SELECT con filtros opcionales y JOIN
3. get_entity_activity_orm() - Test SELECT por entidad
4. get_user_activity_orm() - Test SELECT por usuario
5. get_activity_stats_orm() - Test GROUP BY para estadísticas
6. delete_old_activity_orm() - Test DELETE con filtro de fecha

IMPORTANTE: El modelo ProjectActivity tiene un campo especial:
- En Python: activity_metadata
- En dict retornado: 'metadata'

Estructura:
- Usa SessionLocal para crear sesiones de SQLAlchemy
- Fixtures para crear datos de prueba (usuarios, proyectos)
- Rollback automático después de cada test
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

# Importar TODOS los modelos ORM desde __init__ para que SQLAlchemy resuelva las relaciones
import app.models.orm as orm
from app.crud.activity_crud import (
    create_activity_log_orm,
    delete_old_activity_orm,
    get_activity_stats_orm,
    get_entity_activity_orm,
    get_project_activity_orm,
    get_user_activity_orm,
)
from app.database.session import SessionLocal
from app.models.orm import Project, ProjectActivity, User

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
        description="Test project for activity",
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


# ============================================================================
# TESTS: create_activity_log_orm()
# ============================================================================


def test_create_activity_log_orm_success(db_session, test_project, test_user):
    """Test que se puede crear un log de actividad exitosamente"""
    result = create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="version_created",
        description="Created version 1.0.0",
        entity_id=str(uuid4()),
        entity_type="version",
        metadata={"version": "1.0.0", "changes": "Initial release"},
    )

    assert result is not None
    assert isinstance(result, dict)
    assert result["project_id"] == str(test_project.id)
    assert result["user_id"] == str(test_user.id)
    assert result["activity_type"] == "version_created"
    assert result["description"] == "Created version 1.0.0"
    assert "metadata" in result  # IMPORTANTE: Clave 'metadata' (no 'activity_metadata')
    assert result["metadata"]["version"] == "1.0.0"
    assert result["metadata"]["changes"] == "Initial release"
    assert "id" in result
    assert "created_at" in result


def test_create_activity_log_orm_metadata_mapping(db_session, test_project, test_user):
    """
    Test CRÍTICO: Verificar que activity_metadata se mapea correctamente a 'metadata'
    en el dict retornado
    """
    result = create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="comment_added",
        description="Added comment",
        metadata={"comment_id": "abc123", "text": "Great work!"},
    )

    # Verificar que el dict retornado tiene la clave 'metadata', no 'activity_metadata'
    assert "metadata" in result
    assert "activity_metadata" not in result
    assert result["metadata"]["comment_id"] == "abc123"
    assert result["metadata"]["text"] == "Great work!"


def test_create_activity_log_orm_minimal_fields(db_session, test_project, test_user):
    """Test que se puede crear actividad con campos mínimos (sin entity_id, entity_type, metadata)"""
    result = create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="member_added",
        description="Added new member",
        entity_id=None,
        entity_type=None,
        metadata=None,
    )

    assert result is not None
    assert result["entity_id"] is None
    assert result["entity_type"] is None
    assert result["metadata"] is None


def test_create_activity_log_orm_complex_metadata(db_session, test_project, test_user):
    """Test que se puede almacenar metadata complejo en JSONB"""
    complex_metadata = {
        "action": "update",
        "changes": {
            "field1": {"old": "value1", "new": "value2"},
            "field2": {"old": 100, "new": 200},
        },
        "tags": ["important", "urgent"],
        "count": 42,
        "nested": {"deep": {"value": True}},
    }

    result = create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="data_updated",
        description="Updated data",
        metadata=complex_metadata,
    )

    assert result["metadata"] == complex_metadata
    assert result["metadata"]["changes"]["field1"]["new"] == "value2"
    assert result["metadata"]["tags"] == ["important", "urgent"]
    assert result["metadata"]["nested"]["deep"]["value"] is True


# ============================================================================
# TESTS: get_project_activity_orm()
# ============================================================================


def test_get_project_activity_orm_empty(db_session, test_project):
    """Test que un proyecto sin actividad retorna lista vacía"""
    activities = get_project_activity_orm(db=db_session, project_id=str(test_project.id))

    assert isinstance(activities, list)
    assert len(activities) == 0


def test_get_project_activity_orm_single_activity(db_session, test_project, test_user):
    """Test que se obtiene correctamente una actividad con JOIN de username"""
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="version_created",
        description="Created version",
        metadata={"version": "1.0.0"},
    )

    activities = get_project_activity_orm(db=db_session, project_id=str(test_project.id))

    assert len(activities) == 1
    assert activities[0]["activity_type"] == "version_created"
    assert activities[0]["username"] == test_user.username  # JOIN con User
    assert activities[0]["user_email"] == test_user.email  # JOIN con User
    assert activities[0]["metadata"]["version"] == "1.0.0"  # Metadata mapeado


def test_get_project_activity_orm_pagination(db_session, test_project, test_user):
    """Test que la paginación funciona correctamente con limit y offset"""
    # Crear 5 actividades
    for i in range(5):
        create_activity_log_orm(
            db=db_session,
            project_id=str(test_project.id),
            user_id=str(test_user.id),
            activity_type="test",
            description=f"Activity {i}",
        )

    # Primera página (2 elementos)
    page1 = get_project_activity_orm(
        db=db_session, project_id=str(test_project.id), limit=2, offset=0
    )

    # Segunda página (2 elementos)
    page2 = get_project_activity_orm(
        db=db_session, project_id=str(test_project.id), limit=2, offset=2
    )

    assert len(page1) == 2
    assert len(page2) == 2
    # Verificar que son diferentes
    assert page1[0]["id"] != page2[0]["id"]


def test_get_project_activity_orm_filter_by_activity_type(db_session, test_project, test_user):
    """Test que el filtro por activity_type funciona"""
    # Crear actividades de diferentes tipos
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="version_created",
        description="Version created",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="comment_added",
        description="Comment added",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="version_created",
        description="Another version",
    )

    # Filtrar solo version_created
    filtered = get_project_activity_orm(
        db=db_session, project_id=str(test_project.id), activity_type="version_created"
    )

    assert len(filtered) == 2
    assert all(a["activity_type"] == "version_created" for a in filtered)


def test_get_project_activity_orm_filter_by_entity_id(db_session, test_project, test_user):
    """Test que el filtro por entity_id funciona"""
    entity_id1 = str(uuid4())
    entity_id2 = str(uuid4())

    # Crear actividades con diferentes entity_ids
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="Update 1",
        entity_id=entity_id1,
        entity_type="mapping",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="Update 2",
        entity_id=entity_id2,
        entity_type="mapping",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="Update 3",
        entity_id=entity_id1,
        entity_type="mapping",
    )

    # Filtrar por entity_id1
    filtered = get_project_activity_orm(
        db=db_session, project_id=str(test_project.id), entity_id=entity_id1
    )

    assert len(filtered) == 2
    assert all(a["entity_id"] == entity_id1 for a in filtered)


def test_get_project_activity_orm_ordered_by_created_at_desc(db_session, test_project, test_user):
    """Test que las actividades se retornan ordenadas por created_at DESC"""
    # Crear actividades (la última creada debería aparecer primero)
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="test",
        description="First",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="test",
        description="Second",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="test",
        description="Third",
    )

    activities = get_project_activity_orm(db=db_session, project_id=str(test_project.id))

    # La más reciente primero
    assert activities[0]["description"] == "Third"
    assert activities[1]["description"] == "Second"
    assert activities[2]["description"] == "First"


# ============================================================================
# TESTS: get_entity_activity_orm()
# ============================================================================


def test_get_entity_activity_orm_empty(db_session):
    """Test que una entidad sin actividad retorna lista vacía"""
    activities = get_entity_activity_orm(
        db=db_session, entity_id=str(uuid4()), entity_type="mapping"
    )

    assert isinstance(activities, list)
    assert len(activities) == 0


def test_get_entity_activity_orm_single_entity(db_session, test_project, test_user):
    """Test que se obtiene actividad de una entidad específica"""
    entity_id = str(uuid4())

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="Updated mapping",
        entity_id=entity_id,
        entity_type="mapping",
    )

    activities = get_entity_activity_orm(db=db_session, entity_id=entity_id, entity_type="mapping")

    assert len(activities) == 1
    assert activities[0]["entity_id"] == entity_id
    assert activities[0]["entity_type"] == "mapping"
    assert activities[0]["username"] == test_user.username


def test_get_entity_activity_orm_filters_by_entity_type(db_session, test_project, test_user):
    """Test que filtra correctamente por entity_type"""
    entity_id = str(uuid4())

    # Crear actividades con el mismo entity_id pero diferentes tipos
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="Update mapping",
        entity_id=entity_id,
        entity_type="mapping",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="Update version",
        entity_id=entity_id,
        entity_type="version",
    )

    # Filtrar solo por tipo 'mapping'
    activities = get_entity_activity_orm(db=db_session, entity_id=entity_id, entity_type="mapping")

    assert len(activities) == 1
    assert activities[0]["entity_type"] == "mapping"


def test_get_entity_activity_orm_limit(db_session, test_project, test_user):
    """Test que el parámetro limit funciona"""
    entity_id = str(uuid4())

    # Crear 5 actividades
    for i in range(5):
        create_activity_log_orm(
            db=db_session,
            project_id=str(test_project.id),
            user_id=str(test_user.id),
            activity_type="update",
            description=f"Update {i}",
            entity_id=entity_id,
            entity_type="mapping",
        )

    # Solicitar solo 3
    activities = get_entity_activity_orm(
        db=db_session, entity_id=entity_id, entity_type="mapping", limit=3
    )

    assert len(activities) == 3


# ============================================================================
# TESTS: get_user_activity_orm()
# ============================================================================


def test_get_user_activity_orm_empty(db_session, test_user):
    """Test que un usuario sin actividad retorna lista vacía"""
    activities = get_user_activity_orm(db=db_session, user_id=str(test_user.id))

    assert isinstance(activities, list)
    assert len(activities) == 0


def test_get_user_activity_orm_single_user(db_session, test_project, test_user):
    """Test que se obtiene actividad de un usuario específico"""
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="login",
        description="User logged in",
    )

    activities = get_user_activity_orm(db=db_session, user_id=str(test_user.id))

    assert len(activities) == 1
    assert activities[0]["user_id"] == str(test_user.id)
    assert activities[0]["username"] == test_user.username


def test_get_user_activity_orm_filter_by_project(db_session, test_project, test_user):
    """Test que el filtro opcional por project_id funciona"""
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

    # Crear actividades en ambos proyectos
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="Update in project 1",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(other_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="Update in project 2",
    )

    # Sin filtro - debería retornar ambas
    all_activities = get_user_activity_orm(db=db_session, user_id=str(test_user.id))

    # Con filtro - solo proyecto 1
    filtered_activities = get_user_activity_orm(
        db=db_session, user_id=str(test_user.id), project_id=str(test_project.id)
    )

    assert len(all_activities) == 2
    assert len(filtered_activities) == 1
    assert filtered_activities[0]["project_id"] == str(test_project.id)


def test_get_user_activity_orm_multiple_users(db_session, test_project, test_user, test_user2):
    """Test que solo retorna actividad del usuario especificado"""
    # Usuario 1 crea actividad
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="User 1 activity",
    )

    # Usuario 2 crea actividad
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user2.id),
        activity_type="update",
        description="User 2 activity",
    )

    # Obtener actividad de usuario 1
    user1_activities = get_user_activity_orm(db=db_session, user_id=str(test_user.id))

    assert len(user1_activities) == 1
    assert user1_activities[0]["user_id"] == str(test_user.id)


# ============================================================================
# TESTS: get_activity_stats_orm()
# ============================================================================


def test_get_activity_stats_orm_empty(db_session, test_project):
    """Test que un proyecto sin actividad retorna dict vacío"""
    stats = get_activity_stats_orm(db=db_session, project_id=str(test_project.id))

    assert isinstance(stats, dict)
    assert len(stats) == 0


def test_get_activity_stats_orm_single_type(db_session, test_project, test_user):
    """Test que cuenta correctamente actividades del mismo tipo"""
    # Crear 3 actividades del mismo tipo
    for i in range(3):
        create_activity_log_orm(
            db=db_session,
            project_id=str(test_project.id),
            user_id=str(test_user.id),
            activity_type="version_created",
            description=f"Version {i}",
        )

    stats = get_activity_stats_orm(db=db_session, project_id=str(test_project.id))

    assert stats == {"version_created": 3}


def test_get_activity_stats_orm_multiple_types(db_session, test_project, test_user):
    """Test que agrupa correctamente por tipo con GROUP BY"""
    # Crear actividades de diferentes tipos
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="version_created",
        description="Version 1",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="version_created",
        description="Version 2",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="comment_added",
        description="Comment",
    )

    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="member_added",
        description="Member",
    )

    stats = get_activity_stats_orm(db=db_session, project_id=str(test_project.id))

    assert stats == {"version_created": 2, "comment_added": 1, "member_added": 1}


def test_get_activity_stats_orm_scoped_to_project(db_session, test_project, test_user):
    """Test que las estadísticas están limitadas al proyecto"""
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

    # Crear actividad en proyecto 1
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="Update",
    )

    # Crear actividad en proyecto 2
    create_activity_log_orm(
        db=db_session,
        project_id=str(other_project.id),
        user_id=str(test_user.id),
        activity_type="update",
        description="Update",
    )

    # Obtener stats de proyecto 1
    stats1 = get_activity_stats_orm(db=db_session, project_id=str(test_project.id))

    # Obtener stats de proyecto 2
    stats2 = get_activity_stats_orm(db=db_session, project_id=str(other_project.id))

    assert stats1 == {"update": 1}
    assert stats2 == {"update": 1}


# ============================================================================
# TESTS: delete_old_activity_orm()
# ============================================================================


def test_delete_old_activity_orm_deletes_old(db_session, test_project, test_user):
    """Test que elimina correctamente actividades antiguas"""
    # Crear actividad antigua (manualmente con fecha pasada)
    from app.models.orm.activity import ProjectActivity

    old_activity = ProjectActivity(
        id=uuid4(),
        project_id=test_project.id,
        user_id=test_user.id,
        activity_type="old",
        description="Old activity",
        created_at=datetime.now(timezone.utc) - timedelta(days=100),
    )
    db_session.add(old_activity)
    db_session.commit()

    # Crear actividad reciente
    recent_activity = ProjectActivity(
        id=uuid4(),
        project_id=test_project.id,
        user_id=test_user.id,
        activity_type="recent",
        description="Recent activity",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(recent_activity)
    db_session.commit()

    # Eliminar actividades más antiguas de 90 días
    deleted_count = delete_old_activity_orm(db=db_session, days=90)

    assert deleted_count == 1

    # Verificar que solo queda la actividad reciente
    remaining = get_project_activity_orm(db=db_session, project_id=str(test_project.id))

    assert len(remaining) == 1
    assert remaining[0]["activity_type"] == "recent"


def test_delete_old_activity_orm_no_old_activities(db_session, test_project, test_user):
    """Test que retorna 0 cuando no hay actividades antiguas"""
    # Crear solo actividades recientes
    create_activity_log_orm(
        db=db_session,
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        activity_type="recent",
        description="Recent activity",
    )

    # Intentar eliminar actividades antiguas
    deleted_count = delete_old_activity_orm(db=db_session, days=90)

    assert deleted_count == 0


def test_delete_old_activity_orm_custom_days(db_session, test_project, test_user):
    """Test que funciona con diferentes valores de días"""
    from app.models.orm.activity import ProjectActivity

    # Contar actividades actuales del proyecto antes de la prueba
    initial_activities = get_project_activity_orm(db=db_session, project_id=str(test_project.id))
    initial_count = len(initial_activities)

    # Crear actividad de hace 40 días
    activity_40_days = ProjectActivity(
        id=uuid4(),
        project_id=test_project.id,
        user_id=test_user.id,
        activity_type="test",
        description="40 days old",
        created_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    db_session.add(activity_40_days)
    db_session.commit()

    # Eliminar actividades más antiguas de 30 días (debería eliminar al menos la de 40 días)
    deleted_count = delete_old_activity_orm(db=db_session, days=30)

    # Verificar que se eliminó al menos 1 actividad (puede haber más de otros tests)
    assert deleted_count >= 1

    # Verificar que la actividad de 40 días fue eliminada del proyecto
    remaining = get_project_activity_orm(db=db_session, project_id=str(test_project.id))

    # Debería tener las mismas actividades que al inicio (la de 40 días fue eliminada)
    assert len(remaining) == initial_count


def test_delete_old_activity_orm_deletes_from_all_projects(db_session, test_project, test_user):
    """Test que elimina actividades antiguas de TODOS los proyectos (no está limitado a uno)"""
    from app.models.orm.activity import ProjectActivity

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

    # Crear actividades antiguas en ambos proyectos
    old_activity1 = ProjectActivity(
        id=uuid4(),
        project_id=test_project.id,
        user_id=test_user.id,
        activity_type="old",
        description="Old in project 1",
        created_at=datetime.now(timezone.utc) - timedelta(days=100),
    )

    old_activity2 = ProjectActivity(
        id=uuid4(),
        project_id=other_project.id,
        user_id=test_user.id,
        activity_type="old",
        description="Old in project 2",
        created_at=datetime.now(timezone.utc) - timedelta(days=100),
    )

    db_session.add(old_activity1)
    db_session.add(old_activity2)
    db_session.commit()

    # Eliminar actividades antiguas
    deleted_count = delete_old_activity_orm(db=db_session, days=90)

    # Debería eliminar ambas (de todos los proyectos)
    assert deleted_count == 2
