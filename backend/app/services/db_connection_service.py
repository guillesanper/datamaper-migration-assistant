"""
Database Connection Service

Gestiona sesiones de conexión a bases de datos externas con:
- Cifrado de credenciales con AES-256-GCM
- Almacenamiento temporal en Redis con TTL
- Validación de credenciales antes de crear sesión
- Soporte para PostgreSQL, MySQL, SQL Server, Oracle

SEGURIDAD CRÍTICA:
- Las credenciales NUNCA se almacenan en texto plano
- Cada sesión tiene un UUID único
- TTL máximo de 24 horas
- Las sesiones se invalidan automáticamente al expirar
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import redis  # type: ignore[import-untyped]

from app.models.db_connection import (
    DBConnectionConfig,
    DBConnectionRequest,
    DBConnectionSession,
    DBConnectionSessionResponse,
    DBConnectionTestResult,
)
from app.utils.db_adapters import (
    DBAuthenticationError,
    DBConnectionError,
    DBTimeoutError,
    MySQLAdapter,
    OracleAdapter,
    PostgreSQLAdapter,
    SQLServerAdapter,
)
from app.utils.encryption import DecryptionError, EncryptionManager

logger = logging.getLogger(__name__)


class DBConnectionServiceError(Exception):
    """Base exception for DBConnectionService"""

    pass


class SessionNotFoundError(DBConnectionServiceError):
    """Session does not exist or has expired"""

    pass


class SessionExpiredError(DBConnectionServiceError):
    """Session has expired"""

    pass


class DBConnectionService:
    """
    Servicio de gestión de sesiones de conexión a bases de datos externas.

    Responsabilidades:
    - Validar credenciales de conexión
    - Cifrar y almacenar credenciales en Redis
    - Recuperar y descifrar credenciales
    - Gestionar ciclo de vida de sesiones (TTL, refresh, delete)

    Usage:
        service = DBConnectionService(redis_client, encryption_key)

        # Test connection
        result = service.test_connection(config)

        # Create session
        session = service.create_session(user_id, config, ttl_hours=3)

        # Get session
        session = service.get_session(user_id, session_id)

        # Delete session
        service.delete_session(user_id, session_id)
    """

    # Redis key prefix para sesiones
    REDIS_KEY_PREFIX = "db_connection_session"

    # TTL por defecto: 3 horas
    DEFAULT_TTL_HOURS = 3

    # TTL máximo: 24 horas
    MAX_TTL_HOURS = 24

    def __init__(self, redis_client: redis.Redis, encryption_key: str):
        """
        Inicializa el servicio de conexiones.

        Args:
            redis_client: Cliente Redis configurado
            encryption_key: Master key para cifrado de credenciales (32 bytes, base64)
        """
        self.redis = redis_client
        self.encryption_manager = EncryptionManager()
        # La encryption_key debe ser 32 bytes para AES-256
        # Si es string base64, decodificar; si no, asumir que ya son bytes
        if isinstance(encryption_key, str):
            import base64

            try:
                self.encryption_key = base64.b64decode(encryption_key)
            except:
                # Si no es base64, usar los primeros 32 bytes del UTF-8
                key_bytes = encryption_key.encode("utf-8")
                # Pad o truncate a 32 bytes
                self.encryption_key = key_bytes[:32].ljust(32, b"\x00")
        else:
            self.encryption_key = encryption_key

        logger.info("DBConnectionService initialized")

    def _get_redis_key(self, user_id: str, session_id: str) -> str:
        """
        Genera clave Redis para una sesión.

        Args:
            user_id: ID del usuario
            session_id: ID de la sesión

        Returns:
            Clave Redis: "db_connection_session:{user_id}:{session_id}"
        """
        return f"{self.REDIS_KEY_PREFIX}:{user_id}:{session_id}"

    def _get_adapter(self, config: DBConnectionConfig):
        """
        Obtiene el adapter apropiado según el dialecto.

        Args:
            config: Configuración de conexión

        Returns:
            Instancia del adapter (PostgreSQLAdapter, MySQLAdapter, etc.)

        Raises:
            DBConnectionServiceError: Si el dialecto no está soportado
        """
        adapter_config = config.to_adapter_config()

        if config.dialect == "postgresql":
            return PostgreSQLAdapter(adapter_config)
        elif config.dialect == "mysql":
            return MySQLAdapter(adapter_config)
        elif config.dialect == "sqlserver":
            return SQLServerAdapter(adapter_config)
        elif config.dialect == "oracle":
            return OracleAdapter(adapter_config)
        else:
            raise DBConnectionServiceError(f"Unsupported dialect: {config.dialect}")

    def test_connection(self, config: DBConnectionConfig) -> DBConnectionTestResult:
        """
        Valida credenciales de conexión sin crear sesión.

        Args:
            config: Configuración de conexión a validar

        Returns:
            DBConnectionTestResult con resultado del test
        """
        try:
            adapter = self._get_adapter(config)

            # Test connection (no mantiene conexión abierta)
            adapter.test_connection()

            logger.info(
                f"Connection test successful: {config.dialect}@{config.host}/{config.database}"
            )

            return DBConnectionTestResult(
                success=True,
                dialect=config.dialect,
                host=config.host,
                database=config.database,
            )

        except DBAuthenticationError as e:
            logger.warning(f"Connection test failed (auth): {str(e)}")
            return DBConnectionTestResult(
                success=False,
                dialect=config.dialect,
                host=config.host,
                database=config.database,
                error_message=str(e),
                error_type="authentication",
            )

        except DBTimeoutError as e:
            logger.warning(f"Connection test failed (timeout): {str(e)}")
            return DBConnectionTestResult(
                success=False,
                dialect=config.dialect,
                host=config.host,
                database=config.database,
                error_message=str(e),
                error_type="timeout",
            )

        except DBConnectionError as e:
            logger.warning(f"Connection test failed (connection): {str(e)}")
            return DBConnectionTestResult(
                success=False,
                dialect=config.dialect,
                host=config.host,
                database=config.database,
                error_message=str(e),
                error_type="connection",
            )

        except Exception as e:
            logger.error(f"Connection test failed (unexpected): {str(e)}")
            return DBConnectionTestResult(
                success=False,
                dialect=config.dialect,
                host=config.host,
                database=config.database,
                error_message=f"Unexpected error: {str(e)}",
                error_type="unknown",
            )

    def create_session(
        self,
        user_id: str,
        config: DBConnectionConfig,
        project_id: Optional[str] = None,
        ttl_hours: int = DEFAULT_TTL_HOURS,
        test_connection: bool = True,
    ) -> DBConnectionSessionResponse:
        """
        Crea una nueva sesión de conexión.

        Args:
            user_id: ID del usuario propietario
            config: Configuración de conexión
            project_id: ID del proyecto asociado (opcional)
            ttl_hours: Tiempo de vida en horas (default: 3, max: 24)
            test_connection: Validar credenciales antes de crear sesión

        Returns:
            DBConnectionSessionResponse con metadatos de la sesión

        Raises:
            DBConnectionServiceError: Si el test de conexión falla
            ValueError: Si ttl_hours excede el máximo
        """
        # Validar TTL
        if ttl_hours > self.MAX_TTL_HOURS:
            raise ValueError(f"TTL cannot exceed {self.MAX_TTL_HOURS} hours")

        # Test connection si está habilitado
        if test_connection:
            test_result = self.test_connection(config)
            if not test_result.success:
                raise DBConnectionServiceError(
                    f"Connection test failed: {test_result.error_message}"
                )

        # Cifrar credenciales
        credentials_json = json.dumps(config.to_adapter_config())

        # Usar EncryptionManager para cifrar
        ciphertext, nonce = self.encryption_manager.encrypt_field(
            credentials_json, self.encryption_key
        )

        # Combinar ciphertext y nonce en un solo string base64
        # Formato: base64(nonce + ciphertext)
        combined = nonce + ciphertext
        encrypted_credentials = self.encryption_manager.encode_for_storage(combined)

        # Crear sesión
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=ttl_hours)

        session = DBConnectionSession(
            user_id=user_id,
            project_id=project_id,
            dialect=config.dialect,
            host=config.host,
            database=config.database,
            encrypted_credentials=encrypted_credentials,
            created_at=now,
            expires_at=expires_at,
            last_used_at=now,
        )

        # Guardar en Redis
        redis_key = self._get_redis_key(user_id, session.session_id)
        ttl_seconds = ttl_hours * 3600

        self.redis.hset(redis_key, mapping=session.to_redis_dict())  # type: ignore[arg-type]
        self.redis.expire(redis_key, ttl_seconds)

        logger.info(
            f"Session created: user_id={user_id}, session_id={session.session_id}, "
            f"dialect={config.dialect}, ttl={ttl_hours}h"
        )

        return DBConnectionSessionResponse(
            session_id=session.session_id,
            dialect=session.dialect,
            host=session.host,
            database=session.database,
            expires_at=session.expires_at,
        )

    def get_session(self, user_id: str, session_id: str) -> DBConnectionSession:
        """
        Recupera una sesión activa.

        Args:
            user_id: ID del usuario propietario
            session_id: ID de la sesión

        Returns:
            DBConnectionSession con datos de la sesión

        Raises:
            SessionNotFoundError: Si la sesión no existe
            SessionExpiredError: Si la sesión ha expirado
        """
        redis_key = self._get_redis_key(user_id, session_id)

        # Obtener de Redis
        data = self.redis.hgetall(redis_key)

        if not data:
            raise SessionNotFoundError(
                f"Session not found: user_id={user_id}, session_id={session_id}"
            )

        # Deserializar (Redis devuelve bytes)
        data_str = {k.decode(): v.decode() for k, v in data.items()}  # type: ignore[union-attr]
        session = DBConnectionSession.from_redis_dict(data_str)

        # Verificar expiración
        if session.is_expired():
            # Eliminar sesión expirada
            self.redis.delete(redis_key)
            raise SessionExpiredError(f"Session expired: {session_id}")

        # Actualizar last_used_at
        session.last_used_at = datetime.utcnow()
        self.redis.hset(redis_key, "last_used_at", session.last_used_at.isoformat())

        return session

    def get_decrypted_config(self, session: DBConnectionSession) -> DBConnectionConfig:
        """
        Descifra y retorna la configuración de conexión.

        Args:
            session: Sesión con credenciales cifradas

        Returns:
            DBConnectionConfig con credenciales descifradas

        Raises:
            DecryptionError: Si no se puede descifrar
        """
        try:
            # Descifrar credenciales
            # Decodificar de base64
            combined = self.encryption_manager.decode_from_storage(session.encrypted_credentials)

            # Separar nonce (primeros 12 bytes) y ciphertext (resto)
            nonce = combined[: self.encryption_manager.AES_NONCE_LENGTH]
            ciphertext = combined[self.encryption_manager.AES_NONCE_LENGTH :]

            # Descifrar
            credentials_json = self.encryption_manager.decrypt_field(
                ciphertext, nonce, self.encryption_key
            )

            # Parsear JSON
            credentials_dict = json.loads(credentials_json)

            # Crear config
            return DBConnectionConfig(
                dialect=session.dialect, **credentials_dict  # type: ignore[arg-type]
            )

        except DecryptionError as e:
            logger.error(f"Failed to decrypt session credentials: {str(e)}")
            raise

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse credentials JSON: {str(e)}")
            raise DBConnectionServiceError(f"Corrupted session data: {str(e)}")

    def delete_session(self, user_id: str, session_id: str) -> bool:
        """
        Elimina una sesión.

        Args:
            user_id: ID del usuario propietario
            session_id: ID de la sesión

        Returns:
            True si se eliminó, False si no existía
        """
        redis_key = self._get_redis_key(user_id, session_id)
        deleted = self.redis.delete(redis_key)

        if deleted:
            logger.info(f"Session deleted: user_id={user_id}, session_id={session_id}")
        else:
            logger.warning(
                f"Session not found for deletion: user_id={user_id}, session_id={session_id}"
            )

        return bool(deleted > 0)  # type: ignore[operator]

    def refresh_session(
        self, user_id: str, session_id: str, ttl_hours: int = DEFAULT_TTL_HOURS
    ) -> datetime:
        """
        Extiende el TTL de una sesión.

        Args:
            user_id: ID del usuario propietario
            session_id: ID de la sesión
            ttl_hours: Nuevo TTL en horas (default: 3, max: 24)

        Returns:
            Nueva fecha de expiración

        Raises:
            SessionNotFoundError: Si la sesión no existe
            ValueError: Si ttl_hours excede el máximo
        """
        # Validar TTL
        if ttl_hours > self.MAX_TTL_HOURS:
            raise ValueError(f"TTL cannot exceed {self.MAX_TTL_HOURS} hours")

        # Verificar que existe
        session = self.get_session(user_id, session_id)

        # Extender TTL
        redis_key = self._get_redis_key(user_id, session_id)
        ttl_seconds = ttl_hours * 3600
        new_expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        self.redis.expire(redis_key, ttl_seconds)
        self.redis.hset(redis_key, "expires_at", new_expires_at.isoformat())

        logger.info(
            f"Session refreshed: user_id={user_id}, session_id={session_id}, new_ttl={ttl_hours}h"
        )

        return new_expires_at

    def list_user_sessions(self, user_id: str) -> list[DBConnectionSession]:
        """
        Lista todas las sesiones activas de un usuario.

        Args:
            user_id: ID del usuario

        Returns:
            Lista de DBConnectionSession
        """
        pattern = f"{self.REDIS_KEY_PREFIX}:{user_id}:*"
        keys = self.redis.keys(pattern)

        sessions = []
        for key in keys:  # type: ignore[union-attr]
            data = self.redis.hgetall(key)
            if data:
                data_str = {k.decode(): v.decode() for k, v in data.items()}  # type: ignore[union-attr]
                try:
                    session = DBConnectionSession.from_redis_dict(data_str)
                    if not session.is_expired():
                        sessions.append(session)
                    else:
                        # Eliminar sesión expirada
                        self.redis.delete(key)
                except Exception as e:
                    logger.warning(f"Failed to parse session {key}: {str(e)}")
                    continue

        return sessions
