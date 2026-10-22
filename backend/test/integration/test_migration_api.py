"""
Integration Tests for Migration API

Tests all migration endpoints:
- POST /api/projects/{project_id}/migration/generate-script
- POST /api/projects/{project_id}/migration/execute
- GET /api/projects/{project_id}/migration/executions/{execution_id}
- GET /api/projects/{project_id}/migration/executions
- GET /api/projects/{project_id}/migration/dependency-graph

IMPORTANT: Requires database and Redis to be running
"""

import json
import uuid
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

# =============================================
# FIXTURES
# =============================================


@pytest.fixture
def client():
    """Test client for the API"""
    return TestClient(app)


@pytest.fixture
def auth_user(db, worker_id):
    """Create test user and return user data"""
    from conftest import get_unique_user_data

    # Crear usuario de prueba
    username, email = get_unique_user_data(worker_id, "migration_test_user", "migration@test.com")

    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO users (id, username, email, password_hash, is_verified, is_deleted, failed_login_attempts)
        VALUES (%s, %s, %s, %s, true, false, 0)
        ON CONFLICT (email) DO UPDATE SET username = EXCLUDED.username
        RETURNING id, username, email
    """,
        (str(uuid.uuid4()), username, email, "test_password_hash"),
    )

    user = cursor.fetchone()
    db.commit()
    cursor.close()

    return {"id": user[0], "username": user[1], "email": user[2]}


@pytest.fixture
def client_with_auth(client, auth_user):
    """Test client with mocked authentication"""
    from app.routers.dependencies import get_current_user

    # Mock get_current_user to return our test user
    def mock_get_current_user():
        return auth_user

    # Override dependency
    app.dependency_overrides[get_current_user] = mock_get_current_user

    yield client

    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture
def test_project(db, auth_user):
    """Create a test project with mappings"""
    cursor = db.cursor()

    project_id = str(uuid.uuid4())

    # Crear proyecto
    cursor.execute(
        """
        INSERT INTO projects (id, name, owner_id, created_at, updated_at, is_deleted)
        VALUES (%s, %s, %s, NOW(), NOW(), false)
        RETURNING id
    """,
        (project_id, "Test Migration Project", auth_user["id"]),
    )

    # Crear algunos mappings de prueba
    mappings = [
        ("customers", "id", "customers", "customer_id"),
        ("customers", "name", "customers", "customer_name"),
        ("orders", "id", "orders", "order_id"),
        ("orders", "customer_id", "orders", "customer_id"),
    ]

    for origin_table, origin_col, dest_table, dest_col in mappings:
        cursor.execute(
            """
            INSERT INTO mappings (
                id, project_id, origin_table, origin_column,
                destination_table, destination_column,
                origin_source_type, destination_source_type,
                is_encrypted, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 'import', 'import', false, NOW(), NOW())
        """,
            (str(uuid.uuid4()), project_id, origin_table, origin_col, dest_table, dest_col),
        )

    db.commit()
    cursor.close()

    yield project_id

    # Cleanup
    cursor = db.cursor()
    cursor.execute("DELETE FROM mappings WHERE project_id = %s", (project_id,))
    cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))
    db.commit()
    cursor.close()


@pytest.fixture
def mock_db_connection_service():
    """Mock DBConnectionService for tests"""
    with patch("app.routers.migration.get_db_connection_service") as mock:
        service = Mock()

        # Mock session
        session = Mock()
        session.user_id = "test_user_id"
        session.dialect = "postgresql"
        session.host = "localhost"
        session.database = "test_db"

        # Mock config
        config = Mock()
        config.dialect = "postgresql"
        config.host = "localhost"
        config.port = 5432
        config.database = "test_db"
        config.user = "test_user"
        config.password = "test_pass"

        # Mock adapter
        adapter = MagicMock()
        adapter.is_connected = True
        adapter.connection = MagicMock()
        adapter.connection.cursor.return_value = MagicMock()

        service.get_session.return_value = session
        service.get_decrypted_config.return_value = config
        service._get_adapter.return_value = adapter

        mock.return_value = service
        yield service


# =============================================
# TEST: Generate Script
# =============================================


class TestGenerateScript:
    """Tests for POST /api/projects/{project_id}/migration/generate-script"""

    def test_generate_script_success(self, client_with_auth, test_project, db):
        """Test successful script generation"""
        response = client_with_auth.post(
            f"/api/projects/{test_project}/migration/generate-script",
            json={
                "batch_size": 10000,
                "include_constraints": True,
                "include_validation": True,
                "dialect": "postgresql",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "script_id" in data
        assert "script" in data
        assert "estimated_duration_seconds" in data
        assert "estimated_rows" in data
        assert "dependency_order" in data
        assert "created_at" in data

        # Verificar que el script fue guardado en la BD
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT id, script_content FROM migration_scripts
            WHERE id = %s
        """,
            (data["script_id"],),
        )

        script_row = cursor.fetchone()
        assert script_row is not None
        assert script_row[1] == data["script"]
        cursor.close()

    def test_generate_script_unauthorized(self, client, test_project):
        """Test script generation without authentication"""
        response = client.post(
            f"/api/projects/{test_project}/migration/generate-script",
            json={
                "batch_size": 10000,
                "include_constraints": True,
                "include_validation": True,
                "dialect": "postgresql",
            },
        )

        assert response.status_code in [401, 403]

    def test_generate_script_project_not_found(self, client_with_auth):
        """Test script generation for non-existent project"""
        fake_project_id = str(uuid.uuid4())

        response = client_with_auth.post(
            f"/api/projects/{fake_project_id}/migration/generate-script",
            json={
                "batch_size": 10000,
                "include_constraints": True,
                "include_validation": True,
                "dialect": "postgresql",
            },
        )

        assert response.status_code == 404

    def test_generate_script_invalid_dialect(self, client_with_auth, test_project):
        """Test script generation with invalid dialect"""
        response = client_with_auth.post(
            f"/api/projects/{test_project}/migration/generate-script",
            json={
                "batch_size": 10000,
                "include_constraints": True,
                "include_validation": True,
                "dialect": "invalid_dialect",
            },
        )

        assert response.status_code == 422  # Validation error


