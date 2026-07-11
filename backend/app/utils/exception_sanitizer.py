"""
Exception Sanitizer - Security Module
======================================

Este módulo proporciona utilidades para sanitizar excepciones antes de ser
loggeadas o devueltas al usuario, previniendo la filtración de información
sensible como passphrases, tokens, o claves de encriptación.

CORRECCIÓN DE VULNERABILIDAD: 🔴 CRÍTICA
- Previene exposición de passphrases en logs de error
- Sanitiza tracebacks para eliminar argumentos sensibles
- Proporciona mensajes genéricos hacia usuarios finales

Author: Sistema de Seguridad DataMap
Date: 2025-01-03
"""

import logging
import re
import traceback
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Lista de palabras clave que indican información sensible
SENSITIVE_KEYWORDS = [
    "passphrase",
    "password",
    "secret",
    "token",
    "key",
    "encryption_key",
    "master_key",
    "api_key",
    "auth",
    "credential",
    "private",
]


class SanitizedException(Exception):
    """
    Excepción sanitizada que puede ser mostrada al usuario sin riesgos de seguridad.

    Attributes:
        user_message: Mensaje seguro para mostrar al usuario
        internal_message: Mensaje detallado para logs internos (sanitizado)
        original_type: Tipo de la excepción original
        error_code: Código de error opcional para tracking
    """

    def __init__(
        self,
        user_message: str,
        internal_message: str,
        original_type: str,
        error_code: Optional[str] = None,
    ):
        self.user_message = user_message
        self.internal_message = internal_message
        self.original_type = original_type
        self.error_code = error_code
        super().__init__(user_message)


def _mask_sensitive_value(value: str, show_length: bool = False) -> str:
    """
    Enmascara un valor sensible para logging seguro.

    Args:
        value: Valor a enmascarar
        show_length: Si True, muestra la longitud del valor original

    Returns:
        Valor enmascarado (e.g., "***REDACTED***" o "***REDACTED[12]***")

    Example:
        >>> _mask_sensitive_value("MySecurePassword123")
        "***REDACTED***"
        >>> _mask_sensitive_value("MySecurePassword123", show_length=True)
        "***REDACTED[19]***"
    """
    if show_length:
        return f"***REDACTED[{len(value)}]***"
    return "***REDACTED***"


