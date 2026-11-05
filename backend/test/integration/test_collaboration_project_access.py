"""
Endpoints de colaboración (locks, versions, activity, comments) sobre un proyecto ajeno.

Solo comprobaban que hubiera sesión: cualquier usuario registrado podía leer versiones,
comentarios y actividad de otros proyectos, restaurar versiones, forzar desbloqueos o
comentar en ellos. Ahora hace falta ser owner o miembro, y algunos cambios exigen rol.
"""

import uuid

import pytest


def _create_other_user(db_session):
    from app.services.auth_service import AuthService

    suffix = uuid.uuid4().hex[:10]
    other = AuthService(db_session).create_user(
        username=f"other_{suffix}", email=f"other_{suffix}@example.com", password="Str0ng!Pass1"
    )
    return str(other["user_id"])


@pytest.fixture
def foreign(db_session):
    """Proyecto de otro usuario con versión, tag, comentario, lock y actividad."""
    from app.crud import (
        activity_crud,
        comments_crud,
        locks_crud,
        tags_crud,
        versions_crud,
    )
    from app.crud.project_crud import ProjectCRUD

    owner_id = _create_other_user(db_session)
    project = ProjectCRUD.create_project_orm(
        db=db_session,
        owner_id=owner_id,
        name="Foreign",
        description="",
        origin_db="PostgreSQL",
        destination_db="PostgreSQL",
        status="active",
    )
    project_id = str(project["id"])
    entity_id = str(uuid.uuid4())

    version = versions_crud.create_version_orm(
        db=db_session,
        project_id=project_id,
        entity_id=entity_id,
        entity_type="table",
        user_id=owner_id,
        version_number=1,
        change_type="create",
        snapshot={"name": "secret_salaries"},
        hash=uuid.uuid4().hex,
    )
    tag = tags_crud.create_tag_orm(
        db=db_session,
        version_id=str(version["id"]),
        project_id=project_id,
        name=f"v1-{uuid.uuid4().hex[:6]}",
        created_by=owner_id,
    )
    comment = comments_crud.create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="table",
        project_id=project_id,
        user_id=owner_id,
        content="secret comment",
    )
    lock = locks_crud.acquire_lock_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="table",
        project_id=project_id,
        user_id=owner_id,
    )
    activity_crud.create_activity_log_orm(
        db=db_session,
        project_id=project_id,
        user_id=owner_id,
        activity_type="table_created",
        entity_id=entity_id,
        entity_type="table",
        description="Created secret_salaries",
    )

    return {
        "owner_id": owner_id,
        "project_id": project_id,
        "entity_id": entity_id,
        "version_id": str(version["id"]),
        "tag_id": str(tag["id"]),
        "comment_id": str(comment["id"]),
        "lock_id": str(lock["id"]),
    }


@pytest.fixture
def as_viewer(db_session, foreign, test_user):
    """El usuario de test pasa a ser viewer del proyecto ajeno."""
    from app.crud.project_crud import ProjectCRUD

    ProjectCRUD.add_project_member_orm(
        db_session, foreign["project_id"], str(test_user["id"]), role="viewer"
    )
    return foreign


# ============================================================================
# Sin acceso al proyecto: todo responde 404 o filtra los datos ajenos
# ============================================================================


@pytest.mark.integration
class TestLocksWithoutAccess:
    def test_cannot_list_locks(self, authenticated_client, foreign):
        r = authenticated_client.get(f"/api/locks/projects/{foreign['project_id']}")
        assert r.status_code == 404

    def test_cannot_see_lock_status(self, authenticated_client, foreign):
        r = authenticated_client.get(f"/api/locks/{foreign['entity_id']}/table/status")
        assert r.status_code == 404
        assert "username" not in r.text

    def test_cannot_acquire_lock(self, authenticated_client, foreign):
        r = authenticated_client.post(
            "/api/locks/acquire",
            json={
                "entity_id": str(uuid.uuid4()),
                "entity_type": "table",
                "project_id": foreign["project_id"],
            },
        )
        assert r.status_code == 404

    def test_cannot_force_unlock(self, authenticated_client, foreign, db_session):
        from app.crud import locks_crud

        r = authenticated_client.post(
            "/api/locks/force-unlock",
            json={
                "entity_id": foreign["entity_id"],
                "entity_type": "table",
                "project_id": foreign["project_id"],
            },
        )
        assert r.status_code == 404
        assert locks_crud.get_lock_status_orm(db_session, foreign["entity_id"], "table")

    def test_cannot_force_unlock_through_own_project(
        self, authenticated_client, foreign, test_project, db_session
    ):
        """Ser owner de OTRO proyecto no permite desbloquear locks de este"""
        from app.crud import locks_crud

        r = authenticated_client.post(
            "/api/locks/force-unlock",
            json={
                "entity_id": foreign["entity_id"],
                "entity_type": "table",
                "project_id": str(test_project["id"]),
            },
        )
        assert r.status_code == 404
        assert locks_crud.get_lock_status_orm(db_session, foreign["entity_id"], "table")

    def test_cannot_renew_foreign_lock(self, authenticated_client, foreign):
        r = authenticated_client.post(f"/api/locks/{foreign['lock_id']}/renew", json={})
        assert r.status_code == 400


