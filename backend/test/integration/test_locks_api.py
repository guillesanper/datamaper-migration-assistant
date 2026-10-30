"""
Ciclo de vida de un lock por la API: adquirir, consultar, renovar, liberar y forzar.

acquire, release y force-unlock son endpoints síncronos (corren en el threadpool) y
lanzaban el broadcast con asyncio.create_task, que sin event loop fallaba: la operación
se hacía en BD pero la respuesta era un 500.
"""

import uuid

import pytest


@pytest.fixture
def lock_body(test_project):
    return {
        "entity_id": str(uuid.uuid4()),
        "entity_type": "table",
        "project_id": test_project["id"],
    }


@pytest.mark.integration
def test_acquire_status_renew_release(authenticated_client, lock_body):
    r = authenticated_client.post("/api/locks/acquire", json=lock_body)
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    lock_id = r.json()["lock"]["id"]

    r = authenticated_client.get(f"/api/locks/{lock_body['entity_id']}/table/status")
    assert r.status_code == 200
    assert r.json()["is_locked_by_me"] is True

    assert authenticated_client.post(f"/api/locks/{lock_id}/renew", json={}).status_code == 200

    r = authenticated_client.post("/api/locks/release", json=lock_body)
    assert r.status_code == 200, r.text
    assert r.json() == {"released": True}

    r = authenticated_client.get(f"/api/locks/{lock_body['entity_id']}/table/status")
    assert r.json()["is_locked"] is False


@pytest.mark.integration
def test_force_unlock(authenticated_client, lock_body):
    assert authenticated_client.post("/api/locks/acquire", json=lock_body).status_code == 200

    r = authenticated_client.post("/api/locks/force-unlock", json=lock_body)
    assert r.status_code == 200, r.text
    assert r.json() == {"unlocked": True}


@pytest.mark.integration
def test_active_locks_for_project(authenticated_client, lock_body):
    assert authenticated_client.post("/api/locks/acquire", json=lock_body).status_code == 200

    r = authenticated_client.get(f"/api/locks/projects/{lock_body['project_id']}")
    assert r.status_code == 200
    assert [lock["entity_id"] for lock in r.json()] == [lock_body["entity_id"]]
