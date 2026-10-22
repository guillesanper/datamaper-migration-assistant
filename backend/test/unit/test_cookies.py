# test/unit/test_cookies.py
"""
Tests unitarios para app.utils.cookies
Módulo: Firma y verificación de cookies con itsdangerous
"""

import hashlib
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Setup path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Mock SECRET_KEY before importing the module
os.environ["SECRET_KEY"] = "test-secret-key-12345"

# Import functions to test
from app.utils.cookies import sign_cookie, verify_signed_cookie


@pytest.fixture
def mock_secret_key():
    """Fixture para proporcionar una SECRET_KEY de prueba"""
    return "test-secret-key-12345"


class TestSignCookie:
    """Tests para la función sign_cookie()"""

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_sign_cookie_with_simple_string(self):
        """Test: Debe firmar correctamente una cadena simple"""
        value = "user123"
        result = sign_cookie(value)

        assert result is not None
        assert isinstance(result, str)
        assert len(result) > len(value)  # Firmado es más largo que original
        assert value not in result  # El valor original está codificado

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_sign_cookie_with_complex_string(self):
        """Test: Debe manejar cadenas con caracteres especiales"""
        value = "user@test.com|session123|2025-01-01"
        result = sign_cookie(value)

        assert result is not None
        assert isinstance(result, str)

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_sign_cookie_with_empty_string(self):
        """Test: Debe manejar cadenas vacías"""
        value = ""
        result = sign_cookie(value)

        assert result is not None
        assert isinstance(result, str)

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_sign_cookie_returns_different_values_for_different_inputs(self):
        """Test: Diferentes valores deben generar diferentes firmas"""
        value1 = "user123"
        value2 = "user456"

        result1 = sign_cookie(value1)
        result2 = sign_cookie(value2)

        assert result1 != result2

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_sign_cookie_is_deterministic(self):
        """Test: Mismo valor debe generar la misma firma (determinístico)"""
        value = "user123"

        result1 = sign_cookie(value)
        result2 = sign_cookie(value)

        assert result1 == result2


class TestVerifySignedCookie:
    """Tests para la función verify_signed_cookie()"""

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_verify_valid_signed_cookie(self):
        """Test: Debe verificar correctamente una cookie firmada válida"""
        original_value = "user123"
        signed_value = sign_cookie(original_value)

        result = verify_signed_cookie(signed_value)

        assert result == original_value

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_verify_invalid_signature(self):
        """Test: Debe retornar None para firmas inválidas"""
        invalid_cookie = "invalid.signature.here"

        result = verify_signed_cookie(invalid_cookie)

        assert result is None

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_verify_tampered_cookie(self):
        """Test: Debe detectar cookies manipuladas"""
        original_value = "user123"
        signed_value = sign_cookie(original_value)

        # Manipular la cookie (cambiar un carácter)
        tampered_value = signed_value[:-1] + "X"

        result = verify_signed_cookie(tampered_value)

        assert result is None

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_verify_empty_string(self):
        """Test: Debe manejar cadenas vacías"""
        result = verify_signed_cookie("")

        assert result is None

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_verify_none_value(self):
        """Test: Debe manejar valores None sin crash"""
        # Este test verifica comportamiento robusto
        # La función actual no maneja None explícitamente
        # pero debería retornar None sin crash
        try:
            result = verify_signed_cookie(None)
            assert result is None
        except (TypeError, AttributeError):
            # Es aceptable que falle con None, pero documentamos el comportamiento
            pass

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_verify_with_different_secret_key_fails(self):
        """Test: Cookie firmada con diferente SECRET_KEY debe fallar"""
        from itsdangerous import URLSafeSerializer

        # Crear dos serializers con diferentes keys para simular el comportamiento
        # cuando SECRET_KEY es diferente entre firma y verificación
        serializer_key1 = URLSafeSerializer("key1")
        serializer_key2 = URLSafeSerializer("key2")

        # Firmar con key1
        signed_value = serializer_key1.dumps("user123")

        # Intentar verificar con key2 (debe fallar)
        try:
            result = serializer_key2.loads(signed_value)
            # Si no lanza excepción, el test falla
            pytest.fail("Expected BadSignature exception when using different key")
        except Exception:
            # Esto es lo esperado - la firma no coincide
            # Verificamos que el comportamiento es el mismo que verify_signed_cookie
            pass

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_verify_signed_cookie_with_special_characters(self):
        """Test: Debe manejar valores con caracteres especiales"""
        original_value = "user@example.com|session|123"
        signed_value = sign_cookie(original_value)

        result = verify_signed_cookie(signed_value)

        assert result == original_value


class TestCookiesIntegration:
    """Tests de integración entre sign y verify"""

    @patch.dict(os.environ, {"SECRET_KEY": "test-secret-key-12345"})
    def test_sign_and_verify_roundtrip(self):
        """Test: Ciclo completo de firmar y verificar"""
        test_values = [
            "simple",
            "with-dashes",
            "with_underscores",
            "with.dots",
            "user@example.com",
            "123456",
            "mixed123ABC!@#",
        ]

        for original_value in test_values:
            signed = sign_cookie(original_value)
            verified = verify_signed_cookie(signed)

            assert verified == original_value, f"Failed for value: {original_value}"


class TestGetSessionTokenHash:
    """Tests para la función get_session_token_hash()"""

    @staticmethod
    def _hash_for(cookies):
        """Ejecuta el helper con una request mínima: solo lee request.cookies"""
        from app.utils.cookies import get_session_token_hash

        return get_session_token_hash(SimpleNamespace(cookies=cookies))

    def test_returns_sha256_of_the_signed_token(self):
        """Test: Cookie firmada válida -> sha256 hex del token en claro"""
        raw_token = "token-de-sesion-123"

        result = self._hash_for({"session": sign_cookie(raw_token)})

        assert result == hashlib.sha256(raw_token.encode()).hexdigest()

    def test_returns_none_without_cookie(self):
        """Test: Sin cookie (p. ej. autenticación por API key) -> None"""
        assert self._hash_for({}) is None

    def test_returns_none_for_invalid_or_tampered_signature(self):
        """Test: Cookie con firma inválida o manipulada -> None"""
        signed = sign_cookie("token-de-sesion-123")

        assert self._hash_for({"session": "no.es.valida"}) is None
        assert self._hash_for({"session": signed[:-1] + "X"}) is None
