"""
Tests para migration_script_crud.py (versión ORM)
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.crud import migration_script_crud
from app.models.orm.migration import MigrationExecution, MigrationScript
from app.models.orm.project import Project
from app.models.orm.user import User

# ============================================================================
# Helpers para crear datos de prueba
# ============================================================================


def create_test_user(db_session: Session, user_id: uuid.UUID = None) -> uuid.UUID:
    """Crea un usuario de prueba y retorna su ID"""
    if user_id is None:
        user_id = uuid.uuid4()

    user = User(
        id=user_id,
        username=f"testuser_{str(user_id)[:8]}",
        email=f"{str(user_id)[:8]}@test.com",
        password_hash="hashed_password_test",
        is_verified=True,
        is_deleted=False,
    )
    db_session.add(user)
    db_session.commit()

    return user_id


def create_test_project(
    db_session: Session, owner_id: uuid.UUID, project_id: uuid.UUID = None
) -> uuid.UUID:
    """Crea un proyecto de prueba y retorna su ID"""
    if project_id is None:
        project_id = uuid.uuid4()

    project = Project(id=project_id, name=f"Test Project {str(project_id)[:8]}", owner_id=owner_id)
    db_session.add(project)
    db_session.commit()

    return project_id


# ============================================================================
# Tests de create_migration_script_orm
# ============================================================================


def test_create_migration_script_orm_basic(db_session: Session):
    """Test: crear script de migración básico"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    script_content = "INSERT INTO users (id, name) VALUES (1, 'test');"

    result = migration_script_crud.create_migration_script_orm(
        db_session,
        project_id=str(project_id),
        script_content=script_content,
        created_by=str(user_id),
    )

    assert result is not None
    assert result["project_id"] == str(project_id)
    assert result["script_content"] == script_content
    assert result["batch_size"] == 10000  # default
    assert result["include_constraints"] is True  # default
    assert result["include_validation"] is True  # default
    assert result["dialect"] == "postgresql"  # default
    assert result["script_hash"] is not None
    assert result["created_by"] == str(user_id)

    # Verificar en BD
    script_db = db_session.query(MigrationScript).filter(MigrationScript.id == result["id"]).first()
    assert script_db is not None
    assert script_db.script_content == script_content


def test_create_migration_script_orm_with_options(db_session: Session):
    """Test: crear script con opciones personalizadas"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    script_content = "SELECT * FROM users;"
    dependency_order = ["users", "orders", "products"]

    result = migration_script_crud.create_migration_script_orm(
        db_session,
        project_id=str(project_id),
        script_content=script_content,
        batch_size=5000,
        include_constraints=False,
        include_validation=False,
        dialect="mysql",
        dependency_order=dependency_order,
        created_by=str(user_id),
    )

    assert result["batch_size"] == 5000
    assert result["include_constraints"] is False
    assert result["include_validation"] is False
    assert result["dialect"] == "mysql"
    assert result["dependency_order"] == dependency_order


def test_create_migration_script_orm_hash_calculation(db_session: Session):
    """Test: verificar cálculo correcto del hash SHA-256"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    script_content = "INSERT INTO test VALUES (1);"
    expected_hash = hashlib.sha256(script_content.encode("utf-8")).hexdigest()

    result = migration_script_crud.create_migration_script_orm(
        db_session, project_id=str(project_id), script_content=script_content
    )

    assert result["script_hash"] == expected_hash


def test_create_migration_script_orm_without_creator(db_session: Session):
    """Test: crear script sin especificar creator"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    result = migration_script_crud.create_migration_script_orm(
        db_session, project_id=str(project_id), script_content="SELECT 1;"
    )

    assert result["created_by"] is None


# ============================================================================
# Tests de get_migration_script_by_id_orm
# ============================================================================


def test_get_migration_script_by_id_orm_success(db_session: Session):
    """Test: obtener script por ID"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    created = migration_script_crud.create_migration_script_orm(
        db_session, project_id=str(project_id), script_content="SELECT * FROM test;"
    )

    result = migration_script_crud.get_migration_script_by_id_orm(
        db_session, script_id=created["id"], project_id=str(project_id)
    )

    assert result is not None
    assert result["id"] == created["id"]
    assert result["script_content"] == "SELECT * FROM test;"