# =============================================
# TEST: Execute Migration
# =============================================


class TestExecuteMigration:
    """Tests for POST /api/projects/{project_id}/migration/execute"""

    @patch("app.routers.migration.ExecutionService")
    def test_execute_migration_dry_run(
        self,
        mock_execution_service,
        client_with_auth,
        auth_user,
        test_project,
        mock_db_connection_service,
        db,
    ):
        """Test migration execution in dry-run mode"""
        # Mock ExecutionService
        mock_service_instance = Mock()
        mock_service_instance.execute_migration.return_value = {
            "execution_id": str(uuid.uuid4()),
            "status": "dry_run_complete",
            "rows_affected": 0,
            "duration_seconds": 1.5,
            "backup_id": "backup_test",
            "errors": [],
            "execution_log": [],
        }
        mock_execution_service.return_value = mock_service_instance

        # Crear sesión de conexión mock
        session_id = str(uuid.uuid4())

        response = client_with_auth.post(
            f"/api/projects/{test_project}/migration/execute",
            json={"dry_run": True, "dest_connection_session_id": session_id},
        )

        assert response.status_code == 200
        data = response.json()

        assert "execution_id" in data
        assert data["status"] in ["running", "dry_run_complete"]
        assert "message" in data

    @patch("app.routers.migration.ExecutionService")
    def test_execute_migration_with_script_id(
        self,
        mock_execution_service,
        client_with_auth,
        auth_user,
        test_project,
        mock_db_connection_service,
        db,
    ):
        """Test migration execution with saved script_id"""
        # Crear script guardado
        cursor = db.cursor()
        script_id = str(uuid.uuid4())

        cursor.execute(
            """
            INSERT INTO migration_scripts (
                id, project_id, script_content, script_hash,
                batch_size, include_constraints, include_validation, dialect,
                created_by, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        """,
            (
                script_id,
                test_project,
                "SELECT 1;",
                "hash123",
                10000,
                True,
                True,
                "postgresql",
                auth_user["id"],
            ),
        )
        db.commit()
        cursor.close()

        # Mock ExecutionService
        mock_service_instance = Mock()
        mock_service_instance.execute_migration.return_value = {
            "execution_id": str(uuid.uuid4()),
            "status": "success",
            "rows_affected": 1000,
            "duration_seconds": 2.5,
            "backup_id": "backup_test",
            "errors": [],
            "execution_log": [],
        }
        mock_execution_service.return_value = mock_service_instance

        session_id = str(uuid.uuid4())

        response = client_with_auth.post(
            f"/api/projects/{test_project}/migration/execute",
            json={
                "script_id": script_id,
                "dry_run": False,
                "dest_connection_session_id": session_id,
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "execution_id" in data
        assert "status" in data

    def test_execute_migration_unauthorized(self, client, test_project):
        """Test migration execution without authentication"""
        response = client.post(
            f"/api/projects/{test_project}/migration/execute",
            json={"dry_run": True, "dest_connection_session_id": str(uuid.uuid4())},
        )

        assert response.status_code in [401, 403]


# =============================================
# TEST: Get Execution Status
# =============================================


class TestGetExecutionStatus:
    """Tests for GET /api/projects/{project_id}/migration/executions/{execution_id}"""

    def test_get_execution_status(self, client_with_auth, auth_user, test_project, db):
        """Test getting execution status"""
        # Crear ejecución de prueba
        cursor = db.cursor()
        execution_id = str(uuid.uuid4())

        cursor.execute(
            """
            INSERT INTO migration_executions (
                id, project_id, status, script_hash,
                started_at, rows_migrated, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, NOW(), %s, NOW(), NOW())
        """,
            (execution_id, test_project, "running", "hash123", 5000),
        )
        db.commit()
        cursor.close()

        response = client_with_auth.get(
            f"/api/projects/{test_project}/migration/executions/{execution_id}",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["execution_id"] == execution_id
        assert data["status"] == "running"
        assert "progress_percent" in data
        assert "rows_migrated" in data
        assert "started_at" in data
        assert "current_step" in data
        assert "execution_log" in data
        assert "errors" in data

    def test_get_execution_status_not_found(self, client_with_auth, auth_user, test_project):
        """Test getting status for non-existent execution"""
        fake_execution_id = str(uuid.uuid4())

        response = client_with_auth.get(
            f"/api/projects/{test_project}/migration/executions/{fake_execution_id}",
        )

        assert response.status_code in [404, 500]


# =============================================
# TEST: List Executions
# =============================================


class TestListExecutions:
    """Tests for GET /api/projects/{project_id}/migration/executions"""

    def test_list_executions(self, client_with_auth, auth_user, test_project, db):
        """Test listing all executions"""
        # Crear varias ejecuciones
        cursor = db.cursor()

        for i in range(3):
            execution_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO migration_executions (
                    id, project_id, status, script_hash,
                    started_at, rows_migrated, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, NOW(), %s, NOW(), NOW())
            """,
                (execution_id, test_project, "success", f"hash{i}", i * 1000),
            )

        db.commit()
        cursor.close()

        response = client_with_auth.get(
            f"/api/projects/{test_project}/migration/executions",
        )

        assert response.status_code == 200
        data = response.json()

        assert "executions" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert len(data["executions"]) >= 3
        assert data["total"] >= 3

    def test_list_executions_with_filters(self, client_with_auth, auth_user, test_project, db):
        """Test listing executions with status filter"""
        # Crear ejecuciones con diferentes status
        cursor = db.cursor()

        for status in ["success", "failed", "running"]:
            execution_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO migration_executions (
                    id, project_id, status, script_hash,
                    started_at, rows_migrated, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, NOW(), 0, NOW(), NOW())
            """,
                (execution_id, test_project, status, "hash123"),
            )

        db.commit()
        cursor.close()

        # Filtrar por status='success'
        response = client_with_auth.get(
            f"/api/projects/{test_project}/migration/executions?status_filter=success",
        )

        assert response.status_code == 200
        data = response.json()

        assert all(e["status"] == "success" for e in data["executions"])

    def test_list_executions_pagination(self, client_with_auth, auth_user, test_project, db):
        """Test executions list pagination"""
        response = client_with_auth.get(
            f"/api/projects/{test_project}/migration/executions?limit=5&offset=0",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["limit"] == 5
        assert data["offset"] == 0
        assert len(data["executions"]) <= 5


# =============================================
# TEST: Get Dependency Graph
# =============================================


class TestDependencyGraph:
    """Tests for GET /api/projects/{project_id}/migration/dependency-graph"""

    def test_get_dependency_graph(self, client_with_auth, auth_user, test_project):
        """Test getting dependency graph"""
        response = client_with_auth.get(
            f"/api/projects/{test_project}/migration/dependency-graph",
        )

        assert response.status_code == 200
        data = response.json()

        assert "execution_order" in data
        assert "circular_dependencies" in data
        assert "independent_tables" in data
        assert "graph_visualization" in data

        # Verificar estructura del grafo
        assert "nodes" in data["graph_visualization"]
        assert "edges" in data["graph_visualization"]

        # Verificar que hay tablas
        assert len(data["execution_order"]) > 0

    def test_get_dependency_graph_empty_project(self, client_with_auth, auth_user, db):
        """Test dependency graph for project without mappings"""
        # Crear proyecto sin mappings
        cursor = db.cursor()
        project_id = str(uuid.uuid4())

        cursor.execute(
            """
            INSERT INTO projects (id, name, owner_id, created_at, updated_at, is_deleted)
            VALUES (%s, %s, %s, NOW(), NOW(), false)
        """,
            (project_id, "Empty Project", auth_user["id"]),
        )
        db.commit()
        cursor.close()

        response = client_with_auth.get(
            f"/api/projects/{project_id}/migration/dependency-graph",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["execution_order"] == []
        assert data["circular_dependencies"] == []
        assert data["independent_tables"] == []
        assert data["graph_visualization"]["nodes"] == []
        assert data["graph_visualization"]["edges"] == []

        # Cleanup
        cursor = db.cursor()
        cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        db.commit()
        cursor.close()


# =============================================
# TEST: Role-based access (viewers can't write to the destination DB)
# =============================================


@pytest.fixture
def member_client(client, db, worker_id, test_project):
    """Factory: test client authenticated as a project member with the given role"""
    from conftest import get_unique_user_data

    from app.routers.dependencies import get_current_user

    created_users = []

    def make(role: str):
        username, email = get_unique_user_data(
            worker_id, f"migration_{role}_user", f"migration_{role}@test.com"
        )
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO users (id, username, email, password_hash, is_verified, is_deleted, failed_login_attempts)
            VALUES (%s, %s, %s, %s, true, false, 0)
            ON CONFLICT (email) DO UPDATE SET username = EXCLUDED.username
            RETURNING id, username, email
        """,
            (str(uuid.uuid4()), username, email, "test_password_hash"),
        )
        user = cursor.fetchone()
        cursor.execute(
            """
            INSERT INTO project_members (id, project_id, user_id, role, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (project_id, user_id) DO UPDATE SET role = EXCLUDED.role
        """,
            (str(uuid.uuid4()), test_project, user[0], role),
        )
        db.commit()
        cursor.close()
        created_users.append(user[0])

        member = {"id": user[0], "username": user[1], "email": user[2]}
        app.dependency_overrides[get_current_user] = lambda: member
        return client

    yield make

    app.dependency_overrides.clear()
    cursor = db.cursor()
    for user_id in created_users:
        cursor.execute("DELETE FROM project_members WHERE user_id = %s", (user_id,))
    db.commit()
    cursor.close()


class TestMigrationRoleAccess:
    def test_viewer_cannot_generate_script(self, member_client, test_project):
        client = member_client("viewer")

        response = client.post(
            f"/api/projects/{test_project}/migration/generate-script",
            json={"dialect": "postgresql"},
        )

        assert response.status_code == 403

    @patch("app.routers.migration.ExecutionService")
    def test_viewer_cannot_execute_migration(
        self, mock_execution_service, member_client, test_project, mock_db_connection_service
    ):
        client = member_client("viewer")

        response = client.post(
            f"/api/projects/{test_project}/migration/execute",
            json={"dry_run": True, "dest_connection_session_id": str(uuid.uuid4())},
        )

        assert response.status_code == 403
        mock_execution_service.assert_not_called()
        mock_db_connection_service._get_adapter.assert_not_called()

    def test_viewer_can_read_dependency_graph(self, member_client, test_project):
        client = member_client("viewer")

        response = client.get(f"/api/projects/{test_project}/migration/dependency-graph")

        assert response.status_code == 200

    def test_editor_can_generate_script(self, member_client, test_project):
        client = member_client("editor")

        response = client.post(
            f"/api/projects/{test_project}/migration/generate-script",
            json={"dialect": "postgresql"},
        )

        assert response.status_code == 200


class TestExecuteMigrationConnectionHandling:
    @patch("app.routers.migration.ExecutionService")
    def test_destination_adapter_is_disconnected_and_dialect_used(
        self, mock_execution_service, client_with_auth, test_project, mock_db_connection_service
    ):
        mock_db_connection_service.get_decrypted_config.return_value.dialect = "mysql"
        mock_execution_service.return_value.execute_migration.return_value = {
            "execution_id": str(uuid.uuid4()),
            "status": "dry_run_complete",
            "rows_affected": 0,
        }

        response = client_with_auth.post(
            f"/api/projects/{test_project}/migration/execute",
            json={"dry_run": True, "dest_connection_session_id": str(uuid.uuid4())},
        )

        assert response.status_code == 200
        adapter = mock_db_connection_service._get_adapter.return_value
        adapter.disconnect.assert_called_once()
        script = mock_execution_service.return_value.execute_migration.call_args.kwargs["script"]
        assert "START TRANSACTION;" in script  # generated for the destination's dialect


def test_blocking_endpoints_run_in_threadpool():
    """Endpoints that talk to external DBs must be sync so they don't block the event loop"""
    import inspect

    from app.routers import db_connections, migration

    for module in (db_connections, migration):
        for route in module.router.routes:
            assert not inspect.iscoroutinefunction(route.endpoint), route.path


# =============================================
# TEST: Real execution against a real PostgreSQL destination (no ExecutionService mock)
# =============================================


@pytest.fixture
def real_destination(db, auth_user):
    """
    Proyecto con mappings src_people -> dst_people y un adapter PostgreSQL real
    apuntando a la BD de test (hace de BD externa origen/destino).
    """
    import os

    from app.utils.db_adapters import PostgreSQLAdapter

    suffix = uuid.uuid4().hex[:8]
    src, dst = f"mig_src_{suffix}", f"mig_dst_{suffix}"
    project_id = str(uuid.uuid4())

    cursor = db.cursor()
    cursor.execute(f"CREATE TABLE {src} (name text)")
    cursor.execute(f"INSERT INTO {src} VALUES ('ana'), ('it''s; tricky -- text')")
    cursor.execute(f"CREATE TABLE {dst} (full_name text)")
    cursor.execute(
        """
        INSERT INTO projects (id, name, owner_id, created_at, updated_at, is_deleted)
        VALUES (%s, %s, %s, NOW(), NOW(), false)
    """,
        (project_id, "Real Exec\nDROP TABLE projects;", auth_user["id"]),
    )
    cursor.execute(
        """
        INSERT INTO mappings (
            id, project_id, origin_table, origin_column, destination_table, destination_column,
            origin_source_type, destination_source_type, is_encrypted, created_at, updated_at
        ) VALUES (%s, %s, %s, 'name', %s, 'full_name', 'import', 'import', false, NOW(), NOW())
    """,
        (str(uuid.uuid4()), project_id, src, dst),
    )
    db.commit()

    adapter_config = {
        "host": os.environ.get("TEST_DB_HOST", "localhost"),
        "port": int(os.environ.get("TEST_DB_PORT", "5432")),
        "database": os.environ["DB_NAME"],
        "user": os.environ.get("TEST_DB_USER", "postgres"),
        "password": os.environ.get("TEST_DB_PASSWORD", "postgres"),
        "ssl_mode": "disable",
    }

    with patch("app.routers.migration.get_db_connection_service") as get_service:
        service = Mock()
        service.get_session.return_value = Mock()
        service.get_decrypted_config.return_value = Mock(dialect="postgresql")
        service._get_adapter.side_effect = lambda *a, **kw: PostgreSQLAdapter(adapter_config)
        get_service.return_value = service
        yield {"project_id": project_id, "dst": dst}

    cursor.execute(f"DROP TABLE IF EXISTS {src}")
    cursor.execute(f"DROP TABLE IF EXISTS {dst}")
    cursor.execute("DELETE FROM migration_executions WHERE project_id = %s", (project_id,))
    cursor.execute("DELETE FROM mappings WHERE project_id = %s", (project_id,))
    cursor.execute("DELETE FROM project_activity WHERE project_id = %s", (project_id,))
    cursor.execute("DELETE FROM notifications WHERE project_id = %s", (project_id,))
    cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))
    db.commit()
    cursor.close()


class TestRealMigrationExecution:
    def _execute(self, client, project_id, dry_run):
        return client.post(
            f"/api/projects/{project_id}/migration/execute",
            json={"dry_run": dry_run, "dest_connection_session_id": str(uuid.uuid4())},
        )

    def _count(self, db, table):
        cursor = db.cursor()
        cursor.execute(f"SELECT count(*) FROM {table}")
        count = cursor.fetchone()[0]
        db.commit()
        cursor.close()
        return count

    def test_execute_persists_rows_and_records_execution(
        self, client_with_auth, real_destination, db
    ):
        project_id = real_destination["project_id"]

        response = self._execute(client_with_auth, project_id, dry_run=False)

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "success"
        assert self._count(db, real_destination["dst"]) == 2
        # La inyección en el nombre del proyecto quedó en un comentario
        assert self._count(db, "projects") >= 1

        status_response = client_with_auth.get(
            f"/api/projects/{project_id}/migration/executions/{data['execution_id']}"
        )
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "success"

    def test_dry_run_persists_nothing(self, client_with_auth, real_destination, db):
        response = self._execute(client_with_auth, real_destination["project_id"], dry_run=True)

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "dry_run_complete"
        assert self._count(db, real_destination["dst"]) == 0

    def test_execute_does_not_write_backup_files(self, client_with_auth, real_destination):
        from pathlib import Path

        backups_dir = Path(__file__).resolve().parents[2] / "backups"
        before = set(backups_dir.glob("*")) if backups_dir.exists() else set()

        response = self._execute(client_with_auth, real_destination["project_id"], dry_run=False)

        assert response.status_code == 200, response.text
        after = set(backups_dir.glob("*")) if backups_dir.exists() else set()
        assert after == before


# =============================================
# TEST: Migración entre dos BDs reales distintas y mappings connector
# =============================================

ORIGIN_PG = {
    "host": "localhost",
    "port": 5433,
    "database": "test_database",
    "user": "test_user",
    "password": "test_password",
}


def _sha(name):
    import hashlib

    return hashlib.sha256(name.encode()).hexdigest()


@pytest.fixture
def cross_db(db, auth_user):
    """
    Origen: PostgreSQL de docker-compose.test.yml (5433), tabla con nombre mixto en un
    schema propio. Destino: la BD de test de la app. Mappings connector en origen e
    import en destino, como los crea el frontend al conectar el origen.
    """
    import os

    import psycopg2

    from app.models.db_connection import DBConnectionConfig
    from app.utils.db_adapters import PostgreSQLAdapter

    try:
        origin_conn = psycopg2.connect(connect_timeout=3, **ORIGIN_PG)
    except psycopg2.OperationalError:
        pytest.skip("PostgreSQL origin instance not available on port 5433")
    origin_conn.autocommit = True

    suffix = uuid.uuid4().hex[:8]
    schema, origin_table = f"crm_{suffix}", "Clientes"
    dst = f"xdb_dst_{suffix}"
    project_id = str(uuid.uuid4())
    origin_session, dest_session = str(uuid.uuid4()), str(uuid.uuid4())

    with origin_conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {schema}")
        cur.execute(f'CREATE TABLE {schema}."{origin_table}" ("Nombre" text, email text)')
        cur.execute(
            f'INSERT INTO {schema}."{origin_table}" '
            "SELECT 'cliente ' || g, 'c' || g || '@x.com' FROM generate_series(1, 25) g"
        )
        cur.execute(
            f"INSERT INTO {schema}.\"{origin_table}\" VALUES ('it''s; DROP TABLE x; --', NULL)"
        )

    cursor = db.cursor()
    cursor.execute(f"CREATE TABLE {dst} (full_name text, mail text)")
    cursor.execute(
        """
        INSERT INTO projects (id, name, owner_id, created_at, updated_at, is_deleted)
        VALUES (%s, %s, %s, NOW(), NOW(), false)
    """,
        (project_id, "Cross DB", auth_user["id"]),
    )

    def add_mapping(origin_column, dest_column, transformation=None):
        cursor.execute(
            """
            INSERT INTO mappings (
                id, project_id, origin_source_type, origin_table_hash, origin_column_hash,
                origin_session_id, destination_source_type, destination_table,
                destination_column, transformation_logic, is_encrypted, created_at, updated_at
            ) VALUES (%s, %s, 'connector', %s, %s, %s, 'import', %s, %s, %s, false,
                      NOW(), NOW())
        """,
            (
                str(uuid.uuid4()),
                project_id,
                _sha(origin_table),
                _sha(origin_column),
                origin_session,
                dst,
                dest_column,
                transformation,
            ),
        )

    add_mapping("Nombre", "full_name", "UPPER({column})")
    add_mapping("email", "mail")
    db.commit()

    configs = {
        origin_session: DBConnectionConfig(dialect="postgresql", ssl_mode="disable", **ORIGIN_PG),
        dest_session: DBConnectionConfig(
            dialect="postgresql",
            host=os.environ.get("TEST_DB_HOST", "localhost"),
            port=int(os.environ.get("TEST_DB_PORT", "5432")),
            database=os.environ["DB_NAME"],
            user=os.environ.get("TEST_DB_USER", "postgres"),
            password=os.environ.get("TEST_DB_PASSWORD", "postgres"),
            ssl_mode="disable",
        ),
    }
    opened = []

    def make_adapter(config, **kwargs):
        adapter = PostgreSQLAdapter(config.to_adapter_config())
        opened.append(adapter)
        return adapter

    with patch("app.routers.migration.get_db_connection_service") as get_service:
        service = Mock()
        service.get_session.side_effect = lambda user_id, sid, project_id=None: Mock(session_id=sid)
        service.get_decrypted_config.side_effect = lambda session: configs[session.session_id]
        service._get_adapter.side_effect = make_adapter
        get_service.return_value = service
        yield {
            "project_id": project_id,
            "dst": dst,
            "schema": schema,
            "origin_session": origin_session,
            "dest_session": dest_session,
            "service": service,
            "opened": opened,
            "add_mapping": add_mapping,
            "db": db,
        }

    with origin_conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    origin_conn.close()
    cursor.execute(f"DROP TABLE IF EXISTS {dst}")
    for table in (
        "migration_executions",
        "migration_scripts",
        "mappings",
        "project_activity",
        "notifications",
    ):
        cursor.execute(f"DELETE FROM {table} WHERE project_id = %s", (project_id,))
    cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))
    db.commit()
    cursor.close()


class TestCrossDatabaseMigration:
    def _rows(self, db, table):
        cursor = db.cursor()
        cursor.execute(f"SELECT full_name, mail FROM {table} ORDER BY full_name")
        rows = cursor.fetchall()
        db.commit()
        cursor.close()
        return rows

    def _execute(self, client, ctx, dry_run=False, with_origin=True, script_id=None):
        body = {"dry_run": dry_run, "dest_connection_session_id": ctx["dest_session"]}
        if with_origin:
            body["origin_connection_session_id"] = ctx["origin_session"]
        if script_id:
            body["script_id"] = script_id
        return client.post(f"/api/projects/{ctx['project_id']}/migration/execute", json=body)

    def test_copies_rows_between_databases(self, client_with_auth, cross_db):
        response = self._execute(client_with_auth, cross_db)

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "success", data

        rows = self._rows(cross_db["db"], cross_db["dst"])
        assert len(rows) == 26
        # Transformación evaluada en el origen y datos "peligrosos" copiados como datos
        assert ("CLIENTE 1", "c1@x.com") in rows
        assert ("IT'S; DROP TABLE X; --", None) in rows
        # Todas las conexiones abiertas se cierran
        assert all(not adapter.is_connected for adapter in cross_db["opened"])

    def test_dry_run_copies_nothing(self, client_with_auth, cross_db):
        response = self._execute(client_with_auth, cross_db, dry_run=True)

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "dry_run_complete"
        assert self._rows(cross_db["db"], cross_db["dst"]) == []

    def test_uses_session_stored_in_mappings_when_not_given(self, client_with_auth, cross_db):
        response = self._execute(client_with_auth, cross_db, with_origin=False)

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "success"
        assert len(self._rows(cross_db["db"], cross_db["dst"])) == 26

    def test_generated_copy_plan_executes_with_its_options(self, client_with_auth, cross_db):
        generated = client_with_auth.post(
            f"/api/projects/{cross_db['project_id']}/migration/generate-script",
            json={
                "dialect": "postgresql",
                "batch_size": 7,
                "origin_connection_session_id": cross_db["origin_session"],
                "dest_connection_session_id": cross_db["dest_session"],
            },
        )
        assert generated.status_code == 200, generated.text
        script = generated.json()["script"]
        assert script.startswith("-- DATAMAP CROSS-DATABASE COPY PLAN")
        assert f'FROM "{cross_db["schema"]}"."Clientes"' in script

        response = self._execute(
            client_with_auth, cross_db, script_id=generated.json()["script_id"]
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "success"
        assert len(self._rows(cross_db["db"], cross_db["dst"])) == 26

        # El plan no se puede ejecutar como script SQL en el destino
        response = self._execute(
            client_with_auth, cross_db, with_origin=False, script_id=generated.json()["script_id"]
        )
        assert response.status_code == 400
        assert "origin_connection_session_id" in response.json()["detail"]

    def test_failure_rolls_back_destination(self, client_with_auth, cross_db):
        # Una columna destino inexistente hace fallar la tabla: nada queda escrito
        cross_db["add_mapping"]("email", "missing_column")
        cross_db["db"].commit()

        response = self._execute(client_with_auth, cross_db)

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "failed"
        assert self._rows(cross_db["db"], cross_db["dst"]) == []

    def test_expired_stored_session_is_reported(self, client_with_auth, cross_db):
        from app.services.db_connection_service import SessionNotFoundError

        def get_session(user_id, sid, project_id=None):
            if sid == cross_db["origin_session"]:
                raise SessionNotFoundError("gone")
            return Mock(session_id=sid)

        cross_db["service"].get_session.side_effect = get_session

        response = self._execute(client_with_auth, cross_db, with_origin=False)

        assert response.status_code == 404
        assert response.json()["detail"] == "Origin connection session not found"
        # El destino ya abierto se desconecta igualmente
        assert all(not adapter.is_connected for adapter in cross_db["opened"])


class TestSameDatabaseConnectorMappings:
    def test_connector_names_resolved_and_quoted_exactly(
        self, client_with_auth, real_destination, db, auth_user
    ):
        """Mappings connector en ambos lados sobre la misma BD: script INSERT ... SELECT."""
        session_id = str(uuid.uuid4())
        project_id = real_destination["project_id"]
        suffix = uuid.uuid4().hex[:8]
        src, dst = f"Src{suffix}", f"view_{suffix}"

        cursor = db.cursor()
        cursor.execute(f'CREATE TABLE "{src}" ("Name" text)')
        cursor.execute(f"INSERT INTO \"{src}\" VALUES ('ana'), ('luis')")
        cursor.execute(f'CREATE TABLE "{dst}" ("Full Name" text)')
        cursor.execute("DELETE FROM mappings WHERE project_id = %s", (project_id,))
        cursor.execute(
            """
            INSERT INTO mappings (
                id, project_id, origin_source_type, origin_table_hash, origin_column_hash,
                origin_session_id, destination_source_type, destination_table_hash,
                destination_column_hash, destination_session_id, is_encrypted,
                created_at, updated_at
            ) VALUES (%s, %s, 'connector', %s, %s, %s, 'connector', %s, %s, %s, false,
                      NOW(), NOW())
        """,
            (
                str(uuid.uuid4()),
                project_id,
                _sha(src),
                _sha("Name"),
                session_id,
                _sha(dst),
                _sha("Full Name"),
                session_id,
            ),
        )
        db.commit()

        try:
            response = client_with_auth.post(
                f"/api/projects/{project_id}/migration/execute",
                json={"dry_run": False, "dest_connection_session_id": session_id},
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "success", response.json()

            cursor.execute(f'SELECT count(*) FROM "{dst}"')
            assert cursor.fetchone()[0] == 2
            db.commit()
        finally:
            cursor.execute(f'DROP TABLE IF EXISTS "{src}"')
            cursor.execute(f'DROP TABLE IF EXISTS "{dst}"')
            db.commit()
            cursor.close()


class TestEncryptedMappings:
    @pytest.fixture
    def encrypted_project(self, db, auth_user):
        project_id = str(uuid.uuid4())
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO projects (id, name, owner_id, created_at, updated_at, is_deleted)
            VALUES (%s, 'Encrypted', %s, NOW(), NOW(), false)
        """,
            (project_id, auth_user["id"]),
        )
        cursor.execute(
            """
            INSERT INTO mappings (
                id, project_id, origin_source_type, destination_source_type,
                origin_table_encrypted, origin_table_nonce,
                origin_column_encrypted, origin_column_nonce,
                destination_table_encrypted, destination_table_nonce,
                destination_column_encrypted, destination_column_nonce,
                transformation_logic_encrypted, transformation_logic_nonce,
                is_encrypted, created_at, updated_at
            ) VALUES (%s, %s, 'import', 'import', 'x', 'n', 'x', 'n', 'x', 'n', 'x', 'n',
                      'x', 'n', true, NOW(), NOW())
        """,
            (str(uuid.uuid4()), project_id),
        )
        db.commit()
        yield project_id
        cursor.execute("DELETE FROM migration_scripts WHERE project_id = %s", (project_id,))
        cursor.execute("DELETE FROM mappings WHERE project_id = %s", (project_id,))
        cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        db.commit()
        cursor.close()

    def test_generate_without_encryption_session_is_locked(
        self, client_with_auth, encrypted_project
    ):
        response = client_with_auth.post(
            f"/api/projects/{encrypted_project}/migration/generate-script",
            json={"dialect": "postgresql"},
        )

        assert response.status_code == 423
        assert "encryption" in response.json()["detail"]

    @patch("app.routers.migration.ExecutionService")
    def test_execute_without_encryption_session_is_locked(
        self, mock_execution_service, client_with_auth, encrypted_project
    ):
        response = client_with_auth.post(
            f"/api/projects/{encrypted_project}/migration/execute",
            json={"dry_run": True, "dest_connection_session_id": str(uuid.uuid4())},
        )

        assert response.status_code == 423
        mock_execution_service.return_value.execute_migration.assert_not_called()

    def test_encryption_key_from_session_is_used(self, encrypted_project, db):
        from app.routers import migration

        with patch.object(migration.mappings_crud, "get_mappings_by_project_orm") as get:
            get.return_value = [
                {
                    "destination_table": "t",
                    "destination_column": "c",
                    "transformation_logic_encrypted": "x",
                    "transformation_logic": "UPPER({column})",
                }
            ]
            migration.get_project_mappings(db, encrypted_project, b"k" * 32)

        assert get.call_args.kwargs["encryption_key"] == b"k" * 32
