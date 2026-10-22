"""
Tests de integración para CSRF Protection Middleware

Módulo: app.middleware.csrf_protection
Propósito: Tests para middleware de protección CSRF

Seguridad crítica:
- Generación segura de tokens CSRF (CSPRNG)
- Validación por IP o session_id
- Protección de métodos POST/PUT/DELETE
- Limpieza automática de tokens expirados

Autor: DataMap Testing Team
Última actualización: 2025-01-15
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import Request
from fastapi.responses import Response

from app.middleware.csrf_protection import (
    CSRFProtection,
    csrf_middleware,
    csrf_protect,
    get_csrf_token_for_template,
    start_csrf_cleanup_task,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_request():
    """Mock de FastAPI Request"""
    request = MagicMock(spec=Request)
    request.url = MagicMock()
    request.url.path = "/api/projects/create"
    request.method = "POST"
    request.headers = {}
    request.cookies = {}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def mock_db():
    """Mock de conexión a base de datos"""
    mock = MagicMock()
    mock.cursor = MagicMock()
    mock.commit = MagicMock()
    mock.close = MagicMock()
    return mock


@pytest.fixture
def mock_cursor():
    """Mock de cursor de base de datos"""
    cursor = MagicMock()
    cursor.execute = MagicMock()
    cursor.fetchone = MagicMock()
    cursor.close = MagicMock()
    cursor.rowcount = 0
    return cursor


@pytest.fixture
def mock_security_settings():
    """Mock de security settings"""
    settings = MagicMock()
    settings.CSRF_TOKEN_EXPIRY = 3600
    settings.CSRF_PROTECTED_METHODS = ["POST", "PUT", "DELETE", "PATCH"]
    settings.is_csrf_protected_endpoint = MagicMock(return_value=True)
    return settings


@pytest.fixture
def mock_call_next():
    """Mock de call_next para middleware"""

    async def _call_next(request):
        return Response(status_code=200)

    return _call_next


@pytest.fixture
def valid_csrf_token():
    """Token CSRF válido de prueba"""
    return "csrf_test_token_abcdefghijklmnopqrstuvwxyz123456"


# ============================================================================
# TESTS: CSRFProtection.generate_csrf_token()
# ============================================================================


class TestGenerateCSRFToken:
    """Tests para generación de tokens CSRF"""

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_generate_csrf_token_returns_token(
        self, mock_security_utils, mock_get_db, mock_request, mock_db, mock_cursor
    ):
        """Retorna token CSRF al generar"""
        # Arrange
        mock_security_utils.generate_csrf_token.return_value = "test_token_123"
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed_ip_123"

        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Act
        token = await CSRFProtection.generate_csrf_token(mock_request)

        # Assert
        assert token == "test_token_123"

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_generate_csrf_token_stores_in_database(
        self, mock_security_utils, mock_get_db, mock_csrf_crud, mock_request, mock_db, mock_cursor
    ):
        """Almacena token en base de datos"""
        # Arrange
        mock_security_utils.generate_csrf_token.return_value = "token123"
        mock_security_utils.get_client_ip.return_value = "192.168.1.1"
        mock_security_utils.hash_ip_address.return_value = "hashed_ip"

        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.generate_token_orm.return_value = {"token": "token123"}

        # Act
        await CSRFProtection.generate_csrf_token(mock_request)

        # Assert
        mock_csrf_crud.generate_token_orm.assert_called_once()
        mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    @patch("app.middleware.csrf_protection.security_settings")
    async def test_generate_csrf_token_uses_expiry_from_settings(
        self,
        mock_settings,
        mock_security_utils,
        mock_get_db,
        mock_csrf_crud,
        mock_request,
        mock_db,
        mock_cursor,
    ):
        """Usa CSRF_TOKEN_EXPIRY de settings"""
        # Arrange
        mock_settings.CSRF_TOKEN_EXPIRY = 7200  # 2 horas
        mock_security_utils.generate_csrf_token.return_value = "token"
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed"

        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.generate_token_orm.return_value = {"token": "token"}

        # Act
        await CSRFProtection.generate_csrf_token(mock_request)

        # Assert - expires_in_minutes = 7200 // 60 = 120
        mock_csrf_crud.generate_token_orm.assert_called_once()
        _, call_kwargs = mock_csrf_crud.generate_token_orm.call_args
        assert call_kwargs["expires_in_minutes"] == 120

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_generate_csrf_token_hashes_ip_address(
        self, mock_security_utils, mock_get_db, mock_request, mock_db, mock_cursor
    ):
        """Hash de dirección IP antes de almacenar"""
        # Arrange
        mock_security_utils.generate_csrf_token.return_value = "token"
        mock_security_utils.get_client_ip.return_value = "203.0.113.42"
        mock_security_utils.hash_ip_address.return_value = "hashed_203_0_113_42"

        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        # Act
        await CSRFProtection.generate_csrf_token(mock_request)

        # Assert
        mock_security_utils.hash_ip_address.assert_called_once_with("203.0.113.42")

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_generate_csrf_token_with_session_cookie(
        self, mock_security_utils, mock_get_db, mock_csrf_crud, mock_request, mock_db, mock_cursor
    ):
        """Almacena session_id si existe cookie de sesión"""
        # Arrange
        mock_request.cookies = {"session": "session_token_abcdefghijklmnopqrstuvwxyz123456"}
        mock_security_utils.generate_csrf_token.return_value = "token"
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed"

        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.generate_token_orm.return_value = {"token": "token"}

        # Act
        await CSRFProtection.generate_csrf_token(mock_request)

        # Assert
        mock_csrf_crud.generate_token_orm.assert_called_once()
        _, call_kwargs = mock_csrf_crud.generate_token_orm.call_args
        assert call_kwargs["session_id"] == "session_token_abcdefghijklmnopqr"  # primeros 32 chars

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_generate_csrf_token_without_session_cookie(
        self, mock_security_utils, mock_get_db, mock_csrf_crud, mock_request, mock_db, mock_cursor
    ):
        """Genera token sin session_id si no hay cookie"""
        # Arrange
        mock_request.cookies = {}
        mock_security_utils.generate_csrf_token.return_value = "token"
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed"

        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.generate_token_orm.return_value = {"token": "token"}

        # Act
        await CSRFProtection.generate_csrf_token(mock_request)

        # Assert
        mock_csrf_crud.generate_token_orm.assert_called_once()
        _, call_kwargs = mock_csrf_crud.generate_token_orm.call_args
        assert call_kwargs["session_id"] == ""

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_generate_csrf_token_cleans_expired_tokens(
        self, mock_security_utils, mock_get_db, mock_csrf_crud, mock_request, mock_db, mock_cursor
    ):
        """Genera token delegando al CRUD ORM (limpieza de expirados es interna al ORM)"""
        # Arrange
        mock_security_utils.generate_csrf_token.return_value = "token"
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed"

        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.generate_token_orm.return_value = {"token": "token"}

        # Act
        await CSRFProtection.generate_csrf_token(mock_request)

        # Assert - generate_token_orm maneja internamente la creación
        mock_csrf_crud.generate_token_orm.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_generate_csrf_token_upsert_behavior(
        self, mock_security_utils, mock_get_db, mock_csrf_crud, mock_request, mock_db, mock_cursor
    ):
        """Delega al CRUD ORM para almacenar token (upsert manejado por ORM)"""
        # Arrange
        mock_security_utils.generate_csrf_token.return_value = "token"
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed"

        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.generate_token_orm.return_value = {"token": "token"}

        # Act
        await CSRFProtection.generate_csrf_token(mock_request)

        # Assert - generate_token_orm maneja el almacenamiento
        mock_csrf_crud.generate_token_orm.assert_called_once()
        _, call_kwargs = mock_csrf_crud.generate_token_orm.call_args
        assert call_kwargs["token"] == "token"
        assert call_kwargs["ip_address"] == "hashed"

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_generate_csrf_token_handles_database_error(
        self, mock_security_utils, mock_get_db, mock_request, mock_db, mock_cursor
    ):
        """Maneja error de base de datos gracefully"""
        # Arrange
        mock_security_utils.generate_csrf_token.return_value = "token"
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed"

        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("DB Error")

        # Act
        token = await CSRFProtection.generate_csrf_token(mock_request)

        # Assert
        # Debe retornar token aunque falle DB
        assert token == "token"


# ============================================================================
# TESTS: CSRFProtection.validate_csrf_token()
# ============================================================================


class TestValidateCSRFToken:
    """Tests para validación de tokens CSRF"""

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_validate_csrf_token_valid_token(
        self, mock_security_utils, mock_get_db, mock_csrf_crud, mock_request, mock_db, mock_cursor
    ):
        """Retorna True para token válido"""
        # Arrange
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed_ip"

        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.validate_token_orm.return_value = True

        # Act
        result = await CSRFProtection.validate_csrf_token(mock_request, "valid_token")

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_csrf_token_empty_token(self, mock_request):
        """Retorna False para token vacío"""
        # Arrange & Act
        result = await CSRFProtection.validate_csrf_token(mock_request, "")

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_csrf_token_none_token(self, mock_request):
        """Retorna False para token None"""
        # Arrange & Act
        result = await CSRFProtection.validate_csrf_token(mock_request, None)

        # Assert
        assert result is False

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_validate_csrf_token_not_found_in_db(
        self, mock_security_utils, mock_get_db, mock_request, mock_db, mock_cursor
    ):
        """Retorna False para token no encontrado en DB"""
        # Arrange
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed_ip"

        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = None  # Token no encontrado

        # Act
        result = await CSRFProtection.validate_csrf_token(mock_request, "nonexistent_token")

        # Assert
        assert result is False

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_validate_csrf_token_ip_match(
        self, mock_security_utils, mock_get_db, mock_csrf_crud, mock_request, mock_db, mock_cursor
    ):
        """Valida token cuando IP coincide"""
        # Arrange
        mock_security_utils.get_client_ip.return_value = "192.168.1.100"
        mock_security_utils.hash_ip_address.return_value = "hashed_192_168_1_100"

        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.validate_token_orm.return_value = True

        # Act
        result = await CSRFProtection.validate_csrf_token(mock_request, "token")

        # Assert
        assert result is True
        _, call_kwargs = mock_csrf_crud.validate_token_orm.call_args
        assert call_kwargs["ip_address"] == "hashed_192_168_1_100"

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_validate_csrf_token_session_match(
        self, mock_security_utils, mock_get_db, mock_csrf_crud, mock_request, mock_db, mock_cursor
    ):
        """Valida token cuando session_id coincide"""
        # Arrange
        mock_request.cookies = {"session": "session_abc123_matching_session"}

        mock_security_utils.get_client_ip.return_value = "192.168.1.100"
        mock_security_utils.hash_ip_address.return_value = "different_hashed_ip"

        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.validate_token_orm.return_value = True

        # Act
        result = await CSRFProtection.validate_csrf_token(mock_request, "token")

        # Assert
        assert result is True
        _, call_kwargs = mock_csrf_crud.validate_token_orm.call_args
        assert call_kwargs["session_id"] == "session_abc123_matching_session"[:32]

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_validate_csrf_token_ip_mismatch(
        self, mock_security_utils, mock_get_db, mock_request, mock_db, mock_cursor
    ):
        """Rechaza token cuando IP no coincide"""
        # Arrange
        mock_security_utils.get_client_ip.return_value = "192.168.1.100"
        mock_security_utils.hash_ip_address.return_value = "hashed_100"

        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {
            "id": 1,
            "ip_address": "hashed_200",  # IP diferente
            "session_id": None,
        }

        # Act
        result = await CSRFProtection.validate_csrf_token(mock_request, "token")

        # Assert
        assert result is False  # Debe ser False explícito, no None

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_validate_csrf_token_marks_as_used(
        self, mock_security_utils, mock_get_db, mock_csrf_crud, mock_request, mock_db, mock_cursor
    ):
        """Marca token como usado después de validación exitosa (delegado al CRUD ORM)"""
        # Arrange
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed_ip"

        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.validate_token_orm.return_value = True

        # Act
        result = await CSRFProtection.validate_csrf_token(mock_request, "token")

        # Assert - validate_token_orm internamente marca como usado y retorna True
        assert result is True
        mock_csrf_crud.validate_token_orm.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.get_db")
    @patch("app.middleware.csrf_protection.SecurityUtils")
    async def test_validate_csrf_token_handles_database_error(
        self, mock_security_utils, mock_get_db, mock_request, mock_db, mock_cursor
    ):
        """Retorna False ante error de base de datos"""
        # Arrange
        mock_security_utils.get_client_ip.return_value = "127.0.0.1"
        mock_security_utils.hash_ip_address.return_value = "hashed_ip"

        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor

        mock_cursor.execute.side_effect = Exception("DB Error")

        # Act
        result = await CSRFProtection.validate_csrf_token(mock_request, "token")

        # Assert
        assert result is False


# ============================================================================
# TESTS: CSRFProtection.cleanup_expired_tokens()
# ============================================================================


class TestCleanupExpiredTokens:
    """Tests para limpieza de tokens expirados"""

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.csrf_crud")
    @patch("app.middleware.csrf_protection.get_db")
    async def test_cleanup_expired_tokens_deletes_expired(
        self, mock_get_db, mock_csrf_crud, mock_db, mock_cursor
    ):
        """Elimina tokens expirados"""
        # Arrange
        mock_get_db.return_value = iter([mock_db])
        mock_csrf_crud.cleanup_orm.return_value = 5

        # Act
        await CSRFProtection.cleanup_expired_tokens()

        # Assert
        mock_csrf_crud.cleanup_orm.assert_called_once()
        _, call_kwargs = mock_csrf_crud.cleanup_orm.call_args
        assert call_kwargs.get("hours_old", 24) == 24

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.get_db")
    async def test_cleanup_expired_tokens_handles_error(self, mock_get_db, mock_db, mock_cursor):
        """Maneja error durante limpieza"""
        # Arrange
        mock_get_db.return_value = mock_db
        mock_db.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("DB Error")

        # Act & Assert
        # No debe propagar excepción
        await CSRFProtection.cleanup_expired_tokens()


# ============================================================================
# TESTS: csrf_middleware()
# ============================================================================


class TestCSRFMiddleware:
    """Tests para middleware de CSRF"""

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.security_settings")
    async def test_csrf_middleware_unprotected_endpoint(
        self, mock_settings, mock_request, mock_call_next
    ):
        """No valida CSRF en endpoints no protegidos"""
        # Arrange
        mock_settings.is_csrf_protected_endpoint.return_value = False
        mock_request.url.path = "/api/health"
        mock_request.method = "GET"

        # Act
        response = await csrf_middleware(mock_request, mock_call_next)

        # Assert
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.security_settings")
    async def test_csrf_middleware_safe_method(self, mock_settings, mock_request, mock_call_next):
        """No valida CSRF en métodos seguros (GET)"""
        # Arrange
        mock_settings.is_csrf_protected_endpoint.return_value = True
        mock_settings.CSRF_PROTECTED_METHODS = ["POST", "PUT", "DELETE"]
        mock_request.method = "GET"

        # Act
        response = await csrf_middleware(mock_request, mock_call_next)

        # Assert
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.CSRFProtection.validate_csrf_token")
    @patch("app.middleware.csrf_protection.security_settings")
    async def test_csrf_middleware_valid_token_in_form(
        self, mock_settings, mock_validate, mock_request, mock_call_next
    ):
        """Valida token CSRF de formulario correctamente"""
        # Arrange
        mock_settings.is_csrf_protected_endpoint.return_value = True
        mock_settings.CSRF_PROTECTED_METHODS = ["POST"]
        mock_request.method = "POST"
        mock_request.headers = {"content-type": "application/x-www-form-urlencoded"}

        async def mock_form():
            return {"csrf_token": "valid_token_123"}

        mock_request.form = mock_form
        mock_validate.return_value = True

        # Act
        response = await csrf_middleware(mock_request, mock_call_next)

        # Assert
        assert response.status_code == 200
        mock_validate.assert_called_once_with(mock_request, "valid_token_123")

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.CSRFProtection.validate_csrf_token")
    @patch("app.middleware.csrf_protection.security_settings")
    async def test_csrf_middleware_valid_token_in_header(
        self, mock_settings, mock_validate, mock_request, mock_call_next
    ):
        """Valida token CSRF de header correctamente"""
        # Arrange
        mock_settings.is_csrf_protected_endpoint.return_value = True
        mock_settings.CSRF_PROTECTED_METHODS = ["POST"]
        mock_request.method = "POST"
        mock_request.headers = {
            "content-type": "application/json",
            "X-CSRF-Token": "header_token_456",
        }

        async def mock_form():
            return {}

        mock_request.form = mock_form
        mock_validate.return_value = True

        # Act
        response = await csrf_middleware(mock_request, mock_call_next)

        # Assert
        assert response.status_code == 200
        mock_validate.assert_called_once_with(mock_request, "header_token_456")

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.security_settings")
    async def test_csrf_middleware_missing_token(self, mock_settings, mock_request, mock_call_next):
        """Rechaza request sin token CSRF"""
        # Arrange
        mock_settings.is_csrf_protected_endpoint.return_value = True
        mock_settings.CSRF_PROTECTED_METHODS = ["POST"]
        mock_request.method = "POST"
        mock_request.headers = {}

        async def mock_form():
            return {}

        mock_request.form = mock_form

        # Act & Assert
        # Devuelve la respuesta: una HTTPException en un middleware HTTP acaba en 500
        response = await csrf_middleware(mock_request, mock_call_next)

        assert response.status_code == 403
        assert json.loads(response.body)["detail"]["code"] == "security.csrf_token_invalid"

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.CSRFProtection.validate_csrf_token")
    @patch("app.middleware.csrf_protection.security_settings")
    async def test_csrf_middleware_invalid_token(
        self, mock_settings, mock_validate, mock_request, mock_call_next
    ):
        """Rechaza request con token inválido"""
        # Arrange
        mock_settings.is_csrf_protected_endpoint.return_value = True
        mock_settings.CSRF_PROTECTED_METHODS = ["POST"]
        mock_request.method = "POST"
        mock_request.headers = {"X-CSRF-Token": "invalid_token"}

        async def mock_form():
            return {}

        mock_request.form = mock_form
        mock_validate.return_value = False  # Token inválido

        # Act & Assert
        response = await csrf_middleware(mock_request, mock_call_next)

        assert response.status_code == 403

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.security_settings")
    async def test_csrf_middleware_form_parsing_error(
        self, mock_settings, mock_request, mock_call_next
    ):
        """Maneja error al parsear formulario"""
        # Arrange
        mock_settings.is_csrf_protected_endpoint.return_value = True
        mock_settings.CSRF_PROTECTED_METHODS = ["POST"]
        mock_request.method = "POST"
        mock_request.headers = {"content-type": "application/x-www-form-urlencoded"}

        async def mock_form_error():
            raise Exception("Parse error")

        mock_request.form = mock_form_error

        # Act & Assert
        # Debe buscar en header como fallback
        response = await csrf_middleware(mock_request, mock_call_next)

        assert response.status_code == 403


# ============================================================================
# TESTS: get_csrf_token_for_template()
# ============================================================================


class TestGetCSRFTokenForTemplate:
    """Tests para función auxiliar de templates"""

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.CSRFProtection.generate_csrf_token")
    async def test_get_csrf_token_for_template_returns_token(self, mock_generate, mock_request):
        """Retorna token CSRF para template"""
        # Arrange
        mock_generate.return_value = "template_token_789"

        # Act
        token = await get_csrf_token_for_template(mock_request)

        # Assert
        assert token == "template_token_789"
        mock_generate.assert_called_once_with(mock_request)


# ============================================================================
# TESTS: csrf_protect() decorator
# ============================================================================


class TestCSRFProtectDecorator:
    """Tests para decorador csrf_protect"""

    @pytest.mark.asyncio
    async def test_csrf_protect_with_request_in_args(self):
        """Decorador funciona con request en args"""

        # Arrange
        @csrf_protect
        async def endpoint(request: Request):
            return {"status": "ok"}

        mock_request = MagicMock(spec=Request)

        # Act
        result = await endpoint(mock_request)

        # Assert
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_csrf_protect_with_request_in_kwargs(self):
        """Decorador funciona con request en kwargs"""

        # Arrange
        @csrf_protect
        async def endpoint(request: Request):
            return {"status": "ok"}

        mock_request = MagicMock(spec=Request)

        # Act
        result = await endpoint(request=mock_request)

        # Assert
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_csrf_protect_without_request(self):
        """Decorador funciona sin request (fallback al middleware)"""

        # Arrange
        @csrf_protect
        async def endpoint():
            return {"status": "ok"}

        # Act
        result = await endpoint()

        # Assert
        assert result == {"status": "ok"}


# ============================================================================
# TESTS: start_csrf_cleanup_task()
# ============================================================================


class TestStartCSRFCleanupTask:
    """Tests para tarea de limpieza periódica"""

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.CSRFProtection.cleanup_expired_tokens")
    @patch("app.middleware.csrf_protection.asyncio.sleep", new_callable=AsyncMock)
    async def test_start_csrf_cleanup_task_runs_periodically(self, mock_sleep, mock_cleanup):
        """Tarea ejecuta limpieza periódicamente"""
        # Arrange
        call_count = [0]

        async def limited_cleanup():
            call_count[0] += 1
            if call_count[0] >= 2:
                # Cancelar después de 2 llamadas
                raise asyncio.CancelledError()

        mock_cleanup.side_effect = limited_cleanup

        # Act & Assert
        with pytest.raises(asyncio.CancelledError):
            await start_csrf_cleanup_task()

        # Debe llamar a cleanup al menos una vez
        assert mock_cleanup.call_count >= 1

    @pytest.mark.asyncio
    @patch("app.middleware.csrf_protection.CSRFProtection.cleanup_expired_tokens")
    @patch("app.middleware.csrf_protection.asyncio.sleep", new_callable=AsyncMock)
    async def test_start_csrf_cleanup_task_handles_error(self, mock_sleep, mock_cleanup):
        """Tarea maneja errores y continúa"""
        # Arrange
        call_count = [0]

        async def cleanup_with_error():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Cleanup error")
            elif call_count[0] >= 2:
                raise asyncio.CancelledError()

        mock_cleanup.side_effect = cleanup_with_error

        # Act & Assert
        with pytest.raises(asyncio.CancelledError):
            await start_csrf_cleanup_task()

        # Debe intentar nuevamente después del error
        assert mock_cleanup.call_count >= 2
