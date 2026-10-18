"""
Security Validators

Validadores para prevenir SQL injection y asegurar inputs seguros.
"""

import ipaddress
import re
from typing import Optional

from .exceptions import DBValidationError

# Pattern para nombres válidos de identificadores SQL (tablas, columnas, schemas)
# Solo permite: letras, números, underscore
# Debe empezar con letra o underscore
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Longitud máxima de identificadores (estándar SQL)
MAX_IDENTIFIER_LENGTH = 128

# Etiqueta de hostname DNS (RFC 1123, permitiendo '_' por los nombres de servicio de Docker)
HOSTNAME_LABEL_PATTERN = re.compile(r"[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?")

# Longitud máxima de un hostname DNS sin el punto final (RFC 1035)
MAX_HOSTNAME_LENGTH = 253

# Keywords reservadas de SQL (subset común a todos los dialectos)
SQL_RESERVED_KEYWORDS = {
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "CREATE",
    "ALTER",
    "TRUNCATE",
    "FROM",
    "WHERE",
    "JOIN",
    "UNION",
    "GRANT",
    "REVOKE",
    "EXECUTE",
    "EXEC",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    "INTO",
    "VALUES",
    "SET",
    "TABLE",
    "DATABASE",
    "INDEX",
    "VIEW",
    "PROCEDURE",
    "FUNCTION",
    "TRIGGER",
    "DECLARE",
    "CURSOR",
    # Comandos peligrosos
    "xp_cmdshell",
    "sp_executesql",
    "LOAD_FILE",
    "INTO OUTFILE",
}


def validate_identifier(name: str, identifier_type: str = "identifier") -> str:
    """
    Valida que un identificador SQL sea seguro (previene SQL injection).

    Args:
        name: Nombre del identificador (tabla, columna, schema, etc.)
        identifier_type: Tipo de identificador para mensaje de error

    Returns:
        El nombre validado (sin cambios)

    Raises:
        DBValidationError: Si el nombre no es válido

    Examples:
        >>> validate_identifier("users")
        'users'
        >>> validate_identifier("user_profiles")
        'user_profiles'
        >>> validate_identifier("users'; DROP TABLE users;--")
        DBValidationError: Invalid identifier...
    """
    if not name:
        raise DBValidationError(f"{identifier_type} cannot be empty")

    # Verificar longitud
    if len(name) > MAX_IDENTIFIER_LENGTH:
        raise DBValidationError(
            f"{identifier_type} '{name}' exceeds maximum length of {MAX_IDENTIFIER_LENGTH} characters"
        )

    # Verificar patrón
    if not IDENTIFIER_PATTERN.match(name):
        raise DBValidationError(
            f"Invalid {identifier_type} '{name}'. "
            f"Only alphanumeric characters and underscore are allowed. "
            f"Must start with a letter or underscore."
        )

    # Verificar reserved keywords
    if name.upper() in SQL_RESERVED_KEYWORDS:
        raise DBValidationError(
            f"{identifier_type} '{name}' is a reserved SQL keyword and cannot be used"
        )

    return name


def validate_table_name(table_name: str) -> str:
    """
    Valida nombre de tabla.

    Args:
        table_name: Nombre de la tabla

    Returns:
        El nombre validado

    Raises:
        DBValidationError: Si el nombre no es válido
    """
    return validate_identifier(table_name, "Table name")


def validate_column_name(column_name: str) -> str:
    """
    Valida nombre de columna.

    Args:
        column_name: Nombre de la columna

    Returns:
        El nombre validado

    Raises:
        DBValidationError: Si el nombre no es válido
    """
    return validate_identifier(column_name, "Column name")


def validate_schema_name(schema_name: str) -> str:
    """
    Valida nombre de schema/database.

    Args:
        schema_name: Nombre del schema

    Returns:
        El nombre validado

    Raises:
        DBValidationError: Si el nombre no es válido
    """
    return validate_identifier(schema_name, "Schema name")


def validate_index_name(index_name: str) -> str:
    """
    Valida nombre de índice.

    Args:
        index_name: Nombre del índice

    Returns:
        El nombre validado

    Raises:
        DBValidationError: Si el nombre no es válido
    """
    return validate_identifier(index_name, "Index name")


