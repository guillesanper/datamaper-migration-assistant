"""
Database Adapter Exceptions

Exceptions personalizadas para manejo de errores en conectores de BD.
"""


class DBAdapterError(Exception):
    """Base exception para todos los errores de adapters"""

    pass


class DBConnectionError(DBAdapterError):
    """
    Error al establecer conexión con la base de datos.

    Se lanza cuando:
    - Host no alcanzable
    - Puerto cerrado
    - Timeout de conexión
    - Red no disponible
    """

    pass


class DBAuthenticationError(DBAdapterError):
    """
    Error de autenticación (credenciales inválidas).

    Se lanza cuando:
    - Usuario no existe
    - Password incorrecta
    - Permisos insuficientes para conectar
    """

    pass


class DBQueryExecutionError(DBAdapterError):
    """
    Error al ejecutar una query.

    Se lanza cuando:
    - Sintaxis SQL inválida
    - Tabla/columna no existe
    - Permisos insuficientes
    - Timeout de query
    """

    pass


class DBPermissionError(DBAdapterError):
    """
    Error de permisos insuficientes.

    Se lanza cuando:
    - Usuario no tiene permisos de lectura en information_schema
    - Intento de acceder a tablas de usuario sin permisos
    """

    pass


class DBValidationError(DBAdapterError, ValueError):
    """
    Error de validación de inputs.

    Se lanza cuando:
    - Nombre de tabla/columna inválido (SQL injection attempt)
    - Parámetros de configuración inválidos

    Inherits from ValueError for backward compatibility with tests.
    """

    pass


class DBDialectNotSupportedError(DBAdapterError):
    """
    Dialecto SQL no soportado.

    Se lanza cuando:
    - Se intenta usar un dialecto que no está implementado
    """

    pass


class DBTimeoutError(DBAdapterError):
    """
    Timeout en operación de BD.

    Se lanza cuando:
    - Conexión tarda más del timeout configurado
    - Query tarda más del timeout configurado
    """

    pass


class DBMetadataNotFoundError(DBAdapterError):
    """
    Metadata solicitada no encontrada.

    Se lanza cuando:
    - Tabla no existe
    - Schema no existe
    - Columna no encontrada
    """

    pass