@pytest.mark.integration
class TestVersionsWithoutAccess:
    def test_cannot_read_version(self, authenticated_client, foreign):
        r = authenticated_client.get(f"/api/versions/{foreign['version_id']}")
        assert r.status_code == 404
        assert "secret_salaries" not in r.text

    def test_entity_history_hides_foreign_versions(self, authenticated_client, foreign):
        r = authenticated_client.get(f"/api/versions/entity/{foreign['entity_id']}")
        assert r.status_code == 200
        assert r.json()["data"]["versions"] == []

    def test_cannot_compare_versions(self, authenticated_client, foreign):
        r = authenticated_client.get(
            "/api/versions/compare",
            params={"version_a_id": foreign["version_id"], "version_b_id": foreign["version_id"]},
        )
        assert r.status_code == 404

    def test_cannot_restore_version(self, authenticated_client, foreign):
        r = authenticated_client.post(
            f"/api/versions/{foreign['version_id']}/restore", json={"create_backup": False}
        )
        assert r.status_code == 404

    def test_cannot_list_project_versions_or_tags(self, authenticated_client, foreign):
        pid = foreign["project_id"]
        assert authenticated_client.get(f"/api/versions/projects/{pid}").status_code == 404
        assert authenticated_client.get(f"/api/versions/projects/{pid}/tags").status_code == 404

    def test_cannot_create_version(self, authenticated_client, foreign):
        r = authenticated_client.post(
            "/api/versions",
            json={
                "entity_id": foreign["entity_id"],
                "entity_type": "table",
                "project_id": foreign["project_id"],
                "change_type": "update",
                "snapshot": {"name": "hacked"},
            },
        )
        assert r.status_code == 404

    def test_cannot_create_or_delete_tag(self, authenticated_client, foreign):
        r = authenticated_client.post(
            "/api/versions/tags",
            json={
                "version_id": foreign["version_id"],
                "project_id": foreign["project_id"],
                "name": "evil",
            },
        )
        assert r.status_code == 404
        assert (
            authenticated_client.delete(f"/api/versions/tags/{foreign['tag_id']}").status_code
            == 404
        )


@pytest.mark.integration
class TestActivityWithoutAccess:
    def test_cannot_read_project_activity_or_stats(self, authenticated_client, foreign):
        pid = foreign["project_id"]
        assert authenticated_client.get(f"/api/activity/projects/{pid}").status_code == 404
        assert authenticated_client.get(f"/api/activity/projects/{pid}/stats").status_code == 404

    def test_entity_activity_hides_foreign_projects(self, authenticated_client, foreign):
        r = authenticated_client.get(
            f"/api/activity/entity/{foreign['entity_id']}", params={"entity_type": "table"}
        )
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_user_activity_hides_foreign_projects(self, authenticated_client, foreign):
        r = authenticated_client.get(f"/api/activity/users/{foreign['owner_id']}")
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_user_activity_filtered_by_foreign_project(self, authenticated_client, foreign):
        r = authenticated_client.get(
            f"/api/activity/users/{foreign['owner_id']}",
            params={"project_id": foreign["project_id"]},
        )
        assert r.status_code == 404


@pytest.mark.integration
class TestCommentsWithoutAccess:
    def test_entity_comments_hide_foreign_projects(self, authenticated_client, foreign):
        r = authenticated_client.get(
            "/api/comments", params={"entity_id": foreign["entity_id"], "entity_type": "table"}
        )
        assert r.status_code == 200
        assert r.json()["data"]["comments"] == []

    def test_cannot_comment(self, authenticated_client, foreign):
        r = authenticated_client.post(
            "/api/comments",
            json={
                "entity_id": foreign["entity_id"],
                "entity_type": "table",
                "project_id": foreign["project_id"],
                "content": "spam",
            },
        )
        assert r.status_code == 404

    def test_cannot_reply_to_foreign_comment_from_own_project(
        self, authenticated_client, foreign, test_project
    ):
        r = authenticated_client.post(
            "/api/comments",
            json={
                "entity_id": foreign["entity_id"],
                "entity_type": "table",
                "project_id": str(test_project["id"]),
                "content": "spam",
                "parent_id": foreign["comment_id"],
            },
        )
        assert r.status_code == 404

    def test_cannot_resolve_or_react(self, authenticated_client, foreign):
        cid = foreign["comment_id"]
        r = authenticated_client.patch(
            f"/api/comments/{cid}/resolve",
            json={"resolved": True, "project_id": foreign["project_id"]},
        )
        assert r.status_code == 404
        r = authenticated_client.post(f"/api/comments/{cid}/reactions", json={"emoji": "👍"})
        assert r.status_code == 404
        r = authenticated_client.delete(f"/api/comments/{cid}/reactions", params={"emoji": "👍"})
        assert r.status_code == 404

    def test_cannot_edit_or_delete(self, authenticated_client, foreign):
        cid = foreign["comment_id"]
        assert (
            authenticated_client.put(f"/api/comments/{cid}", json={"content": "x"}).status_code
            == 404
        )
        assert authenticated_client.delete(f"/api/comments/{cid}").status_code == 404

    def test_cannot_read_unread_count(self, authenticated_client, foreign):
        r = authenticated_client.get(f"/api/comments/unread/{foreign['project_id']}")
        assert r.status_code == 404


