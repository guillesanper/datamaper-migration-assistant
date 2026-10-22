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
