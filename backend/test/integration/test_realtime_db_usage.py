"""
El WebSocket de un proyecto no debe retener una conexión del pool de BD mientras está
abierto: con Depends(get_db_session) cada pestaña abierta ocupaba una (pool máx. 30) y
unas decenas de pestañas dejaban la app sin conexiones.
"""

from contextlib import ExitStack

from app.database import session as session_module


def test_open_websockets_do_not_hold_db_connections(authenticated_client, test_project):
    project_id = str(test_project["id"])
    pool = session_module.engine.pool
    baseline = pool.checkedout()

    with ExitStack() as stack:
        sockets = [
            stack.enter_context(
                authenticated_client.websocket_connect(f"/ws/projects/{project_id}")
            )
            for _ in range(3)
        ]
        for ws in sockets:
            assert ws.receive_json()["type"] == "hello"

        assert pool.checkedout() <= baseline


def test_unauthenticated_websocket_is_rejected(client, test_project):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/projects/{test_project['id']}") as ws:
            ws.receive_json()

    assert exc.value.code == 1008