def sanitize_for_logging(value: str, max_length: int = 100) -> str:
    """
    Sanitiza un valor para logging seguro.

    - Trunca a max_length caracteres
    - Remueve caracteres peligrosos
    - No expone información sensible completa

    Args:
        value: Valor a sanitizar
        max_length: Longitud máxima

    Returns:
        Valor sanitizado
    """
    if not value:
        return "[empty]"

    # Truncar
    if len(value) > max_length:
        value = value[:max_length] + "..."

    # Remover caracteres de control
    value = "".join(char if char.isprintable() else "?" for char in value)

    return value


def detect_sql_injection_attempt(value: str) -> bool:
    """
    Detecta posibles intentos de SQL injection.

    Busca patrones comunes de SQL injection:
    - Comentarios SQL (-- o /* */)
    - Múltiples statements (;)
    - UNION attacks
    - Comandos peligrosos

    Args:
        value: Valor a analizar

    Returns:
        True si se detecta posible SQL injection, False en caso contrario

    Note:
        Esta función es un complemento a validate_identifier().
        validate_identifier() es la defensa principal.
    """
    value_upper = value.upper()

    # Patrones sospechosos
    suspicious_patterns = [
        "--",  # Comentarios SQL
        "/*",  # Comentarios multi-línea
        "*/",
        ";",  # Múltiples statements
        "UNION",  # UNION attacks
        "DROP ",
        "DELETE ",
        "INSERT ",
        "UPDATE ",
        "EXEC",
        "EXECUTE",
        "xp_",  # Extended stored procedures (SQL Server)
        "sp_",  # System stored procedures
        "LOAD_FILE",  # MySQL file read
        "INTO OUTFILE",  # MySQL file write
        "WAITFOR",  # SQL Server time delays
        "BENCHMARK",  # MySQL time delays
        "SLEEP(",  # MySQL sleep
        "PG_SLEEP",  # PostgreSQL sleep
    ]

    for pattern in suspicious_patterns:
        if pattern in value_upper:
            return True

    return False


def validate_host(host: str) -> str:
    """
    Valida que el host sea un hostname DNS o una IP (v4/v6).

    El host se interpola en cadenas de conexión (ODBC) y descriptores (Oracle), donde
    ';', '{', '}', '(', ')', '=', ',' o espacios cambiarían el significado de la cadena.

    Args:
        host: Hostname o IP

    Returns:
        El mismo host, sin modificar

    Raises:
        DBValidationError: Si no es un hostname ni una IP válidos
    """
    if not isinstance(host, str) or not host.strip():
        raise DBValidationError("Invalid host: empty")

    if _is_ip_address(host):
        return host

    name = host[:-1] if host.endswith(".") else host
    if len(name) > MAX_HOSTNAME_LENGTH or not all(
        HOSTNAME_LABEL_PATTERN.fullmatch(label) for label in name.split(".")
    ):
        raise DBValidationError("Invalid host: must be a hostname or an IP address")

    return host


def _is_ip_address(value: str) -> bool:
    """True si value es una IPv4/IPv6 literal (sin zone id)."""
    if "%" in value:
        return False
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def validate_connection_config(config: dict) -> dict:
    """
    Valida configuración de conexión.

    Args:
        config: Dict con configuración de conexión

    Returns:
        Config validada

    Raises:
        DBValidationError: Si la configuración no es válida
    """
    required_fields = ["host", "port", "database", "user", "password"]

    for field in required_fields:
        if field not in config:
            raise DBValidationError(f"Missing required field: {field}")

    # Validar host
    if not config["host"] or len(config["host"]) > 255:
        raise DBValidationError("Invalid host")
    validate_host(config["host"])

    # Validar port
    port = config["port"]
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise DBValidationError(f"Invalid port: {port}. Must be between 1 and 65535")

    # Validar database name
    validate_identifier(config["database"], "Database name")

    # Validar timeout si está presente
    if "timeout" in config:
        timeout = config["timeout"]
        if not isinstance(timeout, int) or timeout < 1 or timeout > 600:
            raise DBValidationError(
                f"Invalid timeout: {timeout}. Must be between 1 and 600 seconds"
            )

    return config
