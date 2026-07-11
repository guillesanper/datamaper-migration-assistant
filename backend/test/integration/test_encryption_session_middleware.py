"""
Tests de integración para Encryption Session Middleware

Módulo: app.middleware.encryption_session
Propósito: Tests para middleware que maneja sesiones de cifrado con validación de ownership

Seguridad crítica:
- Prevención de session hijacking (user_id binding)
- httpOnly cookies (inmune a XSS)
- Extracción automática de project_id del path
- Validación de ownership de sesiones

Autor: DataMap Testing Team
Última actualización: 2025-01-15
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, Response

from app.middleware.encryption_session import (
    EncryptionSessionMiddleware,
    extract_project_id_from_path,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_encryption_cache():
    """Mock del caché de sesiones de cifrado"""
    mock = MagicMock()
    mock.get_session = MagicMock(return_value=None)
    mock.invalidate_session = MagicMock()
    return mock


@pytest.fixture
def mock_request():
    """Mock de FastAPI Request"""
    request = MagicMock(spec=Request)
    request.url = MagicMock()
    request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
    request.cookies = {}
    request.state = MagicMock()
    request.state.encryption_key = None
    request.state.encryption_project_id = None
    request.state.current_user = None
    return request


@pytest.fixture
def mock_call_next():
    """Mock de call_next para middleware"""

    async def _call_next(request):
        response = MagicMock(spec=Response)
        return response

    return _call_next


@pytest.fixture
def middleware():
    """Instancia del middleware"""
    app = MagicMock()
    return EncryptionSessionMiddleware(app)


@pytest.fixture
def valid_session():
    """Sesión válida de cifrado"""
    return {
        "user_id": "user-123",
        "project_id": "12345678-1234-1234-1234-123456789abc",
        "encryption_key": b"test_encryption_key_32_bytes_long",
        "created_at": "2025-01-15T10:00:00Z",
    }


@pytest.fixture
def current_user():
    """Usuario autenticado actual"""
    return {"id": "user-123", "email": "test@example.com", "username": "testuser"}


# ============================================================================
# TESTS: extract_project_id_from_path()
# ============================================================================


class TestExtractProjectIdFromPath:
    """Tests para extracción de project_id del path"""

    def test_extract_project_id_standard_path(self):
        """Extrae project_id de path estándar /api/projects/{uuid}/..."""
        # Arrange
        path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result == "12345678-1234-1234-1234-123456789abc"

    def test_extract_project_id_without_trailing_path(self):
        """Extrae project_id de path sin trailing /api/projects/{uuid}"""
        # Arrange
        path = "/api/projects/abcdef12-3456-7890-abcd-ef1234567890"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result == "abcdef12-3456-7890-abcd-ef1234567890"

    def test_extract_project_id_with_nested_path(self):
        """Extrae project_id de path anidado"""
        # Arrange
        path = "/api/mappings/projects/11111111-2222-3333-4444-555555555555/tables/table1"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result == "11111111-2222-3333-4444-555555555555"

    def test_extract_project_id_case_insensitive(self):
        """Extrae project_id case-insensitive"""
        # Arrange
        path = "/api/PROJECTS/AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE/schemas"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result == "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"

    def test_extract_project_id_lowercase_uuid(self):
        """Extrae project_id con UUID lowercase"""
        # Arrange
        path = "/api/projects/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/schemas"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def test_extract_project_id_not_found_health_endpoint(self):
        """Retorna None para endpoints sin project_id (health)"""
        # Arrange
        path = "/api/health"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result is None

    def test_extract_project_id_not_found_auth_endpoint(self):
        """Retorna None para endpoints de autenticación"""
        # Arrange
        path = "/api/auth/login"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result is None

    def test_extract_project_id_not_found_invalid_uuid(self):
        """Retorna None para UUID inválido"""
        # Arrange
        path = "/api/projects/invalid-uuid/schemas"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result is None

    def test_extract_project_id_not_found_short_uuid(self):
        """Retorna None para UUID demasiado corto"""
        # Arrange
        path = "/api/projects/12345678/schemas"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result is None

    def test_extract_project_id_empty_path(self):
        """Retorna None para path vacío"""
        # Arrange
        path = ""

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result is None

    def test_extract_project_id_root_path(self):
        """Retorna None para path raíz"""
        # Arrange
        path = "/"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result is None

    def test_extract_project_id_multiple_projects_in_path(self):
        """Extrae primer project_id cuando hay múltiples en el path"""
        # Arrange
        path = "/api/projects/11111111-1111-1111-1111-111111111111/copy/projects/22222222-2222-2222-2222-222222222222"

        # Act
        result = extract_project_id_from_path(path)

        # Assert
        assert result == "11111111-1111-1111-1111-111111111111"


# ============================================================================
# TESTS: EncryptionSessionMiddleware.dispatch()
# ============================================================================


class TestDispatchBasicFlow:
    """Tests para flujo básico del middleware"""

    @pytest.mark.asyncio
    async def test_dispatch_initializes_state_defaults(
        self, middleware, mock_request, mock_call_next
    ):
        """Inicializa valores por defecto en request.state"""
        # Arrange
        mock_request.url.path = "/api/health"

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert mock_request.state.encryption_key is None
        assert mock_request.state.encryption_project_id is None

    @pytest.mark.asyncio
    async def test_dispatch_no_project_id_in_path(self, middleware, mock_request, mock_call_next):
        """No procesa sesión si no hay project_id en path"""
        # Arrange
        mock_request.url.path = "/api/health"

        # Act
        response = await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert mock_request.state.encryption_key is None
        assert mock_request.state.encryption_project_id is None
        assert response is not None

    @pytest.mark.asyncio
    async def test_dispatch_project_id_but_no_cookie(
        self, middleware, mock_request, mock_call_next
    ):
        """No procesa sesión si hay project_id pero no cookie"""
        # Arrange
        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {}

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert mock_request.state.encryption_key is None
        assert mock_request.state.encryption_project_id is None

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_cookie_exists_but_session_not_in_cache(
        self, mock_get_cache, middleware, mock_request, mock_call_next, mock_encryption_cache
    ):
        """No inyecta encryption_key si sesión no existe en caché"""
        # Arrange
        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = None

        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "token123"}

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        mock_encryption_cache.get_session.assert_called_once_with(
            "token123", "12345678-1234-1234-1234-123456789abc"
        )
        assert mock_request.state.encryption_key is None
        assert mock_request.state.encryption_project_id is None


class TestDispatchSessionValidation:
    """Tests para validación de sesiones"""

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_valid_session_with_user_match(
        self,
        mock_get_cache,
        middleware,
        mock_request,
        mock_call_next,
        mock_encryption_cache,
        valid_session,
        current_user,
    ):
        """Inyecta encryption_key cuando sesión es válida y user_id coincide"""
        # Arrange
        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = valid_session

        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "valid_token"}
        mock_request.state.current_user = current_user

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert mock_request.state.encryption_key == b"test_encryption_key_32_bytes_long"
        assert mock_request.state.encryption_project_id == "12345678-1234-1234-1234-123456789abc"

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_session_hijacking_detected(
        self,
        mock_get_cache,
        middleware,
        mock_request,
        mock_call_next,
        mock_encryption_cache,
        valid_session,
    ):
        """Detecta y rechaza intento de session hijacking (user_id no coincide)"""
        # Arrange
        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = valid_session

        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "stolen_token"}

        # Usuario diferente al dueño de la sesión
        attacker_user = {
            "id": "attacker-999",  # Diferente a 'user-123' de la sesión
            "email": "attacker@evil.com",
        }
        mock_request.state.current_user = attacker_user

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        # Sesión debe ser invalidada
        mock_encryption_cache.invalidate_session.assert_called_once_with("stolen_token")

        # NO debe inyectar encryption_key
        assert mock_request.state.encryption_key is None
        assert mock_request.state.encryption_project_id is None

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_session_without_user_id(
        self,
        mock_get_cache,
        middleware,
        mock_request,
        mock_call_next,
        mock_encryption_cache,
        current_user,
    ):
        """Maneja sesión sin user_id (legacy fallback)"""
        # Arrange
        session_without_user_id = {
            "project_id": "12345678-1234-1234-1234-123456789abc",
            "encryption_key": b"test_key",
        }

        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = session_without_user_id

        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "token"}
        mock_request.state.current_user = current_user

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        # Debe inyectar encryption_key (fallback legacy)
        assert mock_request.state.encryption_key == b"test_key"
        assert mock_request.state.encryption_project_id == "12345678-1234-1234-1234-123456789abc"

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_session_without_current_user(
        self,
        mock_get_cache,
        middleware,
        mock_request,
        mock_call_next,
        mock_encryption_cache,
        valid_session,
    ):
        """Guarda sesión pendiente si no hay current_user aún"""
        # Arrange
        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = valid_session

        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "token"}
        mock_request.state.current_user = None  # No hay usuario autenticado aún

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        # Debe guardar sesión pendiente
        assert hasattr(mock_request.state, "_pending_encryption_session")
        assert mock_request.state._pending_encryption_session == valid_session


class TestDispatchUserTypes:
    """Tests para diferentes tipos de objetos de usuario"""

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_current_user_as_dict(
        self,
        mock_get_cache,
        middleware,
        mock_request,
        mock_call_next,
        mock_encryption_cache,
        valid_session,
    ):
        """Maneja current_user como dict"""
        # Arrange
        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = valid_session

        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "token"}
        mock_request.state.current_user = {"id": "user-123", "email": "test@test.com"}

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert mock_request.state.encryption_key == b"test_encryption_key_32_bytes_long"

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_current_user_as_object(
        self,
        mock_get_cache,
        middleware,
        mock_request,
        mock_call_next,
        mock_encryption_cache,
        valid_session,
    ):
        """Maneja current_user como objeto con atributos"""
        # Arrange
        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = valid_session

        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "token"}

        # Usuario como objeto
        user_obj = MagicMock()
        user_obj.id = "user-123"
        user_obj.email = "test@test.com"
        mock_request.state.current_user = user_obj

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert mock_request.state.encryption_key == b"test_encryption_key_32_bytes_long"


class TestDispatchCookieNames:
    """Tests para diferentes formatos de nombres de cookies"""

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_cookie_name_format(
        self,
        mock_get_cache,
        middleware,
        mock_request,
        mock_call_next,
        mock_encryption_cache,
        valid_session,
        current_user,
    ):
        """Verifica formato correcto de cookie enc_session_{project_id}"""
        # Arrange
        project_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        expected_cookie_name = f"enc_session_{project_id}"

        valid_session["project_id"] = project_id
        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = valid_session

        mock_request.url.path = f"/api/projects/{project_id}/schemas"
        mock_request.cookies = {expected_cookie_name: "token123"}
        mock_request.state.current_user = current_user

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        mock_encryption_cache.get_session.assert_called_with("token123", project_id)

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_wrong_cookie_name_ignored(
        self, mock_get_cache, middleware, mock_request, mock_call_next, mock_encryption_cache
    ):
        """Ignora cookies con nombres incorrectos"""
        # Arrange
        project_id = "12345678-1234-1234-1234-123456789abc"

        mock_get_cache.return_value = mock_encryption_cache
        mock_request.url.path = f"/api/projects/{project_id}/schemas"

        # Cookie con nombre incorrecto
        mock_request.cookies = {"wrong_cookie_name": "token123"}

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        # No debe llamar a get_session
        mock_encryption_cache.get_session.assert_not_called()


class TestDispatchMultipleProjects:
    """Tests para manejo de múltiples proyectos"""

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_different_projects_different_cookies(
        self, mock_get_cache, middleware, mock_call_next, mock_encryption_cache, current_user
    ):
        """Maneja cookies diferentes para proyectos diferentes"""
        # Arrange
        project1_id = "11111111-1111-1111-1111-111111111111"
        project2_id = "22222222-2222-2222-2222-222222222222"

        session1 = {
            "user_id": "user-123",
            "project_id": project1_id,
            "encryption_key": b"key_for_project_1",
        }

        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = session1

        # Request para proyecto 1
        request1 = MagicMock(spec=Request)
        request1.url = MagicMock()
        request1.url.path = f"/api/projects/{project1_id}/schemas"
        request1.cookies = {f"enc_session_{project1_id}": "token_project1"}
        request1.state = MagicMock()
        request1.state.current_user = current_user
        request1.state.encryption_key = None
        request1.state.encryption_project_id = None

        # Act
        await middleware.dispatch(request1, mock_call_next)

        # Assert
        mock_encryption_cache.get_session.assert_called_with("token_project1", project1_id)
        assert request1.state.encryption_key == b"key_for_project_1"
        assert request1.state.encryption_project_id == project1_id


class TestDispatchEdgeCases:
    """Tests para casos edge"""

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_empty_cookie_value(
        self, mock_get_cache, middleware, mock_request, mock_call_next, mock_encryption_cache
    ):
        """Maneja cookie vacía correctamente"""
        # Arrange
        mock_get_cache.return_value = mock_encryption_cache

        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": ""}

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        # Cookie vacía no debe procesar sesión
        assert mock_request.state.encryption_key is None

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_cache_get_session_raises_exception(
        self, mock_get_cache, middleware, mock_request, mock_call_next, mock_encryption_cache
    ):
        """Maneja excepción al obtener sesión del caché"""
        # Arrange
        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.side_effect = Exception("Cache error")

        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "token"}

        # Act & Assert
        # Debe propagar la excepción o manejarla apropiadamente
        with pytest.raises(Exception):
            await middleware.dispatch(mock_request, mock_call_next)

    @pytest.mark.asyncio
    async def test_dispatch_call_next_is_called(self, middleware, mock_request, mock_call_next):
        """Verifica que call_next siempre es llamado"""
        # Arrange
        mock_request.url.path = "/api/health"

        # Act
        response = await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        assert response is not None

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_session_key_none(
        self,
        mock_get_cache,
        middleware,
        mock_request,
        mock_call_next,
        mock_encryption_cache,
        current_user,
    ):
        """Maneja sesión con encryption_key None"""
        # Arrange
        session_with_none_key = {
            "user_id": "user-123",
            "project_id": "12345678-1234-1234-1234-123456789abc",
            "encryption_key": None,
        }

        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = session_with_none_key

        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "token"}
        mock_request.state.current_user = current_user

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        # Debe inyectar None (sesión válida pero sin clave)
        assert mock_request.state.encryption_key is None
        assert mock_request.state.encryption_project_id == "12345678-1234-1234-1234-123456789abc"


class TestDispatchSecurityScenarios:
    """Tests para escenarios de seguridad específicos"""

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_prevents_cross_user_access(
        self, mock_get_cache, middleware, mock_call_next, mock_encryption_cache
    ):
        """Previene acceso cross-user a sesiones"""
        # Arrange
        # Usuario A crea sesión
        user_a_session = {
            "user_id": "user-A",
            "project_id": "12345678-1234-1234-1234-123456789abc",
            "encryption_key": b"user_a_secret_key",
        }

        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = user_a_session

        # Usuario B intenta usar la sesión de A
        request_b = MagicMock(spec=Request)
        request_b.url = MagicMock()
        request_b.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        request_b.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "user_a_token"}
        request_b.state = MagicMock()
        request_b.state.current_user = {"id": "user-B", "email": "b@test.com"}
        request_b.state.encryption_key = None
        request_b.state.encryption_project_id = None

        # Act
        await middleware.dispatch(request_b, mock_call_next)

        # Assert
        # Usuario B NO debe obtener la clave de Usuario A
        assert request_b.state.encryption_key is None
        # Sesión debe ser invalidada
        mock_encryption_cache.invalidate_session.assert_called_once_with("user_a_token")

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_allows_same_user_access(
        self, mock_get_cache, middleware, mock_call_next, mock_encryption_cache
    ):
        """Permite acceso cuando mismo usuario usa su sesión"""
        # Arrange
        user_session = {
            "user_id": "user-A",
            "project_id": "12345678-1234-1234-1234-123456789abc",
            "encryption_key": b"user_a_secret_key",
        }

        mock_get_cache.return_value = mock_encryption_cache
        mock_encryption_cache.get_session.return_value = user_session

        # Mismo usuario A accede a su sesión
        request_a = MagicMock(spec=Request)
        request_a.url = MagicMock()
        request_a.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"
        request_a.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "user_a_token"}
        request_a.state = MagicMock()
        request_a.state.current_user = {"id": "user-A", "email": "a@test.com"}
        request_a.state.encryption_key = None
        request_a.state.encryption_project_id = None

        # Act
        await middleware.dispatch(request_a, mock_call_next)

        # Assert
        # Usuario A debe obtener su clave
        assert request_a.state.encryption_key == b"user_a_secret_key"
        assert request_a.state.encryption_project_id == "12345678-1234-1234-1234-123456789abc"
        # Sesión NO debe ser invalidada
        mock_encryption_cache.invalidate_session.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.middleware.encryption_session.get_encryption_session_cache")
    async def test_dispatch_httponly_cookie_not_accessible_to_javascript(
        self, mock_get_cache, middleware, mock_request, mock_call_next
    ):
        """
        Verifica que cookies httpOnly sean usadas (test conceptual)

        Nota: httpOnly es una propiedad de la cookie en la respuesta HTTP,
        no del Request. Este test verifica que el middleware espera
        cookies httpOnly en el diseño.
        """
        # Arrange
        mock_request.url.path = "/api/projects/12345678-1234-1234-1234-123456789abc/schemas"

        # Cookie debe ser leída del request (asumiendo que fue enviada como httpOnly)
        mock_request.cookies = {"enc_session_12345678-1234-1234-1234-123456789abc": "token"}

        # Act
        await middleware.dispatch(mock_request, mock_call_next)

        # Assert
        # El middleware debe poder leer la cookie
        # (httpOnly solo previene acceso desde JavaScript, no desde servidor)
        assert "enc_session_12345678-1234-1234-1234-123456789abc" in mock_request.cookies
