"""
Los 500 por excepciones inesperadas no devuelven el texto de la excepción al cliente.

Antes muchos endpoints respondían detail=f"...: {str(e)}", que podía exponer SQL, rutas
o mensajes del driver. El detalle se queda en el log del servidor.
"""

import logging

import pytest

LEAK = "relation users_secret does not exist at /srv/app/db.py"


def _boom(*args, **kwargs):
    raise RuntimeError(LEAK)


@pytest.mark.integration
def test_activity_500_hides_exception(authenticated_client, test_project, monkeypatch, caplog):
    from app.services import activity_service

    monkeypatch.setattr(activity_service, "get_project_activity", _boom)

    with caplog.at_level(logging.ERROR):
        r = authenticated_client.get(f"/api/activity/projects/{test_project['id']}")

    assert r.status_code == 500
    assert r.json()["detail"] == "Error fetching activity"
    assert LEAK not in r.text
    # El detalle sigue en el log del servidor
    assert LEAK in caplog.text


@pytest.mark.integration
def test_locks_500_hides_exception(authenticated_client, test_project, monkeypatch):
    from app.services import locking_service

    monkeypatch.setattr(locking_service, "get_active_locks", _boom)

    r = authenticated_client.get(f"/api/locks/projects/{test_project['id']}")

    assert r.status_code == 500
    assert LEAK not in r.text


@pytest.mark.integration
def test_versions_500_hides_exception(authenticated_client, test_project, monkeypatch):
    from app.services import version_control_service

    monkeypatch.setattr(version_control_service, "get_project_versions", _boom)

    r = authenticated_client.get(f"/api/versions/projects/{test_project['id']}")

    assert r.status_code == 500
    assert LEAK not in r.text


@pytest.mark.integration
def test_comments_500_hides_exception(authenticated_client, test_project, monkeypatch):
    from app.services import comments_service

    monkeypatch.setattr(comments_service, "get_unread_count", _boom)

    r = authenticated_client.get(f"/api/comments/unread/{test_project['id']}")

    assert r.status_code == 500
    assert LEAK not in r.text


@pytest.mark.integration
def test_migration_500_hides_exception(authenticated_client, test_project, monkeypatch):
    from app.routers import migration

    monkeypatch.setattr(migration.migration_script_crud, "get_recent_executions_for_user", _boom)

    r = authenticated_client.get("/api/migrations/recent")

    assert r.status_code == 500
    assert LEAK not in r.text
