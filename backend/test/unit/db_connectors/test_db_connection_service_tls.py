"""
Estado TLS de las sesiones de conexión (DBConnectionService + router).

- La sesión recuerda si se verifica el certificado (tls_verified) y la API lo devuelve.
- El flag en claro y el blob cifrado deben coincidir: el blob manda.
- Las sesiones creadas antes de existir el flag se invalidan en vez de heredar un estado
  inseguro: el usuario ve "reconecta".
- Un fallo de verificación TLS se informa como error_type="tls" con un mensaje saneado, sin
  el texto crudo del driver (puede incluir rutas temporales y detalles de red).
"""

import logging
from unittest.mock import MagicMock, patch

import fakeredis
import pytest
from fastapi import HTTPException

from app.models.db_connection import DBConnectionConfig
from app.routers.db_connections import get_user_session, list_sessions, refresh_session
from app.services.db_connection_service import (
    DBConnectionService,
    DBConnectionServiceError,
    SessionExpiredError,
    SessionRequiresReconnectError,
)
from app.utils.db_adapters import DBConnectionError, DBTLSError

USER = "user-1"
HOST = "db.example.com"
DRIVER_DETAIL = 'root certificate file "/tmp/datamap-ca-secret.pem" does not exist (10.0.0.9)'


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture
def service(redis_client):
    return DBConnectionService(
        redis_client, "ZGF0YW1hcC10ZXN0LW1hc3Rlci1rZXktMzItYnl0ZXM="
    )  # base64 de 32 bytes


def _config(**extra) -> DBConnectionConfig:
    return DBConnectionConfig(
        dialect="postgresql",
        host=HOST,
        port=5432,
        database="app",
        user="u",
        password="s3cret-pass",
        **extra,
    )


def _unverified() -> DBConnectionConfig:
    return _config(tls_verify=False, confirm_hostname=HOST)


def _create(service, config=None):
    return service.create_session(USER, config or _config(), test_connection=False)


class TestSesionVerificada:
    def test_la_respuesta_indica_que_se_verifica(self, service):
        assert _create(service).tls_verified is True

    def test_el_flag_se_guarda_en_claro_para_poder_listar(self, service, redis_client):
        response = _create(service)

        key = f"db_connection_session:{USER}:{response.session_id}"
        assert redis_client.hget(key, "tls_verified") == b"1"

    def test_get_session_y_list_user_sessions_lo_exponen(self, service):
        response = _create(service)

        assert service.get_session(USER, response.session_id).tls_verified is True
        assert [s.tls_verified for s in service.list_user_sessions(USER)] == [True]

    def test_la_politica_sobrevive_al_ciclo_de_cifrado(self, service):
        response = _create(service)

        session = service.get_session(USER, response.session_id)

        assert service.get_decrypted_config(session).tls_verify is True


class TestSesionSinVerificar:
    def test_la_respuesta_la_marca_como_no_verificada(self, service):
        assert _create(service, _unverified()).tls_verified is False

    def test_el_flag_en_claro_es_cero(self, service, redis_client):
        response = _create(service, _unverified())

        key = f"db_connection_session:{USER}:{response.session_id}"
        assert redis_client.hget(key, "tls_verified") == b"0"

    def test_el_marcado_persiste_mientras_dura_la_sesion(self, service):
        response = _create(service, _unverified())

        service.refresh_session(USER, response.session_id, ttl_hours=5)

        assert service.get_session(USER, response.session_id).tls_verified is False
        assert [s.tls_verified for s in service.list_user_sessions(USER)] == [False]

    def test_la_confirmacion_viaja_cifrada_y_se_rehidrata(self, service):
        response = _create(service, _unverified())
        session = service.get_session(USER, response.session_id)

        config = service.get_decrypted_config(session)

        assert config.tls_verify is False
        assert config.confirm_hostname == HOST

    def test_se_registra_un_aviso_sin_credenciales(self, service, caplog):
        with caplog.at_level(logging.WARNING, logger="app.services.db_connection_service"):
            _create(service, _unverified())

        avisos = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("TLS verification disabled" in a and HOST in a and USER in a for a in avisos)
        assert not any("s3cret-pass" in a for a in avisos)

    def test_una_sesion_verificada_no_genera_aviso(self, service, caplog):
        with caplog.at_level(logging.WARNING, logger="app.services.db_connection_service"):
            _create(service)

        assert not [r for r in caplog.records if "TLS verification disabled" in r.getMessage()]

    def test_el_flag_en_claro_no_puede_ocultar_un_opt_out(self, service, redis_client):
        """Si alguien edita el hash para aparentar verificación, el blob cifrado manda."""
        response = _create(service, _unverified())
        key = f"db_connection_session:{USER}:{response.session_id}"
        redis_client.hset(key, "tls_verified", "1")

        session = service.get_session(USER, response.session_id)

        with pytest.raises(DBConnectionServiceError, match="TLS"):
            service.get_decrypted_config(session)

    def test_el_flag_en_claro_no_puede_aparentar_un_opt_out(self, service, redis_client):
        response = _create(service)
        key = f"db_connection_session:{USER}:{response.session_id}"
        redis_client.hset(key, "tls_verified", "0")

        session = service.get_session(USER, response.session_id)

        with pytest.raises(DBConnectionServiceError, match="TLS"):
            service.get_decrypted_config(session)

    @pytest.mark.parametrize("valor", ["", "true", "2", "yes"])
    def test_un_flag_ilegible_se_trata_como_sesion_corrupta(self, service, redis_client, valor):
        response = _create(service)
        key = f"db_connection_session:{USER}:{response.session_id}"
        redis_client.hset(key, "tls_verified", valor)

        with pytest.raises(DBConnectionServiceError):
            service.get_session(USER, response.session_id)


