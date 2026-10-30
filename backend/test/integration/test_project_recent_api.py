# backend/test/integration/test_project_recent_api.py
"""
Tests de integración para los endpoints de proyectos recientes.

Cobertura:
- GET /api/projects/recent — lista proyectos ordenados por last_accessed_at
- GET /api/projects/{project_id} — actualiza last_accessed_at al acceder
"""

import pytest
from fastapi import status

# ============================================================================
# TESTS - GET /api/projects/recent
# ============================================================================


@pytest.mark.integration
def test_get_recent_projects_success(authenticated_client, test_project):
    """Endpoint devuelve lista de proyectos con estructura correcta"""
    # Acceder al proyecto para que tenga last_accessed_at
    authenticated_client.get(f"/api/projects/{test_project['id']}")

    response = authenticated_client.get("/api/projects/recent")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    assert "projects" in data["data"]
    assert "total" in data["data"]
    assert isinstance(data["data"]["projects"], list)
    assert data["data"]["total"] == len(data["data"]["projects"])


@pytest.mark.integration
def test_get_recent_projects_contains_accessed_project(authenticated_client, test_project):
    """El proyecto accedido aparece en la lista de recientes"""
    project_id = test_project["id"]

    # Acceder al proyecto para registrar el timestamp
    authenticated_client.get(f"/api/projects/{project_id}")

    response = authenticated_client.get("/api/projects/recent")

    assert response.status_code == status.HTTP_200_OK
    project_ids = [p["id"] for p in response.json()["data"]["projects"]]
    assert project_id in project_ids


@pytest.mark.integration
def test_get_recent_projects_default_limit(authenticated_client, test_project):
    """El límite por defecto es 5 (máximo devuelto)"""
    response = authenticated_client.get("/api/projects/recent")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["data"]["projects"]) <= 5


@pytest.mark.integration
def test_get_recent_projects_custom_limit(authenticated_client, test_project):
    """El parámetro limit=1 restringe a un proyecto máximo"""
    # Asegurarse de que hay al menos un proyecto accedido
    authenticated_client.get(f"/api/projects/{test_project['id']}")

    response = authenticated_client.get("/api/projects/recent?limit=1")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["data"]["projects"]) <= 1


@pytest.mark.integration
def test_get_recent_projects_limit_too_low(authenticated_client):
    """limit=0 devuelve 422 Unprocessable Entity"""
    response = authenticated_client.get("/api/projects/recent?limit=0")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.integration
def test_get_recent_projects_limit_too_high(authenticated_client):
    """limit=21 devuelve 422 Unprocessable Entity"""
    response = authenticated_client.get("/api/projects/recent?limit=21")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.integration
def test_get_recent_projects_unauthenticated(client):
    """Sin sesión activa devuelve 401 o 403"""
    response = client.get("/api/projects/recent")
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )


# ============================================================================
# TESTS - GET /api/projects/{project_id} actualiza last_accessed_at
# ============================================================================


@pytest.mark.integration
def test_get_project_updates_last_accessed_at(authenticated_client, test_project, db_session):
    """Acceder a un proyecto por ID actualiza su last_accessed_at"""
    from app.models.orm import Project

    project_id = test_project["id"]

    # Leer el estado inicial
    db_session.expire_all()
    project_before = db_session.query(Project).filter(Project.id == project_id).first()
    before = project_before.last_accessed_at if project_before else None

    # Acceder vía API
    response = authenticated_client.get(f"/api/projects/{project_id}")
    assert response.status_code == status.HTTP_200_OK

    # Verificar que el timestamp se actualizó
    db_session.expire_all()
    project_after = db_session.query(Project).filter(Project.id == project_id).first()
    assert project_after is not None
    assert project_after.last_accessed_at is not None
    if before is not None:
        assert project_after.last_accessed_at >= before


@pytest.mark.integration
def test_get_project_still_returns_data_if_timestamp_update_fails(
    authenticated_client, test_project, monkeypatch
):
    """El endpoint devuelve el proyecto aunque falle la actualización del timestamp"""
    from app.services import project_service

    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated DB failure")

    monkeypatch.setattr(
        project_service.ProjectService, "update_project_last_accessed", failing_update
    )

    response = authenticated_client.get(f"/api/projects/{test_project['id']}")

    # La respuesta debe ser exitosa; el error de timestamp es silenciado en el router
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["data"]["project"]["id"] == test_project["id"]