def _contains_sensitive_keyword(text: str) -> bool:
    """
    Verifica si el texto contiene palabras clave sensibles.

    Args:
        text: Texto a verificar

    Returns:
        True si contiene palabras sensibles, False en caso contrario
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in SENSITIVE_KEYWORDS)


def sanitize_dict(data: Dict[str, Any], mask_values: bool = True) -> Dict[str, Any]:
    """
    Sanitiza un diccionario eliminando o enmascarando valores sensibles.

    Args:
        data: Diccionario a sanitizar
        mask_values: Si True, enmascara valores sensibles. Si False, elimina las keys.

    Returns:
        Diccionario sanitizado

    Example:
        >>> sanitize_dict({"username": "john", "password": "secret123"})
        {"username": "john", "password": "***REDACTED***"}
    """
    sanitized: Dict[str, Any] = {}

    for key, value in data.items():
        # Verificar si la key es sensible
        if _contains_sensitive_keyword(key):
            if mask_values:
                sanitized[key] = _mask_sensitive_value(str(value), show_length=True)
            # Si mask_values=False, simplemente no incluimos la key
            continue

        # Recursivamente sanitizar valores que sean dicts
        if isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, mask_values)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict(item, mask_values) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def sanitize_traceback(tb_lines: List[str]) -> List[str]:
    """
    Sanitiza las líneas de un traceback eliminando argumentos sensibles.

    Args:
        tb_lines: Lista de líneas del traceback

    Returns:
        Lista de líneas sanitizadas

    Security Note:
        Los tracebacks de Python pueden incluir valores de argumentos en la pila,
        lo que podría exponer passphrases o claves. Este método elimina esos valores.
    """
    sanitized_lines = []

    for line in tb_lines:
        # Buscar patrones de argumentos de función
        # Ejemplo: "function(passphrase='secret123')" -> "function(passphrase=***REDACTED***)"

        # Pattern para capturar asignaciones de parámetros
        pattern = r"(\b(?:" + "|".join(SENSITIVE_KEYWORDS) + r')\s*=\s*)["\']([^"\']+)["\']'

        sanitized_line = re.sub(pattern, r"\1***REDACTED***", line, flags=re.IGNORECASE)

        sanitized_lines.append(sanitized_line)

    return sanitized_lines


def sanitize_exception(
    exception: Exception,
    user_friendly_message: Optional[str] = None,
    include_type: bool = True,
    error_code: Optional[str] = None,
) -> SanitizedException:
    """
    Sanitiza una excepción para uso seguro en logs y respuestas HTTP.

    Args:
        exception: Excepción original a sanitizar
        user_friendly_message: Mensaje opcional para el usuario (genérico)
        include_type: Si True, incluye el tipo de excepción en el mensaje interno
        error_code: Código de error opcional para tracking

    Returns:
        SanitizedException con mensajes seguros

    Example:
        ```python
        try:
            verify_passphrase(user_input)
        except Exception as e:
            safe_exc = sanitize_exception(
                e,
                user_friendly_message="Error de autenticación",
                error_code="AUTH_001"
            )
            logger.error(safe_exc.internal_message)
            raise HTTPException(status_code=500, detail=safe_exc.user_message)
        ```
    """
    # Mensaje genérico para el usuario
    if user_friendly_message is None:
        user_friendly_message = "Ocurrió un error procesando la solicitud"

    # Obtener información básica de la excepción
    exc_type = type(exception).__name__
    exc_message = str(exception)

    # Sanitizar el mensaje de error
    sanitized_message = exc_message
    for keyword in SENSITIVE_KEYWORDS:
        # Reemplazar patrones como "passphrase='secret'" con "passphrase=***REDACTED***"
        pattern = rf"{keyword}\s*=\s*['\"]?[^'\")\s]+['\"]?"
        sanitized_message = re.sub(
            pattern, f"{keyword}=***REDACTED***", sanitized_message, flags=re.IGNORECASE
        )

    # Construir mensaje interno (para logs)
    if include_type:
        internal_message = f"{exc_type}: {sanitized_message}"
    else:
        internal_message = sanitized_message

    if error_code:
        internal_message = f"[{error_code}] {internal_message}"

    return SanitizedException(
        user_message=user_friendly_message,
        internal_message=internal_message,
        original_type=exc_type,
        error_code=error_code,
    )


def safe_log_exception(
    exception: Exception,
    logger_instance: logging.Logger,
    level: str = "error",
    context: Optional[Dict[str, Any]] = None,
    user_friendly_message: Optional[str] = None,
) -> SanitizedException:
    """
    Loggea una excepción de forma segura, sanitizando información sensible.

    Args:
        exception: Excepción a loggear
        logger_instance: Instancia del logger a usar
        level: Nivel de log (debug, info, warning, error, critical)
        context: Contexto adicional a loggear (será sanitizado)
        user_friendly_message: Mensaje opcional para el usuario

    Returns:
        SanitizedException que puede ser usada en respuestas HTTP

    Example:
        ```python
        try:
            risky_operation(passphrase)
        except Exception as e:
            safe_exc = safe_log_exception(
                e,
                logger,
                level="error",
                context={"operation": "encryption_setup", "project_id": project_id}
            )
            raise HTTPException(status_code=500, detail=safe_exc.user_message)
        ```
    """
    # Sanitizar la excepción
    sanitized_exc = sanitize_exception(exception, user_friendly_message)

    # Preparar contexto sanitizado
    sanitized_context = {}
    if context:
        sanitized_context = sanitize_dict(context, mask_values=True)

    # Construir mensaje de log
    log_message = sanitized_exc.internal_message
    if sanitized_context:
        log_message += f" | Context: {sanitized_context}"

    # Loggear según el nivel
    log_method = getattr(logger_instance, level.lower(), logger_instance.error)
    log_method(log_message)

    # Loggear traceback sanitizado solo en modo DEBUG
    if logger_instance.isEnabledFor(logging.DEBUG):
        tb_lines = traceback.format_tb(exception.__traceback__)
        sanitized_tb = sanitize_traceback(tb_lines)
        logger_instance.debug("Sanitized traceback:\n" + "".join(sanitized_tb))

    return sanitized_exc


def create_safe_http_exception(
    exception: Exception,
    status_code: int = 500,
    default_detail: str = "Error interno del servidor",
    error_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crea un diccionario seguro para respuestas HTTP a partir de una excepción.

    Args:
        exception: Excepción original
        status_code: Código HTTP a retornar
        default_detail: Mensaje por defecto si no se puede extraer uno seguro
        error_code: Código de error opcional para tracking

    Returns:
        Diccionario con {status_code, detail, error_code}

    Example:
        ```python
        try:
            dangerous_operation()
        except Exception as e:
            error_response = create_safe_http_exception(
                e,
                status_code=500,
                error_code="ENC_001"
            )
            raise HTTPException(**error_response)
        ```
    """
    sanitized_exc = sanitize_exception(
        exception, user_friendly_message=default_detail, error_code=error_code
    )

    response = {"status_code": status_code, "detail": sanitized_exc.user_message}

    if error_code:
        response["headers"] = {"X-Error-Code": error_code}

    return response


