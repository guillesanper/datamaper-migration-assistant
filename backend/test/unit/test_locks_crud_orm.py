"""
Unit tests for locks_crud.py ORM functions

Tests para las 9 funciones ORM de locks_crud:
1. cleanup_expired_locks_orm() - Test limpieza de locks expirados
2. acquire_lock_orm() - Test adquisición con renovación automática
3. release_lock_orm() - Test liberación (solo owner)
4. get_lock_status_orm() - Test estado con JOIN
5. renew_lock_orm() - Test renovación (heartbeat)
6. force_unlock_orm() - Test desbloqueo forzado (admin)
7. get_active_locks_orm() - Test listado de locks activos
8. get_user_locks_orm() - Test locks de usuario
9. check_lock_owner_orm() - Test verificación de ownership

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
from app.crud.locks_crud import (
    DEFAULT_LOCK_DURATION,
    acquire_lock_orm,
    check_lock_owner_orm,
    cleanup_expired_locks_orm,
    force_unlock_orm,
    get_active_locks_orm,
    get_lock_status_orm,
    get_user_locks_orm,
    release_lock_orm,
    renew_lock_orm,
)
from app.database.session import SessionLocal
from app.models.orm import EntityLock, Project, User

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
        description="Test project for locks",
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
# TESTS: cleanup_expired_locks_orm()
# ============================================================================


def test_cleanup_expired_locks_orm_no_expired(db_session):
    """Test que retorna 0 cuando no hay locks expirados"""
    deleted_count = cleanup_expired_locks_orm(db_session)

    assert deleted_count == 0


def test_cleanup_expired_locks_orm_removes_expired(db_session, test_project, test_user):
    """Test que elimina correctamente locks expirados"""
    # Crear lock expirado manualmente
    expired_lock = EntityLock(
        id=uuid4(),
        entity_id=uuid4(),
        entity_type="mapping",
        project_id=test_project.id,
        user_id=test_user.id,
        acquired_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # Expirado
        last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(expired_lock)
    db_session.commit()

    # Limpiar locks expirados
    deleted_count = cleanup_expired_locks_orm(db_session)

    assert deleted_count == 1


def test_cleanup_expired_locks_orm_keeps_active(db_session, test_project, test_user):
    """Test que NO elimina locks activos"""
    # Crear lock activo
    active_lock = EntityLock(
        id=uuid4(),
        entity_id=uuid4(),
        entity_type="mapping",
        project_id=test_project.id,
        user_id=test_user.id,
        acquired_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_LOCK_DURATION),
        last_heartbeat=datetime.now(timezone.utc),
    )
    db_session.add(active_lock)
    db_session.commit()

    # Limpiar locks expirados
    deleted_count = cleanup_expired_locks_orm(db_session)

    assert deleted_count == 0

    # Verificar que el lock activo sigue existiendo
    remaining = db_session.query(EntityLock).filter(EntityLock.id == active_lock.id).first()
    assert remaining is not None


# ============================================================================
# TESTS: acquire_lock_orm()
# ============================================================================


def test_acquire_lock_orm_success(db_session, test_project, test_user):
    """Test que se puede adquirir un lock exitosamente"""
    entity_id = str(uuid4())

    result = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        duration_minutes=DEFAULT_LOCK_DURATION,
    )

    assert result is not None
    assert isinstance(result, dict)
    assert result["entity_id"] == entity_id
    assert result["entity_type"] == "mapping"
    assert result["user_id"] == str(test_user.id)
    assert result["project_id"] == str(test_project.id)
    assert "id" in result
    assert "acquired_at" in result
    assert "expires_at" in result
    assert "last_heartbeat" in result


def test_acquire_lock_orm_blocked_by_other_user(db_session, test_project, test_user, test_user2):
    """Test que no se puede adquirir un lock si otro usuario ya lo tiene"""
    entity_id = str(uuid4())

    # Usuario 1 adquiere el lock
    lock1 = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock1 is not None

    # Usuario 2 intenta adquirir el mismo lock - debe retornar None
    lock2 = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user2.id),
    )
    assert lock2 is None


def test_acquire_lock_orm_renews_own_lock(db_session, test_project, test_user):
    """Test que si el mismo usuario intenta adquirir un lock que ya tiene, lo renueva"""
    entity_id = str(uuid4())

    # Primera adquisición
    lock1 = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        duration_minutes=5,
    )
    assert lock1 is not None
    first_expires = lock1["expires_at"]

    # Segunda adquisición por el mismo usuario - debe renovar
    lock2 = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        duration_minutes=10,
    )
    assert lock2 is not None
    second_expires = lock2["expires_at"]

    # La segunda expiración debe ser posterior (renovado)
    assert second_expires > first_expires


def test_acquire_lock_orm_custom_duration(db_session, test_project, test_user):
    """Test que se puede especificar una duración personalizada"""
    entity_id = str(uuid4())
    custom_duration = 30

    result = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="table",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        duration_minutes=custom_duration,
    )

    assert result is not None
    # Verificar que expires_at es aproximadamente custom_duration minutos en el futuro
    expires_delta = result["expires_at"] - result["acquired_at"]
    assert expires_delta.total_seconds() >= (custom_duration * 60) - 5  # Margen de 5 segundos


# ============================================================================
# TESTS: release_lock_orm()
# ============================================================================


def test_release_lock_orm_success(db_session, test_project, test_user):
    """Test que se puede liberar un lock exitosamente"""
    entity_id = str(uuid4())

    # Adquirir lock
    lock = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock is not None

    # Liberar lock
    released = release_lock_orm(
        db=db_session, entity_id=entity_id, entity_type="mapping", user_id=str(test_user.id)
    )

    assert released is True

    # Verificar que el lock ya no existe
    status = get_lock_status_orm(db=db_session, entity_id=entity_id, entity_type="mapping")
    assert status is None


def test_release_lock_orm_not_owner(db_session, test_project, test_user, test_user2):
    """Test que no se puede liberar un lock de otro usuario"""
    entity_id = str(uuid4())

    # Usuario 1 adquiere el lock
    lock = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock is not None

    # Usuario 2 intenta liberar el lock - debe retornar False
    released = release_lock_orm(
        db=db_session, entity_id=entity_id, entity_type="mapping", user_id=str(test_user2.id)
    )

    assert released is False

    # Verificar que el lock sigue existiendo
    status = get_lock_status_orm(db=db_session, entity_id=entity_id, entity_type="mapping")
    assert status is not None


def test_release_lock_orm_nonexistent(db_session, test_user):
    """Test que liberar un lock inexistente retorna False"""
    entity_id = str(uuid4())

    released = release_lock_orm(
        db=db_session, entity_id=entity_id, entity_type="mapping", user_id=str(test_user.id)
    )

    assert released is False


# ============================================================================
# TESTS: get_lock_status_orm()
# ============================================================================


def test_get_lock_status_orm_active_lock(db_session, test_project, test_user):
    """Test que retorna información del lock con JOIN de username"""
    entity_id = str(uuid4())

    # Adquirir lock
    lock = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock is not None

    # Obtener estado
    status = get_lock_status_orm(db=db_session, entity_id=entity_id, entity_type="mapping")

    assert status is not None
    assert status["entity_id"] == entity_id
    assert status["user_id"] == str(test_user.id)
    assert status["username"] == test_user.username  # JOIN con User
    assert status["user_email"] == test_user.email  # JOIN con User


def test_get_lock_status_orm_no_lock(db_session):
    """Test que retorna None cuando no hay lock"""
    entity_id = str(uuid4())

    status = get_lock_status_orm(db=db_session, entity_id=entity_id, entity_type="mapping")

    assert status is None


def test_get_lock_status_orm_cleans_expired(db_session, test_project, test_user):
    """Test que limpia locks expirados antes de consultar"""
    entity_id = str(uuid4())

    # Crear lock expirado manualmente
    expired_lock = EntityLock(
        id=uuid4(),
        entity_id=entity_id,
        entity_type="mapping",
        project_id=test_project.id,
        user_id=test_user.id,
        acquired_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(expired_lock)
    db_session.commit()

    # get_lock_status_orm debe limpiar el lock expirado
    status = get_lock_status_orm(db=db_session, entity_id=entity_id, entity_type="mapping")

    assert status is None


# ============================================================================
# TESTS: renew_lock_orm()
# ============================================================================


def test_renew_lock_orm_success(db_session, test_project, test_user):
    """Test que se puede renovar un lock exitosamente"""
    entity_id = str(uuid4())

    # Adquirir lock
    lock = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        duration_minutes=5,
    )
    assert lock is not None
    original_expires = lock["expires_at"]

    # Renovar lock
    renewed = renew_lock_orm(
        db=db_session, lock_id=lock["id"], user_id=str(test_user.id), duration_minutes=10
    )

    assert renewed is not None
    assert renewed["id"] == lock["id"]
    assert renewed["expires_at"] > original_expires  # Expiración extendida


def test_renew_lock_orm_not_owner(db_session, test_project, test_user, test_user2):
    """Test que no se puede renovar un lock de otro usuario"""
    entity_id = str(uuid4())

    # Usuario 1 adquiere el lock
    lock = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock is not None

    # Usuario 2 intenta renovar - debe retornar None
    renewed = renew_lock_orm(db=db_session, lock_id=lock["id"], user_id=str(test_user2.id))

    assert renewed is None


def test_renew_lock_orm_nonexistent(db_session, test_user):
    """Test que renovar un lock inexistente retorna None"""
    fake_lock_id = str(uuid4())

    renewed = renew_lock_orm(db=db_session, lock_id=fake_lock_id, user_id=str(test_user.id))

    assert renewed is None


# ============================================================================
# TESTS: force_unlock_orm()
# ============================================================================


def test_force_unlock_orm_success(db_session, test_project, test_user):
    """Test que se puede forzar el desbloqueo de una entidad"""
    entity_id = str(uuid4())

    # Adquirir lock
    lock = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock is not None

    # Force unlock
    unlocked = force_unlock_orm(db=db_session, entity_id=entity_id, entity_type="mapping")

    assert unlocked is True

    # Verificar que el lock ya no existe
    status = get_lock_status_orm(db=db_session, entity_id=entity_id, entity_type="mapping")
    assert status is None


def test_force_unlock_orm_nonexistent(db_session):
    """Test que force unlock de entidad sin lock retorna False"""
    entity_id = str(uuid4())

    unlocked = force_unlock_orm(db=db_session, entity_id=entity_id, entity_type="mapping")

    assert unlocked is False


# ============================================================================
# TESTS: get_active_locks_orm()
# ============================================================================


def test_get_active_locks_orm_empty(db_session, test_project):
    """Test que un proyecto sin locks retorna lista vacía"""
    locks = get_active_locks_orm(db=db_session, project_id=str(test_project.id))

    assert isinstance(locks, list)
    assert len(locks) == 0


def test_get_active_locks_orm_single_lock(db_session, test_project, test_user):
    """Test que retorna locks activos con JOIN de username"""
    entity_id = str(uuid4())

    # Adquirir lock
    lock = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock is not None

    # Obtener locks activos
    locks = get_active_locks_orm(db=db_session, project_id=str(test_project.id))

    assert len(locks) == 1
    assert locks[0]["entity_id"] == entity_id
    assert locks[0]["username"] == test_user.username
    assert locks[0]["user_email"] == test_user.email


def test_get_active_locks_orm_multiple_locks(db_session, test_project, test_user, test_user2):
    """Test que retorna múltiples locks ordenados por acquired_at DESC"""
    entity_id1 = str(uuid4())
    entity_id2 = str(uuid4())

    # Usuario 1 adquiere lock
    lock1 = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id1,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock1 is not None

    # Usuario 2 adquiere otro lock
    lock2 = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id2,
        entity_type="table",
        project_id=str(test_project.id),
        user_id=str(test_user2.id),
    )
    assert lock2 is not None

    # Obtener locks activos
    locks = get_active_locks_orm(db=db_session, project_id=str(test_project.id))

    assert len(locks) == 2
    # Verificar orden DESC (el más reciente primero)
    assert locks[0]["entity_id"] == entity_id2
    assert locks[1]["entity_id"] == entity_id1


def test_get_active_locks_orm_filters_by_project(db_session, test_project, test_user):
    """Test que solo retorna locks del proyecto especificado"""
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

    # Lock en proyecto original
    lock1 = acquire_lock_orm(
        db=db_session,
        entity_id=str(uuid4()),
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock1 is not None

    # Lock en otro proyecto
    lock2 = acquire_lock_orm(
        db=db_session,
        entity_id=str(uuid4()),
        entity_type="mapping",
        project_id=str(other_project.id),
        user_id=str(test_user.id),
    )
    assert lock2 is not None

    # Obtener locks solo del proyecto original
    locks = get_active_locks_orm(db=db_session, project_id=str(test_project.id))

    assert len(locks) == 1
    assert locks[0]["project_id"] == str(test_project.id)


# ============================================================================
# TESTS: get_user_locks_orm()
# ============================================================================


def test_get_user_locks_orm_empty(db_session, test_user):
    """Test que un usuario sin locks retorna lista vacía"""
    locks = get_user_locks_orm(db=db_session, user_id=str(test_user.id))

    assert isinstance(locks, list)
    assert len(locks) == 0


def test_get_user_locks_orm_single_lock(db_session, test_project, test_user):
    """Test que retorna locks de un usuario"""
    entity_id = str(uuid4())

    # Adquirir lock
    lock = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock is not None

    # Obtener locks del usuario
    locks = get_user_locks_orm(db=db_session, user_id=str(test_user.id))

    assert len(locks) == 1
    assert locks[0]["entity_id"] == entity_id
    assert locks[0]["user_id"] == str(test_user.id)


def test_get_user_locks_orm_filters_by_user(db_session, test_project, test_user, test_user2):
    """Test que solo retorna locks del usuario especificado"""
    # Usuario 1 adquiere lock
    lock1 = acquire_lock_orm(
        db=db_session,
        entity_id=str(uuid4()),
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock1 is not None

    # Usuario 2 adquiere lock
    lock2 = acquire_lock_orm(
        db=db_session,
        entity_id=str(uuid4()),
        entity_type="table",
        project_id=str(test_project.id),
        user_id=str(test_user2.id),
    )
    assert lock2 is not None

    # Obtener locks solo del usuario 1
    locks_user1 = get_user_locks_orm(db=db_session, user_id=str(test_user.id))

    assert len(locks_user1) == 1
    assert locks_user1[0]["user_id"] == str(test_user.id)


# ============================================================================
# TESTS: check_lock_owner_orm()
# ============================================================================


def test_check_lock_owner_orm_true(db_session, test_project, test_user):
    """Test que retorna True cuando el usuario es el owner del lock"""
    entity_id = str(uuid4())

    # Adquirir lock
    lock = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock is not None

    # Verificar ownership
    is_owner = check_lock_owner_orm(
        db=db_session, entity_id=entity_id, entity_type="mapping", user_id=str(test_user.id)
    )

    assert is_owner is True


def test_check_lock_owner_orm_false_different_user(db_session, test_project, test_user, test_user2):
    """Test que retorna False cuando otro usuario es el owner"""
    entity_id = str(uuid4())

    # Usuario 1 adquiere lock
    lock = acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
    )
    assert lock is not None

    # Verificar con usuario 2 - debe retornar False
    is_owner = check_lock_owner_orm(
        db=db_session, entity_id=entity_id, entity_type="mapping", user_id=str(test_user2.id)
    )

    assert is_owner is False


def test_check_lock_owner_orm_false_no_lock(db_session, test_user):
    """Test que retorna False cuando no existe el lock"""
    entity_id = str(uuid4())

    is_owner = check_lock_owner_orm(
        db=db_session, entity_id=entity_id, entity_type="mapping", user_id=str(test_user.id)
    )

    assert is_owner is False


def test_check_lock_owner_orm_false_expired(db_session, test_project, test_user):
    """Test que retorna False cuando el lock está expirado"""
    entity_id = uuid4()

    # Crear lock expirado manualmente
    expired_lock = EntityLock(
        id=uuid4(),
        entity_id=entity_id,
        entity_type="mapping",
        project_id=test_project.id,
        user_id=test_user.id,
        acquired_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(expired_lock)
    db_session.commit()

    # Verificar ownership - debe retornar False porque está expirado
    is_owner = check_lock_owner_orm(
        db=db_session, entity_id=str(entity_id), entity_type="mapping", user_id=str(test_user.id)
    )

    assert is_owner is False