class TestSesionesAntiguas:
    @staticmethod
    def _crear_antigua(service, redis_client):
        response = _create(service)
        key = f"db_connection_session:{USER}:{response.session_id}"
        redis_client.hdel(key, "tls_verified")  # así eran antes de existir el flag
        return response.session_id, key

    def test_get_session_las_invalida(self, service, redis_client):
        session_id, key = self._crear_antigua(service, redis_client)

        with pytest.raises(SessionRequiresReconnectError):
            service.get_session(USER, session_id)

        assert not redis_client.exists(key)

    def test_siguen_siendo_un_caso_de_sesion_expirada(self, service, redis_client):
        """Los llamadores que ya capturan SessionExpiredError las tratan sin cambios."""
        session_id, _ = self._crear_antigua(service, redis_client)

        with pytest.raises(SessionExpiredError):
            service.get_session(USER, session_id)

    def test_list_user_sessions_las_descarta_y_las_borra(self, service, redis_client):
        _, antigua = self._crear_antigua(service, redis_client)
        vigente = _create(service)

        sesiones = service.list_user_sessions(USER)

        assert [s.session_id for s in sesiones] == [vigente.session_id]
        assert not redis_client.exists(antigua)

    def test_get_user_session_responde_410_con_un_mensaje_claro(self, service, redis_client):
        session_id, _ = self._crear_antigua(service, redis_client)

        with pytest.raises(HTTPException) as excinfo:
            get_user_session(session_id, service, {"id": USER})

        assert excinfo.value.status_code == 410
        assert "reconnect" in excinfo.value.detail.lower()


class TestRouter:
    def test_list_sessions_devuelve_tls_verified(self, service):
        _create(service)
        _create(service, _unverified())

        respuesta = list_sessions(service=service, current_user={"id": USER})

        assert sorted(s.tls_verified for s in respuesta) == [False, True]

    def test_refresh_session_conserva_tls_verified(self, service):
        creada = _create(service, _unverified())

        respuesta = refresh_session(
            creada.session_id, 4, service=service, current_user={"id": USER}
        )

        assert respuesta.tls_verified is False


class TestResultadoDelTest:
    @staticmethod
    def _con_adaptador(service, config, **adapter_kwargs):
        adapter = MagicMock()
        adapter.test_connection.configure_mock(**adapter_kwargs)
        with patch.object(DBConnectionService, "_get_adapter", return_value=adapter):
            return service.test_connection(config)

    def test_exito_refleja_la_politica_verificada(self, service):
        resultado = self._con_adaptador(service, _config(), return_value=True)

        assert (resultado.success, resultado.tls_verified) == (True, True)

    def test_exito_refleja_el_opt_out(self, service):
        resultado = self._con_adaptador(service, _unverified(), return_value=True)

        assert (resultado.success, resultado.tls_verified) == (True, False)

    def test_un_fallo_tls_es_error_type_tls(self, service):
        resultado = self._con_adaptador(service, _config(), side_effect=DBTLSError(DRIVER_DETAIL))

        assert resultado.success is False
        assert resultado.error_type == "tls"
        assert resultado.tls_verified is True

    def test_el_mensaje_tls_no_filtra_el_texto_del_driver(self, service):
        resultado = self._con_adaptador(service, _config(), side_effect=DBTLSError(DRIVER_DETAIL))

        assert "datamap-ca-secret" not in resultado.error_message
        assert "10.0.0.9" not in resultado.error_message
        assert "certificate" in resultado.error_message.lower()

    def test_un_fallo_de_red_sigue_siendo_connection(self, service):
        resultado = self._con_adaptador(
            service, _config(), side_effect=DBConnectionError("Connection refused")
        )

        assert resultado.error_type == "connection"

    def test_el_mensaje_tls_conserva_el_prefijo_que_reconoce_el_frontend(self, service):
        """DatabaseConnectionModal.tsx detecta este prefijo en el detail de un 400."""
        resultado = self._con_adaptador(service, _config(), side_effect=DBTLSError(DRIVER_DETAIL))

        assert resultado.error_message.startswith("TLS verification failed")

    def test_create_session_propaga_el_mensaje_saneado(self, service):
        adapter = MagicMock()
        adapter.test_connection.side_effect = DBTLSError(DRIVER_DETAIL)

        with patch.object(DBConnectionService, "_get_adapter", return_value=adapter):
            with pytest.raises(DBConnectionServiceError) as excinfo:
                service.create_session(USER, _config(), test_connection=True)

        assert "datamap-ca-secret" not in str(excinfo.value)