def test_get_migration_script_by_id_orm_not_found(db_session: Session):
    """Test: obtener script inexistente"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)
    fake_id = str(uuid.uuid4())

    result = migration_script_crud.get_migration_script_by_id_orm(
        db_session, script_id=fake_id, project_id=str(project_id)
    )

    assert result is None


def test_get_migration_script_by_id_orm_wrong_project(db_session: Session):
    """Test: no se puede obtener script de otro proyecto"""
    user_id = create_test_user(db_session)
    project1_id = create_test_project(db_session, user_id)
    project2_id = create_test_project(db_session, user_id)

    # Crear script en project1
    created = migration_script_crud.create_migration_script_orm(
        db_session, project_id=str(project1_id), script_content="SELECT 1;"
    )

    # Intentar obtener con project2
    result = migration_script_crud.get_migration_script_by_id_orm(
        db_session, script_id=created["id"], project_id=str(project2_id)
    )

    assert result is None


# ============================================================================
# Tests de get_migration_scripts_orm
# ============================================================================


def test_get_migration_scripts_orm_empty(db_session: Session):
    """Test: obtener scripts cuando no hay ninguno"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    result = migration_script_crud.get_migration_scripts_orm(db_session, str(project_id))

    assert result == []


def test_get_migration_scripts_orm_multiple(db_session: Session):
    """Test: obtener múltiples scripts"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    # Crear 3 scripts
    for i in range(3):
        migration_script_crud.create_migration_script_orm(
            db_session, project_id=str(project_id), script_content=f"SELECT {i};"
        )

    result = migration_script_crud.get_migration_scripts_orm(db_session, str(project_id))

    assert len(result) == 3


def test_get_migration_scripts_orm_ordering(db_session: Session):
    """Test: verificar orden (más recientes primero)"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    # Crear scripts con delay
    script1 = migration_script_crud.create_migration_script_orm(
        db_session, project_id=str(project_id), script_content="SELECT 1;"
    )

    import time

    time.sleep(0.1)

    script2 = migration_script_crud.create_migration_script_orm(
        db_session, project_id=str(project_id), script_content="SELECT 2;"
    )

    result = migration_script_crud.get_migration_scripts_orm(db_session, str(project_id))

    # El más reciente debe estar primero
    assert result[0]["id"] == script2["id"]
    assert result[1]["id"] == script1["id"]


def test_get_migration_scripts_orm_pagination(db_session: Session):
    """Test: paginación de scripts"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    # Crear 10 scripts
    for i in range(10):
        migration_script_crud.create_migration_script_orm(
            db_session, project_id=str(project_id), script_content=f"SELECT {i};"
        )

    # Obtener primera página
    page1 = migration_script_crud.get_migration_scripts_orm(
        db_session, str(project_id), limit=5, offset=0
    )
    assert len(page1) == 5

    # Obtener segunda página
    page2 = migration_script_crud.get_migration_scripts_orm(
        db_session, str(project_id), limit=5, offset=5
    )
    assert len(page2) == 5

    # Verificar que son diferentes
    assert page1[0]["id"] != page2[0]["id"]


def test_get_migration_scripts_orm_isolation(db_session: Session):
    """Test: un proyecto no ve scripts de otro"""
    user_id = create_test_user(db_session)
    project1_id = create_test_project(db_session, user_id)
    project2_id = create_test_project(db_session, user_id)

    # Crear script para project1
    migration_script_crud.create_migration_script_orm(
        db_session, project_id=str(project1_id), script_content="SELECT 1;"
    )

    # Crear script para project2
    migration_script_crud.create_migration_script_orm(
        db_session, project_id=str(project2_id), script_content="SELECT 2;"
    )

    # Verificar aislamiento
    project1_scripts = migration_script_crud.get_migration_scripts_orm(db_session, str(project1_id))
    project2_scripts = migration_script_crud.get_migration_scripts_orm(db_session, str(project2_id))

    assert len(project1_scripts) == 1
    assert len(project2_scripts) == 1


# ============================================================================
# Tests de create_migration_execution_orm
# ============================================================================


def test_create_migration_execution_orm_basic(db_session: Session):
    """Test: crear ejecución de migración básica"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    script_hash = "abc123def456"

    result = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash=script_hash, created_by=str(user_id)
    )

    assert result is not None
    assert result["project_id"] == str(project_id)
    assert result["script_hash"] == script_hash
    assert result["status"] == "pending"  # default
    assert result["rows_migrated"] == 0  # default
    assert result["created_by"] == str(user_id)
    assert result["execution_log"] == []  # default

    # Verificar en BD
    exec_db = (
        db_session.query(MigrationExecution).filter(MigrationExecution.id == result["id"]).first()
    )
    assert exec_db is not None


