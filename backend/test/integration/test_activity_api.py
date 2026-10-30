# backend/test/integration/test_activity_api.py
"""
Integration tests for GET /api/activity/global

Coverage:
- Returns activities from all accessible projects
- Correct response structure: {id, project_id, activity_type, description, created_at, username}
- Pagination (limit/offset)
- Empty list when no activity exists
- 401/403 for unauthenticated requests
"""

import pytest
from fastapi import status

# ============================================================================
# HELPERS
# ============================================================================


def create_activity(db_session, project_id: str, user_id: str, activity_type: str = "test_action"):
    """Insert an activity log entry directly via ORM."""
    from app.crud.activity_crud import create_activity_log_orm

    return create_activity_log_orm(
        db=db_session,
        project_id=project_id,
        user_id=user_id,
        activity_type=activity_type,
        description=f"Test {activity_type} on project {project_id}",
    )


# ============================================================================
# TESTS
# ============================================================================


@pytest.mark.integration
def test_global_activity_success(authenticated_client, test_project, test_user, db_session):
    """Endpoint returns activities from accessible projects with correct structure"""
    create_activity(db_session, test_project["id"], test_user["id"])

    response = authenticated_client.get("/api/activity/global")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) >= 1

    entry = data["data"][0]
    for field in ("id", "project_id", "activity_type", "description", "created_at", "username"):
        assert field in entry, f"Missing field: {field}"


@pytest.mark.integration
def test_global_activity_contains_logged_entry(
    authenticated_client, test_project, test_user, db_session
):
    """The logged activity appears in the global feed"""
    activity = create_activity(db_session, test_project["id"], test_user["id"], "table_created")

    response = authenticated_client.get("/api/activity/global")

    assert response.status_code == status.HTTP_200_OK
    ids = [e["id"] for e in response.json()["data"]]
    assert activity["id"] in ids


@pytest.mark.integration
def test_global_activity_default_limit(authenticated_client):
    """Default limit caps the response at ≤20 entries"""
    response = authenticated_client.get("/api/activity/global")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) <= 20


@pytest.mark.integration
def test_global_activity_limit(authenticated_client, test_project, test_user, db_session):
    """limit=1 returns at most one entry"""
    for i in range(3):
        create_activity(db_session, test_project["id"], test_user["id"], f"action_{i}")

    response = authenticated_client.get("/api/activity/global?limit=1")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["data"]) <= 1


@pytest.mark.integration
def test_global_activity_offset(authenticated_client, test_project, test_user, db_session):
    """offset skips entries; offset >= total returns empty list"""
    for i in range(2):
        create_activity(db_session, test_project["id"], test_user["id"], f"action_{i}")

    response_all = authenticated_client.get("/api/activity/global?limit=100&offset=0")
    total = len(response_all.json()["data"])

    response_skip = authenticated_client.get(f"/api/activity/global?limit=100&offset={total}")
    assert response_skip.status_code == status.HTTP_200_OK
    assert response_skip.json()["data"] == []


@pytest.mark.integration
def test_global_activity_invalid_limit(authenticated_client):
    """limit=0 returns 422 Unprocessable Entity"""
    response = authenticated_client.get("/api/activity/global?limit=0")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.integration
def test_global_activity_unauthenticated(client):
    """Without an active session returns 401 or 403"""
    response = client.get("/api/activity/global")
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