# Decorador para sanitizar excepciones automáticamente
def sanitize_exceptions(
    user_message: str = "Error procesando la solicitud",
    log_level: str = "error",
    error_code_prefix: Optional[str] = None,
):
    """
    Decorador que sanitiza automáticamente las excepciones de una función.

    Args:
        user_message: Mensaje genérico para el usuario
        log_level: Nivel de logging
        error_code_prefix: Prefijo para códigos de error automáticos

    Example:
        ```python
        @sanitize_exceptions(
            user_message="Error configurando encriptación",
            error_code_prefix="ENC"
        )
        def setup_encryption(project_id: str, passphrase: str):
            # Código que podría lanzar excepciones
            pass
        ```
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Generar código de error único
                error_code = None
                if error_code_prefix:
                    error_code = f"{error_code_prefix}_{func.__name__.upper()}"

                # Sanitizar y loggear
                safe_exc = safe_log_exception(
                    e,
                    logger,
                    level=log_level,
                    context={
                        "function": func.__name__,
                        "args_count": len(args),
                        "kwargs_keys": list(kwargs.keys()),
                    },
                    user_friendly_message=user_message,
                )

                # Re-lanzar la excepción sanitizada
                raise safe_exc

        return wrapper

    return decorator


if __name__ == "__main__":
    # Tests básicos
    print("=== Test: Sanitización de diccionario ===")
    test_data = {
        "username": "john_doe",
        "password": "secret123",
        "encryption_key": "abc123xyz",
        "project_id": "uuid-1234",
        "nested": {"api_token": "token_value", "safe_field": "safe_value"},
    }
    sanitized = sanitize_dict(test_data)
    print("Original:", test_data)
    print("Sanitized:", sanitized)

    print("\n=== Test: Sanitización de excepción ===")
    try:
        # Simular una excepción con información sensible
        raise ValueError("Invalid passphrase='MySecretPass123' provided")
    except Exception as e:
        safe_exc = sanitize_exception(
            e, user_friendly_message="Error de autenticación", error_code="AUTH_001"
        )
        print("User Message:", safe_exc.user_message)
        print("Internal Message:", safe_exc.internal_message)
        print("Error Code:", safe_exc.error_code)
