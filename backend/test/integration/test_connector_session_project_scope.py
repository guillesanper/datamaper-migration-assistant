"""
Sesiones de conexión atadas a un proyecto.

Una sesión creada con project_id solo se puede usar desde ese proyecto: en otro proyecto
(aunque sea del mismo usuario) se comporta como inexistente (404). Las sesiones sin
proyecto siguen valiendo para cualquier proyecto del usuario.

Servicio real (cifrado y Redis) sobre FakeRedis, compartido por los routers de conexiones,
mappings y migración. No se conecta a ninguna BD externa (test_connection=false).
"""

import uuid
from unittest.mock import patch

import fakeredis
import pytest

from app.crud.project_crud import ProjectCRUD
from app.routers import db_connections
from app.services.db_connection_service import DBConnectionService
from main import app

ENCRYPTION_KEY = "ZGF0YW1hcC10ZXN0LW1hc3Rlci1rZXktMzItYnl0ZXM="  # base64 de 32 bytes

CONNECTION = {
    "dialect": "postgresql",
    "host": "localhost",
    "port": 5433,
    "database": "test_database",
    "user": "test_user",
    "password": "test_password",
    "ssl_mode": "disable",
}


@pytest.fixture
def shared_redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def scoped_client(authenticated_client, shared_redis):
    """Todos los routers usan el mismo DBConnectionService sobre FakeRedis"""

    def service():
        return DBConnectionService(shared_redis, ENCRYPTION_KEY)

    app.dependency_overrides[db_connections.get_db_connection_service] = service
    with (
        patch("app.routers.migration.get_db_connection_service", service),
        patch("app.routers.mappings.get_redis_client", lambda: shared_redis),
        patch.dict("os.environ", {"ENCRYPTION_MASTER_KEY": ENCRYPTION_KEY}),
    ):
        yield authenticated_client
    app.dependency_overrides.pop(db_connections.get_db_connection_service, None)


@pytest.fixture
def other_project(db_session, test_user):
    """Segundo proyecto del mismo usuario"""
    return ProjectCRUD.create_project_orm(
        db=db_session,
        owner_id=test_user["id"],
        name="Other Project",
        description="Another project of the same user",
        origin_db="PostgreSQL",
        destination_db="PostgreSQL",
        status="active",
    )


def _create_session(client, project_id=None):
    body = {"connection": CONNECTION, "test_connection": False}
    if project_id is not None:
        body["project_id"] = str(project_id)
    return client.post("/api/db-connections/sessions", json=body)


def _execute(client, project_id, dest_session_id):
    return client.post(
        f"/api/projects/{project_id}/migration/execute",
        json={"dry_run": True, "dest_connection_session_id": dest_session_id},
    )


def _save_connector_mapping(client, project_id, origin_session_id):
    return client.post(
        f"/api/mappings/projects/{project_id}/save",
        params={"origin_source_type": "connector", "origin_session_id": origin_session_id},
        json={
            "origin_table": "a",
            "origin_column": "b",
            "destination_table": "c",
            "destination_column": "d",
        },
    )


class TestCreateBoundSession:
    def test_session_is_bound_to_project(
        self, scoped_client, shared_redis, test_project, test_user
    ):
        response = _create_session(scoped_client, test_project["id"])

        assert response.status_code == 201, response.text
        session = DBConnectionService(shared_redis, ENCRYPTION_KEY).get_session(
            test_user["id"], response.json()["session_id"]
        )
        assert session.project_id == str(test_project["id"])

    def test_unknown_or_foreign_project_is_rejected(self, scoped_client, shared_redis):
        response = _create_session(scoped_client, uuid.uuid4())

        assert response.status_code == 404
        assert not list(shared_redis.scan_iter("db_connection_session:*"))

    def test_invalid_project_id_is_rejected(self, scoped_client):
        response = _create_session(scoped_client, "not-a-uuid")

        assert response.status_code == 422


class TestBoundSessionUsedFromAnotherProject:
    def test_migration_rejects_session_of_another_project(
        self, scoped_client, test_project, other_project
    ):
        session_id = _create_session(scoped_client, test_project["id"]).json()["session_id"]

        response = _execute(scoped_client, other_project["id"], session_id)

        assert response.status_code == 404
        assert response.json()["detail"] == "Destination connection session not found"

    def test_save_mapping_rejects_session_of_another_project(
        self, scoped_client, test_project, other_project
    ):
        session_id = _create_session(scoped_client, test_project["id"]).json()["session_id"]

        response = _save_connector_mapping(scoped_client, other_project["id"], session_id)

        assert response.status_code == 404, response.text

    def test_own_project_accepts_bound_session(self, scoped_client, test_project):
        session_id = _create_session(scoped_client, test_project["id"]).json()["session_id"]

        # Pasa la comprobación de sesión; la conexión falla a propósito después (no es 404)
        with patch.object(DBConnectionService, "_get_adapter", side_effect=RuntimeError("no db")):
            response = _execute(scoped_client, test_project["id"], session_id)

        assert response.status_code != 404, response.text

    def test_unbound_session_works_in_any_project(self, scoped_client, other_project):
        session_id = _create_session(scoped_client).json()["session_id"]

        with patch.object(DBConnectionService, "_get_adapter", side_effect=RuntimeError("no db")):
            response = _execute(scoped_client, other_project["id"], session_id)

        assert response.status_code != 404, response.text