def test_create_migration_execution_orm_with_backup(db_session: Session):
    """Test: crear ejecución con backup_id"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    result = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash123", backup_id="backup_12345"
    )

    assert result["backup_id"] == "backup_12345"


# ============================================================================
# Tests de get_migration_execution_orm
# ============================================================================


def test_get_migration_execution_orm_success(db_session: Session):
    """Test: obtener ejecución por ID"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    created = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash123"
    )

    result = migration_script_crud.get_migration_execution_orm(db_session, created["id"])

    assert result is not None
    assert result["id"] == created["id"]
    assert result["status"] == "pending"


def test_get_migration_execution_orm_not_found(db_session: Session):
    """Test: obtener ejecución inexistente"""
    fake_id = str(uuid.uuid4())

    result = migration_script_crud.get_migration_execution_orm(db_session, fake_id)

    assert result is None


# ============================================================================
# Tests de update_execution_status_orm
# ============================================================================


def test_update_execution_status_orm_basic(db_session: Session):
    """Test: actualizar estado de ejecución"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    created = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash123"
    )

    # Actualizar a running
    result = migration_script_crud.update_execution_status_orm(
        db_session,
        execution_id=created["id"],
        status="running",
        rows_migrated=1000,
        mark_started=True,
    )

    assert result is not None
    assert result["status"] == "running"
    assert result["rows_migrated"] == 1000
    assert result["started_at"] is not None


def test_update_execution_status_orm_with_error(db_session: Session):
    """Test: actualizar ejecución con error"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    created = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash123"
    )

    result = migration_script_crud.update_execution_status_orm(
        db_session,
        execution_id=created["id"],
        status="failed",
        error_message="Connection timeout",
        mark_completed=True,
    )

    assert result["status"] == "failed"
    assert result["error_message"] == "Connection timeout"
    assert result["completed_at"] is not None


def test_update_execution_status_orm_with_log(db_session: Session):
    """Test: actualizar ejecución con execution_log"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    created = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash123"
    )

    log = [
        {"step": 1, "table": "users", "rows": 100, "status": "success"},
        {"step": 2, "table": "orders", "rows": 200, "status": "running"},
    ]

    result = migration_script_crud.update_execution_status_orm(
        db_session, execution_id=created["id"], status="running", execution_log=log
    )

    assert result["execution_log"] == log


def test_update_execution_status_orm_not_found(db_session: Session):
    """Test: actualizar ejecución inexistente"""
    fake_id = str(uuid.uuid4())

    result = migration_script_crud.update_execution_status_orm(
        db_session, execution_id=fake_id, status="running"
    )

    assert result is None


# ============================================================================
# Tests de get_execution_logs_orm
# ============================================================================


def test_get_execution_logs_orm_success(db_session: Session):
    """Test: obtener logs de ejecución"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    created = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash123"
    )

    # Actualizar con logs
    log = [{"step": 1, "message": "Started"}]
    migration_script_crud.update_execution_status_orm(
        db_session,
        execution_id=created["id"],
        status="running",
        execution_log=log,
        error_message="Test error",
    )

    result = migration_script_crud.get_execution_logs_orm(db_session, created["id"])

    assert result["execution_log"] == log
    assert result["error_message"] == "Test error"


def test_get_execution_logs_orm_empty(db_session: Session):
    """Test: obtener logs de ejecución sin logs"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    created = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash123"
    )

    result = migration_script_crud.get_execution_logs_orm(db_session, created["id"])

    assert result["execution_log"] == []
    assert result["error_message"] is None


# ============================================================================
# Tests de count_executions_orm
# ============================================================================


def test_count_executions_orm_zero(db_session: Session):
    """Test: contar cuando no hay ejecuciones"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    count = migration_script_crud.count_executions_orm(db_session, str(project_id))

    assert count == 0


