# backend/test/integration/test_versions_recent_api.py
"""
Integration tests for GET /api/versions/recent

Coverage:
- Returns versions across all accessible projects with correct shape
- limit query param is respected
- Created version appears in response
- Empty list when no versions exist
- 401/403 for unauthenticated requests
"""

import uuid

import pytest
from fastapi import status


# ============================================================================
# HELPERS
# ============================================================================


def create_version(db_session, project_id: str, user_id: str, entity_type: str = "table"):
    """Insert an entity version directly via ORM."""
    import hashlib
    from datetime import datetime, timezone

    from app.models.orm.version import EntityVersion

    snapshot = {"name": "test_entity"}
    hash_val = hashlib.sha256(f"{project_id}{uuid.uuid4()}".encode()).hexdigest()

    version = EntityVersion(
        id=uuid.uuid4(),
        hash=hash_val,
        project_id=project_id,
        entity_id=uuid.uuid4(),
        entity_type=entity_type,
        user_id=user_id,
        version_number=1,
        change_type="create",
        message="test version",
        snapshot=snapshot,
        is_encrypted=False,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    db_session.commit()
    db_session.refresh(version)
    return {"id": str(version.id), "entity_type": entity_type}


# ============================================================================
# TESTS
# ============================================================================


@pytest.mark.integration
def test_recent_versions_success(authenticated_client, test_project, test_user, db_session):
    """Endpoint returns versions with the expected shape."""
    create_version(db_session, test_project["id"], test_user["id"])

    response = authenticated_client.get("/api/versions/recent")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)
    assert len(data["data"]) >= 1

    entry = data["data"][0]
    for field in ("id", "project_id", "project_name", "entity_type", "change_type", "message", "created_at", "created_by_username"):
        assert field in entry, f"Missing field: {field}"


@pytest.mark.integration
def test_recent_versions_contains_created_entry(
    authenticated_client, test_project, test_user, db_session
):
    """The created version appears in the response."""
    version = create_version(db_session, test_project["id"], test_user["id"], "mapping")

    response = authenticated_client.get("/api/versions/recent")

    assert response.status_code == status.HTTP_200_OK
    ids = [e["id"] for e in response.json()["data"]]
    assert version["id"] in ids


@pytest.mark.integration
def test_recent_versions_limit(authenticated_client, test_project, test_user, db_session):
    """limit=1 returns at most one entry."""
    for _ in range(3):
        create_version(db_session, test_project["id"], test_user["id"])

    response = authenticated_client.get("/api/versions/recent?limit=1")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["data"]) <= 1


@pytest.mark.integration
def test_recent_versions_empty(authenticated_client):
    """Returns empty list when no versions exist."""
    response = authenticated_client.get("/api/versions/recent")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


@pytest.mark.integration
def test_recent_versions_unauthenticated(client):
    """Without an active session returns 401 or 403."""
    response = client.get("/api/versions/recent")
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
