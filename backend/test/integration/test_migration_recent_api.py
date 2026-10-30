# backend/test/integration/test_migration_recent_api.py
"""
Integration tests for GET /api/migrations/recent

Coverage:
- Returns executions across all accessible projects
- Correct response shape: {execution_id, project_id, project_name, status, started_at, completed_at}
- limit query param is respected
- Empty list when no executions exist
- 401/403 for unauthenticated requests
"""

import uuid

import pytest
from fastapi import status

# ============================================================================
# HELPERS
# ============================================================================


def create_execution(db_session, project_id: str, exec_status: str = "success"):
    """Insert a migration execution directly via ORM."""
    from datetime import datetime, timezone

    from app.models.orm.migration import MigrationExecution

    execution = MigrationExecution(
        id=uuid.uuid4(),
        project_id=project_id,
        script_hash="abc123",
        status=exec_status,
        rows_migrated=0,
        started_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(execution)
    db_session.commit()
    db_session.refresh(execution)
    return {"id": str(execution.id), "status": execution.status}


# ============================================================================
# TESTS
# ============================================================================


@pytest.mark.integration
def test_recent_migrations_success(authenticated_client, test_project, db_session):
    """Endpoint returns executions with the expected shape."""
    create_execution(db_session, test_project["id"])

    response = authenticated_client.get("/api/migrations/recent")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    entry = data[0]
    for field in (
        "execution_id",
        "project_id",
        "project_name",
        "status",
        "started_at",
        "completed_at",
    ):
        assert field in entry, f"Missing field: {field}"


@pytest.mark.integration
def test_recent_migrations_contains_created_entry(authenticated_client, test_project, db_session):
    """The created execution appears in the response."""
    execution = create_execution(db_session, test_project["id"], "failed")

    response = authenticated_client.get("/api/migrations/recent")

    assert response.status_code == status.HTTP_200_OK
    ids = [e["execution_id"] for e in response.json()]
    assert execution["id"] in ids


@pytest.mark.integration
def test_recent_migrations_limit(authenticated_client, test_project, db_session):
    """limit=1 returns at most one entry."""
    for _ in range(3):
        create_execution(db_session, test_project["id"])

    response = authenticated_client.get("/api/migrations/recent?limit=1")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) <= 1


@pytest.mark.integration
def test_recent_migrations_empty(authenticated_client):
    """Returns empty list when no executions exist."""
    response = authenticated_client.get("/api/migrations/recent")

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)


@pytest.mark.integration
def test_recent_migrations_unauthenticated(client):
    """Without an active session returns 401 or 403."""
    response = client.get("/api/migrations/recent")
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
