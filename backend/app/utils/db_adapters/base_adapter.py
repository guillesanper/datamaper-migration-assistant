"""
Base Database Adapter

Clase abstracta que define la interfaz común para todos los conectores de BD.

IMPORTANTE: Los adapters solo leen METADATA (estructura), NO datos de usuario.
"""

import logging
import re
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from app.models.db_metadata import (
    ColumnMetadata,
    ForeignKeyMetadata,
    IndexMetadata,
    PrimaryKeyMetadata,
    SchemaMetadata,
    TableMetadata,
    TableStatistics,
    UniqueConstraintMetadata,
)

from .exceptions import (
    DBAuthenticationError,
    DBConnectionError,
    DBMetadataNotFoundError,
    DBPermissionError,
    DBQueryExecutionError,
)
from .validators import validate_connection_config

logger = logging.getLogger(__name__)


class BaseDBAdapter(ABC):
    """
    Adapter base para conexiones a bases de datos externas.

    Todos los adapters específicos (PostgreSQL, MySQL, SQL Server, Oracle)
    deben heredar de esta clase e implementar los métodos abstractos.

    SEGURIDAD IMPORTANTE:
    - Solo lectura de METADATA (information_schema, pg_catalog, sys views)
    - NO ejecuta queries sobre datos de usuario
    - Usuario de conexión debe tener permisos limitados a metadata
    """

    def __init__(self, connection_config: Dict[str, Any]):
        """
        Inicializa el adapter con configuración de conexión.

        Args:
            connection_config: Dict con keys:
                - host: str
                - port: int
                - database: str
                - user: str
                - password: str
                - ssl_mode: 'verify' | 'require' | 'disable' (opcional, default 'verify')
                - timeout: int (opcional, default 30)
        """
        # Validar configuración
        self.connection_config = validate_connection_config(connection_config)
        self.connection: Any = None
        self._is_connected = False
        self.timeout = connection_config.get("timeout", 30)
        self.ssl_mode = connection_config.get("ssl_mode", "verify")

    @property
    @abstractmethod
    def dialect(self) -> str:
        """
        Retorna el dialecto SQL: 'postgresql', 'mysql', 'sqlserver', 'oracle'.

        Este valor se usa para:
        - Generación de scripts SQL específicos del dialecto
        - Traducción de queries entre dialectos
        - Mapeo de tipos de datos
        """
        pass

    @property
    def is_connected(self) -> bool:
        """Retorna True si hay una conexión activa"""
        return self._is_connected and self.connection is not None

    @property
    def connection_info(self) -> Dict[str, Any]:
        """
        Retorna metadata de la conexión (sin credenciales sensibles).

        Returns:
            Dict con: host, port, database, dialect, is_connected
        """
        return {
            "host": self.connection_config.get("host"),
            "port": self.connection_config.get("port"),
            "database": self.connection_config.get("database"),
            "dialect": self.dialect,
            "is_connected": self.is_connected,
            "timeout": self.timeout,
        }

    # =============================================================================
    # CONNECTION MANAGEMENT
    # =============================================================================

    @abstractmethod
    def connect(self) -> None:
        """
        Establece conexión con la base de datos.

        Raises:
            DBConnectionError: Si no se puede conectar
            DBAuthenticationError: Si las credenciales son inválidas
            DBPermissionError: Si el usuario no tiene permisos necesarios
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """
        Cierra la conexión con la base de datos.

        Este método debe ser llamado siempre, incluso si hay errores.
        Usar context manager (__enter__/__exit__) es la forma recomendada.
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Valida credenciales sin mantener conexión abierta.

        Útil para verificar que las credenciales son correctas antes de
        crear una sesión de conexión.

        Returns:
            True si las credenciales son válidas

        Raises:
            DBAuthenticationError: Si las credenciales son inválidas
            DBConnectionError: Si no se puede conectar
        """
        pass

    # =============================================================================
    # METADATA INTROSPECTION - SOLO LECTURA DE ESTRUCTURA
    # =============================================================================

    @abstractmethod
    def get_schemas(self) -> List[str]:
        """
        Lista todos los schemas/databases disponibles.

        Para PostgreSQL: schemas (public, custom_schema, etc.)
        Para MySQL: databases
        Para SQL Server: schemas (dbo, custom_schema, etc.)
        Para Oracle: schemas/users

        Returns:
            Lista de nombres de schemas

        Note:
            Solo schemas a los que el usuario tiene acceso (información de metadata)
        """
        pass

    @abstractmethod
    def get_tables(self, schema: Optional[str] = None) -> List[TableMetadata]:
        """
        Lista todas las tablas de un schema.

        IMPORTANTE: Solo lee metadata de information_schema, NO datos de tablas.

        Args:
            schema: Nombre del schema (None = schema por defecto)

        Returns:
            Lista de TableMetadata con información básica de cada tabla

        Raises:
            DBQueryExecutionError: Si falla la query
            DBPermissionError: Si el usuario no tiene permisos de lectura en information_schema
        """
        pass

    @abstractmethod
    def get_columns(self, table_name: str, schema: Optional[str] = None) -> List[ColumnMetadata]:
        """
        Lista todas las columnas de una tabla.

        IMPORTANTE: Solo lee metadata de information_schema.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema (opcional)

        Returns:
            Lista de ColumnMetadata con tipo, nullable, default, etc.

        Raises:
            DBValidationError: Si table_name contiene caracteres inválidos
            DBQueryExecutionError: Si la tabla no existe
        """
        pass

    @abstractmethod
    def get_primary_keys(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[PrimaryKeyMetadata]:
        """
        Obtiene las primary keys de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema (opcional)

        Returns:
            Lista de PrimaryKeyMetadata (normalmente 1 elemento)
        """
        pass

    @abstractmethod
    def get_foreign_keys(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[ForeignKeyMetadata]:
        """
        Obtiene las foreign keys de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema (opcional)

        Returns:
            Lista de ForeignKeyMetadata con tabla referenciada, columnas, ON DELETE, etc.
        """
        pass

    @abstractmethod
    def get_indexes(self, table_name: str, schema: Optional[str] = None) -> List[IndexMetadata]:
        """
        Obtiene los índices de una tabla.

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema (opcional)

        Returns:
            Lista de IndexMetadata con columnas, tipo, unique, etc.
        """
        pass

    @abstractmethod
    def get_table_statistics(
        self, table_name: str, schema: Optional[str] = None
    ) -> TableStatistics:
        """
        Obtiene estadísticas de una tabla (solo metadata, NO lee datos).

        IMPORTANTE: Los valores son aproximados, obtenidos de:
        - PostgreSQL: pg_stat_user_tables, pg_class
        - MySQL: information_schema.tables
        - SQL Server: sys.dm_db_partition_stats
        - Oracle: user_tables

        Args:
            table_name: Nombre de la tabla
            schema: Nombre del schema (opcional)

        Returns:
            TableStatistics con row_count (aproximado), size_bytes, etc.

        Note:
            row_count es aproximado, NO ejecuta SELECT COUNT(*) sobre datos.
        """
        pass

    # =============================================================================
    # HIGH-LEVEL OPERATIONS
    # =============================================================================

    def get_unique_constraints(
        self, table_name: str, schema: Optional[str] = None
    ) -> List[UniqueConstraintMetadata]:
        """
        Obtiene las unique constraints de una tabla.

        Implementación por defecto vacía para los dialectos que no la soportan todavía.
        """
        return []

    def get_full_schema_metadata(self, schema: Optional[str] = None) -> SchemaMetadata:
        """
        Obtiene metadata completa de un schema (tablas, columnas, constraints, índices).

        Implementación genérica tabla a tabla; los adapters pueden sobrescribirla con
        queries por schema (ver PostgreSQLAdapter). Una tabla cuyas columnas no son
        visibles (permisos) o que desaparece durante la introspección no tumba el schema
        entero: se devuelve sin columnas y se registra un aviso.

        Args:
            schema: Nombre del schema (None = schema por defecto)

        Returns:
            SchemaMetadata con toda la información del schema
        """
        schema = schema or self._get_default_schema()
        logger.info(f"Getting full schema metadata for schema '{schema}'")

        tables = self.get_tables(schema)

        primary_keys: List[PrimaryKeyMetadata] = []
        foreign_keys: List[ForeignKeyMetadata] = []
        unique_constraints: List[UniqueConstraintMetadata] = []
        indexes: List[IndexMetadata] = []

        for table in tables:
            try:
                table.columns = self.get_columns(table.name, schema)
            except DBMetadataNotFoundError:
                logger.warning(f"No visible columns for table '{schema}.{table.name}'")
                table.columns = []

            pks = self.get_primary_keys(table.name, schema)
            fks = self.get_foreign_keys(table.name, schema)
            # No todos los dialectos marcan PK/FK en get_columns()
            table.columns = self._apply_key_flags(table.columns, pks, fks)

            primary_keys.extend(pks)
            foreign_keys.extend(fks)
            unique_constraints.extend(self.get_unique_constraints(table.name, schema))
            indexes.extend(self.get_indexes(table.name, schema))

        return self._build_schema_metadata(
            schema, tables, primary_keys, foreign_keys, unique_constraints, indexes
        )

    @staticmethod
    def _build_schema_metadata(
        schema: str,
        tables: List[TableMetadata],
        primary_keys: List[PrimaryKeyMetadata],
        foreign_keys: List[ForeignKeyMetadata],
        unique_constraints: List[UniqueConstraintMetadata],
        indexes: List[IndexMetadata],
    ) -> SchemaMetadata:
        """Construye el SchemaMetadata y registra un resumen."""
        logger.info(
            f"Schema '{schema}' metadata: "
            f"{len(tables)} tables, "
            f"{sum(len(t.columns) for t in tables)} columns, "
            f"{len(primary_keys)} primary keys, "
            f"{len(foreign_keys)} foreign keys, "
            f"{len(indexes)} indexes"
        )
        return SchemaMetadata(
            name=schema,
            tables=tables,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            unique_constraints=unique_constraints,
            indexes=indexes,
        )

    @staticmethod
    def _apply_key_flags(
        columns: List[ColumnMetadata],
        primary_keys: List[PrimaryKeyMetadata],
        foreign_keys: List[ForeignKeyMetadata],
    ) -> List[ColumnMetadata]:
        """
        Marca las columnas que forman parte de una PK o FK.

        Returns:
            Nueva lista; las columnas sin cambios se reutilizan tal cual.
        """
        pk_columns = {name for pk in primary_keys for name in pk.columns}
        fk_columns = {name for fk in foreign_keys for name in fk.columns}

        updated_columns = []
        for col in columns:
            is_pk = col.name in pk_columns
            is_fk = col.name in fk_columns
            if is_pk or is_fk:
                col_dict = col.model_dump()
                if is_pk:
                    col_dict["is_primary_key"] = True
                if is_fk:
                    col_dict["is_foreign_key"] = True
                updated_columns.append(ColumnMetadata(**col_dict))
            else:
                updated_columns.append(col)
        return updated_columns

    @abstractmethod
    def _get_default_schema(self) -> str:
        """
        Retorna el nombre del schema por defecto para este dialecto.

        PostgreSQL: 'public'
        MySQL: nombre de la database
        SQL Server: 'dbo'
        Oracle: nombre del usuario
        """
        pass

    # =============================================================================
    # CONTEXT MANAGER SUPPORT
    # =============================================================================

    def __enter__(self):
        """Context manager: conecta al entrar"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: desconecta al salir (siempre, incluso si hay errores)"""
        try:
            self.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
        return False  # No suprimir excepciones

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    def _sanitize_for_logging(self, message: str) -> str:
        """
        Remueve información sensible antes de loggear.

        Args:
            message: Mensaje a sanitizar

        Returns:
            Mensaje sin información sensible
        """
        # Remover passwords
        sanitized = message
        if "password" in message.lower():
            sanitized = re.sub(
                r"password[=:]\s*\S+", "password=***", sanitized, flags=re.IGNORECASE
            )

        return sanitized

    def __repr__(self) -> str:
        """Representación string del adapter"""
        return (
            f"<{self.__class__.__name__} "
            f"dialect={self.dialect} "
            f"host={self.connection_config.get('host')} "
            f"database={self.connection_config.get('database')} "
            f"connected={self.is_connected}>"
        )