def test_count_executions_orm_multiple(db_session: Session):
    """Test: contar múltiples ejecuciones"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    # Crear 5 ejecuciones
    for i in range(5):
        migration_script_crud.create_migration_execution_orm(
            db_session, project_id=str(project_id), script_hash=f"hash{i}"
        )

    count = migration_script_crud.count_executions_orm(db_session, str(project_id))

    assert count == 5


def test_count_executions_orm_with_filter(db_session: Session):
    """Test: contar con filtro de estado"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    # Crear 3 ejecuciones
    exec1 = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash1"
    )
    exec2 = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash2"
    )
    exec3 = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash3"
    )

    # Actualizar 2 a success
    migration_script_crud.update_execution_status_orm(db_session, exec1["id"], "success")
    migration_script_crud.update_execution_status_orm(db_session, exec2["id"], "success")

    # Contar solo success
    count = migration_script_crud.count_executions_orm(
        db_session, str(project_id), status_filter="success"
    )

    assert count == 2


# ============================================================================
# Tests de get_executions_paginated_orm
# ============================================================================


def test_get_executions_paginated_orm_empty(db_session: Session):
    """Test: obtener ejecuciones cuando no hay ninguna"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    result = migration_script_crud.get_executions_paginated_orm(db_session, str(project_id))

    assert result == []


def test_get_executions_paginated_orm_multiple(db_session: Session):
    """Test: obtener múltiples ejecuciones"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    # Crear 3 ejecuciones
    for i in range(3):
        exec_created = migration_script_crud.create_migration_execution_orm(
            db_session, project_id=str(project_id), script_hash=f"hash{i}"
        )
        # Marcar como iniciadas
        migration_script_crud.update_execution_status_orm(
            db_session, execution_id=exec_created["id"], status="running", mark_started=True
        )

    result = migration_script_crud.get_executions_paginated_orm(db_session, str(project_id))

    assert len(result) == 3
    # Verificar campos
    assert "id" in result[0]
    assert "status" in result[0]
    assert "rows_migrated" in result[0]
    assert "duration_seconds" in result[0]


def test_get_executions_paginated_orm_with_filter(db_session: Session):
    """Test: filtrar ejecuciones por estado"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    # Crear ejecuciones con diferentes estados
    exec1 = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash1"
    )
    exec2 = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash2"
    )

    migration_script_crud.update_execution_status_orm(
        db_session, exec1["id"], "success", mark_started=True
    )
    migration_script_crud.update_execution_status_orm(
        db_session, exec2["id"], "failed", mark_started=True
    )

    # Filtrar solo success
    result = migration_script_crud.get_executions_paginated_orm(
        db_session, str(project_id), status_filter="success"
    )

    assert len(result) == 1
    assert result[0]["status"] == "success"


def test_get_executions_paginated_orm_pagination(db_session: Session):
    """Test: paginación de ejecuciones"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    # Crear 10 ejecuciones
    for i in range(10):
        exec_created = migration_script_crud.create_migration_execution_orm(
            db_session, project_id=str(project_id), script_hash=f"hash{i}"
        )
        migration_script_crud.update_execution_status_orm(
            db_session, execution_id=exec_created["id"], status="pending", mark_started=True
        )

    # Primera página
    page1 = migration_script_crud.get_executions_paginated_orm(
        db_session, str(project_id), limit=5, offset=0
    )
    assert len(page1) == 5

    # Segunda página
    page2 = migration_script_crud.get_executions_paginated_orm(
        db_session, str(project_id), limit=5, offset=5
    )
    assert len(page2) == 5

    # Verificar que son diferentes
    assert page1[0]["id"] != page2[0]["id"]


# ============================================================================
# Tests de get_execution_by_project_orm
# ============================================================================


def test_get_execution_by_project_orm_success(db_session: Session):
    """Test: obtener ejecución validando proyecto"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    created = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project_id), script_hash="hash123"
    )

    result = migration_script_crud.get_execution_by_project_orm(
        db_session, execution_id=created["id"], project_id=str(project_id)
    )

    assert result is not None
    assert result["id"] == created["id"]


def test_get_execution_by_project_orm_wrong_project(db_session: Session):
    """Test: no se puede obtener ejecución de otro proyecto"""
    user_id = create_test_user(db_session)
    project1_id = create_test_project(db_session, user_id)
    project2_id = create_test_project(db_session, user_id)

    # Crear ejecución en project1
    created = migration_script_crud.create_migration_execution_orm(
        db_session, project_id=str(project1_id), script_hash="hash123"
    )

    # Intentar obtener con project2
    result = migration_script_crud.get_execution_by_project_orm(
        db_session, execution_id=created["id"], project_id=str(project2_id)
    )

    assert result is None
