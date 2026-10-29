"""
Database Adapters Package

Conectores para bases de datos externas con soporte para múltiples dialectos SQL.

SEGURIDAD IMPORTANTE:
- Solo lectura de METADATA (estructura de BDs)
- NO acceso a datos de usuario
- Permisos limitados a information_schema y vistas de sistema

Usage:
    from app.utils.db_adapters import PostgreSQLAdapter

    config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'mydb',
        'user': 'datamap_readonly',
        'password': 'secure_password',
    }

    with PostgreSQLAdapter(config) as adapter:
        tables = adapter.get_tables()
        for table in tables:
            columns = adapter.get_columns(table.name)
            print(f"{table.name}: {len(columns)} columns")
"""

from .base_adapter import BaseDBAdapter
from .exceptions import (
    DBAdapterError,
    DBAuthenticationError,
    DBConnectionError,
    DBDialectNotSupportedError,
    DBHostNotAllowedError,
    DBMetadataNotFoundError,
    DBPermissionError,
    DBQueryExecutionError,
    DBTimeoutError,
    DBTLSError,
    DBValidationError,
)
from .mysql_adapter import MySQLAdapter
from .network_policy import validate_connection_host
from .oracle_adapter import OracleAdapter

# Import adapters específicos
from .postgres_adapter import PostgreSQLAdapter
from .sqlserver_adapter import SQLServerAdapter
from .validators import (
    detect_sql_injection_attempt,
    validate_column_name,
    validate_connection_config,
    validate_identifier,
    validate_metadata_name,
    validate_schema_name,
    validate_table_name,
)

__all__ = [
    # Base
    "BaseDBAdapter",
    # Exceptions
    "DBAdapterError",
    "DBConnectionError",
    "DBAuthenticationError",
    "DBQueryExecutionError",
    "DBPermissionError",
    "DBValidationError",
    "DBDialectNotSupportedError",
    "DBHostNotAllowedError",
    "DBTimeoutError",
    "DBTLSError",
    "DBMetadataNotFoundError",
    # Validators
    "validate_identifier",
    "validate_metadata_name",
    "validate_table_name",
    "validate_column_name",
    "validate_schema_name",
    "validate_connection_config",
    "detect_sql_injection_attempt",
    "validate_connection_host",
    # Adapters
    "PostgreSQLAdapter",
    "MySQLAdapter",
    "SQLServerAdapter",
    "OracleAdapter",
]


# Versión del paquete
__version__ = "1.0.0"
