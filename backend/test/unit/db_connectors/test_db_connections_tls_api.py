"""
Contrato HTTP de TLS en /api/db-connections (sin BD ni app completa).

Se monta solo el router sobre un Redis en memoria y se sustituye la autenticación, de modo
que se ejercitan la validación de FastAPI (422), la serialización de la respuesta y los
códigos de error reales. Demuestra que la confirmación de hostname se exige en el backend
aunque el cliente no pase por la UI.
"""

from unittest.mock import MagicMock, patch

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.db_connections import get_db_connection_service, router
from app.routers.dependencies import CurrentUserORM
from app.services.db_connection_service import DBConnectionService
from app.utils.db_adapters import DBTLSError

USER = {"id": "user-1", "email": "u@example.com"}
HOST = "db.example.com"
BASE = "/api/db-connections"


def _config(**extra) -> dict:
    return {
        "dialect": "postgresql",
        "host": HOST,
        "port": 5432,
        "database": "app",
        "user": "u",
        "password": "s3cret-pass",
        **extra,
    }


def _walk(dependant):
    for dependency in dependant.dependencies:
        yield dependency
        yield from _walk(dependency)


@pytest.fixture
def service():
    return DBConnectionService(fakeredis.FakeRedis(), "test_master_key_12345")


@pytest.fixture
def client(service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_connection_service] = lambda: service
    # Cada Depends(CurrentUser()) es una instancia distinta: se sustituyen todas
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        for dependency in _walk(dependant):
            if isinstance(dependency.call, CurrentUserORM):
                app.dependency_overrides[dependency.call] = lambda: USER
    return TestClient(app)


@pytest.fixture
def adapter_ok():
    adapter = MagicMock()
    adapter.test_connection.return_value = True
    with patch.object(DBConnectionService, "_get_adapter", return_value=adapter):
        yield adapter


class TestConfirmacionDeHostnameEnElBackend:
    @pytest.mark.parametrize("path", ["/test", "/sessions"])
    def test_opt_out_sin_confirmacion_es_422(self, client, adapter_ok, path):
        body = _config(tls_verify=False)
        if path == "/sessions":
            body = {"connection": body, "test_connection": False}

        response = client.post(BASE + path, json=body)

        assert response.status_code == 422
        assert "confirm_hostname" in response.text
        adapter_ok.test_connection.assert_not_called()

    @pytest.mark.parametrize("path", ["/test", "/sessions"])
    def test_opt_out_con_hostname_ajeno_es_422(self, client, adapter_ok, path):
        body = _config(tls_verify=False, confirm_hostname="otro.example.com")
        if path == "/sessions":
            body = {"connection": body, "test_connection": False}

        assert client.post(BASE + path, json=body).status_code == 422

    def test_tls_verify_como_texto_es_422(self, client, adapter_ok):
        """ "false" como cadena no desactiva la verificación por coerción."""
        response = client.post(BASE + "/test", json=_config(tls_verify="false"))

        assert response.status_code == 422

    def test_opt_out_confirmado_en_test_conecta_y_lo_indica(self, client, adapter_ok):
        response = client.post(
            BASE + "/test", json=_config(tls_verify=False, confirm_hostname=HOST.upper())
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["tls_verified"] is False

    def test_por_defecto_se_verifica(self, client, adapter_ok):
        response = client.post(BASE + "/test", json=_config())

        assert response.json()["tls_verified"] is True


class TestSesionesEnLaApi:
    @staticmethod
    def _crear(client, **extra):
        return client.post(
            BASE + "/sessions",
            json={"connection": _config(**extra), "test_connection": False},
        )

    def test_crear_sin_verificar_devuelve_tls_verified_false(self, client):
        response = self._crear(client, tls_verify=False, confirm_hostname=HOST)

        assert response.status_code == 201
        assert response.json()["tls_verified"] is False

    def test_crear_verificada_devuelve_tls_verified_true(self, client):
        assert self._crear(client).json()["tls_verified"] is True

    def test_el_listado_conserva_la_marca(self, client):
        self._crear(client)
        self._crear(client, tls_verify=False, confirm_hostname=HOST)

        listado = client.get(BASE + "/sessions").json()

        assert sorted(item["tls_verified"] for item in listado) == [False, True]

    def test_refresh_conserva_la_marca(self, client):
        creada = self._crear(client, tls_verify=False, confirm_hostname=HOST).json()

        respuesta = client.post(f"{BASE}/sessions/{creada['session_id']}/refresh?ttl_hours=2")

        assert respuesta.status_code == 200
        assert respuesta.json()["tls_verified"] is False

    def test_las_credenciales_y_la_ca_nunca_salen_en_la_respuesta(self, client):
        cuerpo = self._crear(client, tls_verify=False, confirm_hostname=HOST).text

        assert "s3cret-pass" not in cuerpo
        assert "confirm_hostname" not in cuerpo
        assert "tls_ca_pem" not in cuerpo

    def test_sesion_antigua_responde_410_y_se_borra(self, client, service):
        creada = self._crear(client).json()
        key = f"db_connection_session:{USER['id']}:{creada['session_id']}"
        service.redis.hdel(key, "tls_verified")

        respuesta = client.get(f"{BASE}/sessions/{creada['session_id']}/schemas")

        assert respuesta.status_code == 410
        assert "reconnect" in respuesta.json()["detail"].lower()
        assert not service.redis.exists(key)


class TestRechazosDeLaConfiguracion:
    def test_sqlserver_con_ca_propia_es_422(self, client, ca_pem):
        response = client.post(
            BASE + "/test", json=_config(dialect="sqlserver", port=1433, tls_ca_pem=ca_pem)
        )

        assert response.status_code == 422
        assert "SQL Server" in response.text

    def test_ca_con_clave_privada_es_422(self, client, ca_key_pem):
        response = client.post(BASE + "/test", json=_config(tls_ca_pem=ca_key_pem))

        assert response.status_code == 422

    @pytest.mark.parametrize("host", ["x;Encrypt=no", "db{evil}", "(DESCRIPTION=x)"])
    def test_host_con_caracteres_de_control_es_422(self, client, host):
        assert client.post(BASE + "/test", json=_config(host=host)).status_code == 422


class TestErroresTLSEnLaApi:
    def test_fallo_tls_se_devuelve_saneado(self, client):
        adapter = MagicMock()
        adapter.test_connection.side_effect = DBTLSError('root certificate file "/tmp/x.pem"')

        with patch.object(DBConnectionService, "_get_adapter", return_value=adapter):
            response = client.post(BASE + "/test", json=_config())

        cuerpo = response.json()
        assert cuerpo["success"] is False
        assert cuerpo["error_type"] == "tls"
        assert "/tmp/x.pem" not in cuerpo["error_message"]