@pytest.mark.integration
def test_invalid_project_id_is_404(authenticated_client):
    assert authenticated_client.get("/api/locks/projects/not-a-uuid").status_code == 404
    assert authenticated_client.get("/api/versions/not-a-uuid").status_code == 404


# ============================================================================
# Viewer del proyecto: lee, pero no cambia
# ============================================================================


@pytest.mark.integration
class TestViewerRole:
    def test_viewer_can_read(self, authenticated_client, as_viewer):
        pid = as_viewer["project_id"]
        assert authenticated_client.get(f"/api/locks/projects/{pid}").status_code == 200
        assert (
            authenticated_client.get(f"/api/versions/{as_viewer['version_id']}").status_code == 200
        )
        assert authenticated_client.get(f"/api/activity/projects/{pid}").status_code == 200
        r = authenticated_client.get(
            "/api/comments", params={"entity_id": as_viewer["entity_id"], "entity_type": "table"}
        )
        assert r.status_code == 200
        assert len(r.json()["data"]["comments"]) == 1

    def test_viewer_cannot_force_unlock(self, authenticated_client, as_viewer):
        r = authenticated_client.post(
            "/api/locks/force-unlock",
            json={
                "entity_id": as_viewer["entity_id"],
                "entity_type": "table",
                "project_id": as_viewer["project_id"],
            },
        )
        assert r.status_code == 403

    def test_viewer_cannot_restore_or_tag(self, authenticated_client, as_viewer):
        r = authenticated_client.post(
            f"/api/versions/{as_viewer['version_id']}/restore", json={"create_backup": False}
        )
        assert r.status_code == 403
        r = authenticated_client.post(
            "/api/versions/tags",
            json={
                "version_id": as_viewer["version_id"],
                "project_id": as_viewer["project_id"],
                "name": "viewer-tag",
            },
        )
        assert r.status_code == 403

    def test_viewer_cannot_delete_tag_of_others(self, authenticated_client, as_viewer):
        r = authenticated_client.delete(f"/api/versions/tags/{as_viewer['tag_id']}")
        assert r.status_code == 403

    def test_viewer_cannot_acquire_lock(self, authenticated_client, as_viewer):
        r = authenticated_client.post(
            "/api/locks/acquire",
            json={
                "entity_id": str(uuid.uuid4()),
                "entity_type": "table",
                "project_id": as_viewer["project_id"],
            },
        )
        assert r.status_code == 403


# ============================================================================
# Owner del proyecto: sigue pudiendo hacerlo todo (el ciclo de locks está en test_locks_api.py)
# ============================================================================


@pytest.mark.integration
class TestOwnerKeepsAccess:
    def test_owner_comments_and_tags(self, authenticated_client, test_project, test_user):
        pid, entity_id = str(test_project["id"]), str(uuid.uuid4())

        r = authenticated_client.post(
            "/api/comments",
            json={
                "entity_id": entity_id,
                "entity_type": "table",
                "project_id": pid,
                "content": "hi",
            },
        )
        assert r.status_code == 200
        cid = r.json()["data"]["comment"]["id"]
        r = authenticated_client.patch(
            f"/api/comments/{cid}/resolve", json={"resolved": True, "project_id": pid}
        )
        assert r.status_code == 200

        r = authenticated_client.post(
            "/api/versions",
            json={
                "entity_id": entity_id,
                "entity_type": "table",
                "project_id": pid,
                "change_type": "create",
                "snapshot": {"name": "t"},
            },
        )
        assert r.status_code == 200
        version_id = r.json()["data"]["version"]["id"]

        r = authenticated_client.get(
            "/api/versions/compare", params={"version_a_id": version_id, "version_b_id": version_id}
        )
        assert r.status_code == 200

        r = authenticated_client.post(
            "/api/versions/tags",
            json={"version_id": version_id, "project_id": pid, "name": "release"},
        )
        assert r.status_code == 200
        tag_id = r.json()["data"]["tag"]["id"]
        assert authenticated_client.delete(f"/api/versions/tags/{tag_id}").status_code == 200
