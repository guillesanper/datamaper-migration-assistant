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
from pydantic import ValidationError

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
    DBHostNotAllowedError,
    DBTimeoutError,
    DBTLSError,
    MySQLAdapter,
    OracleAdapter,
    PostgreSQLAdapter,
    SQLServerAdapter,
    validate_connection_host,
)
from app.utils.encryption import DecryptionError, EncryptionManager
from app.utils.master_key import parse_master_key

logger = logging.getLogger(__name__)


def _decode_hash(data: Dict[Any, Any]) -> Dict[str, str]:
    """
    Normaliza un HGETALL a dict de str.

    El cliente compartido (app.utils.redis_client) usa decode_responses=True y devuelve
    str; un cliente sin decodificar devuelve bytes. El servicio acepta ambos.
    """
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in data.items()
    }


class DBConnectionServiceError(Exception):
    """Base exception for DBConnectionService"""

    pass


class SessionNotFoundError(DBConnectionServiceError):
    """Session does not exist or has expired"""

    pass


class SessionProjectMismatchError(SessionNotFoundError):
    """
    La sesión está atada a otro proyecto.

    Hereda de SessionNotFoundError: para quien la usa desde otro proyecto no existe (404),
    sin revelar que la sesión existe.
    """

    pass


class SessionExpiredError(DBConnectionServiceError):
    """Session has expired"""

    pass


class SessionRequiresReconnectError(SessionExpiredError):
    """
    La sesión es anterior a la política TLS y se ha invalidado.

    Es una sesión expirada para quien ya captura SessionExpiredError: el usuario debe volver
    a conectar, esta vez con verificación TLS (o confirmando el opt-out).
    """

    pass


# Mensaje fijo para fallos TLS: el texto del driver puede incluir rutas temporales y detalles
# de red, así que se registra en el log y no se devuelve al cliente
TLS_ERROR_MESSAGE = (
    "TLS verification failed: the server certificate could not be verified (untrusted CA, "
    "hostname mismatch, expired certificate or server without TLS). Check the CA and hostname, "
    "or disable verification for this connection (not recommended)"
)


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
        # 32 bytes para AES-256 (base64 estricto); una clave inválida es un error, no se
        # "arregla" en silencio
        self.encryption_key = parse_master_key(encryption_key)

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

    def _get_adapter(self, config: DBConnectionConfig, long_running: bool = False):
        """
        Obtiene el adapter apropiado según el dialecto.

        Args:
            config: Configuración de conexión
            long_running: Si True, no se limita el tiempo de espera de respuesta de las
                queries (ejecución de migraciones). Por defecto las lecturas usan el
                mismo timeout que la conexión (introspección de metadata).

        Returns:
            Instancia del adapter (PostgreSQLAdapter, MySQLAdapter, etc.)

        Raises:
            DBConnectionServiceError: Si el dialecto no está soportado
            DBHostNotAllowedError: Si el host resuelve a una red interna no permitida
        """
        # Política de red anti-SSRF: se revalida en cada conexión, no solo al crear
        # la sesión, y el adapter conecta a la IP validada (pinning contra DNS rebinding)
        pinned_address = validate_connection_host(config.host, config.port)

        adapter_config = config.to_adapter_config()
        if long_running:
            adapter_config["read_timeout"] = None
        if pinned_address:
            adapter_config["hostaddr"] = pinned_address

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

        def failure(error_type: str, message: str, exc: Exception) -> DBConnectionTestResult:
            # El detalle del driver (IPs, puertos, versiones, mensajes del servidor) solo
            # va al log: devolverlo convertiría el endpoint en un oráculo de la red
            logger.warning(f"Connection test failed ({error_type}): {str(exc)}")
            return DBConnectionTestResult(
                success=False,
                dialect=config.dialect,
                host=config.host,
                database=config.database,
                error_message=message,
                error_type=error_type,
                tls_verified=config.tls_verify,
            )

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
                tls_verified=config.tls_verify,
            )

        except DBHostNotAllowedError as e:
            return failure("host_not_allowed", str(e), e)

        except DBAuthenticationError as e:
            return failure("authentication", "Authentication failed: check user and password", e)

        except DBTimeoutError as e:
            return failure("timeout", "Connection timed out", e)

        except DBTLSError as e:
            # Antes que DBConnectionError, de la que hereda
            return failure("tls", TLS_ERROR_MESSAGE, e)

        except DBConnectionError as e:
            return failure(
                "connection",
                "Could not connect to the database: check host, port and database name",
                e,
            )

        except Exception as e:
            logger.exception("Unexpected error testing connection")
            return failure("unknown", "Unexpected error testing connection", e)

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

        # La política de red se aplica aunque no se pruebe la conexión
        try:
            validate_connection_host(config.host, config.port)
        except DBHostNotAllowedError as e:
            raise DBConnectionServiceError(str(e))

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
            tls_verified=config.tls_verify,
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
        if not config.tls_verify:
            logger.warning(
                f"TLS verification disabled for connection: user_id={user_id}, "
                f"project_id={project_id}, session_id={session.session_id}, "
                f"dialect={config.dialect}, host={config.host}"
            )

        return DBConnectionSessionResponse(
            session_id=session.session_id,
            dialect=session.dialect,
            host=session.host,
            database=session.database,
            expires_at=session.expires_at,
            tls_verified=session.tls_verified,
        )

    def _parse_session(self, redis_key: Any, data: Dict[str, str]) -> DBConnectionSession:
        """
        Deserializa una sesión de Redis, invalidando las anteriores a la política TLS.

        Una sesión sin tls_verified se creó antes de que existiera la verificación. En vez de
        heredar un estado inseguro (o fallar luego con un error TLS poco claro) se borra y se
        pide al usuario que reconecte.

        Raises:
            SessionRequiresReconnectError: Si la sesión no lleva el flag tls_verified
            DBConnectionServiceError: Si el flag existe pero no es legible
        """
        if "tls_verified" not in data:
            self.redis.delete(redis_key)
            logger.info(f"Session without TLS policy invalidated: key={redis_key!r}")
            raise SessionRequiresReconnectError(
                f"Session requires reconnect: {data.get('session_id', '?')}"
            )
        try:
            return DBConnectionSession.from_redis_dict(data)
        except ValueError as e:
            logger.error(f"Unreadable session {redis_key!r}: {str(e)}")
            raise DBConnectionServiceError("Corrupted session data: unreadable TLS flag")

    def get_session(
        self, user_id: str, session_id: str, project_id: Optional[str] = None
    ) -> DBConnectionSession:
        """
        Recupera una sesión activa.

        Args:
            user_id: ID del usuario propietario
            session_id: ID de la sesión
            project_id: Proyecto desde el que se usa. Una sesión atada a otro proyecto se
                rechaza; las sesiones sin proyecto valen para cualquiera del usuario

        Returns:
            DBConnectionSession con datos de la sesión

        Raises:
            SessionNotFoundError: Si la sesión no existe
            SessionProjectMismatchError: Si la sesión es de otro proyecto
            SessionExpiredError: Si la sesión ha expirado
        """
        redis_key = self._get_redis_key(user_id, session_id)

        # Obtener de Redis
        data = self.redis.hgetall(redis_key)

        if not data:
            raise SessionNotFoundError(
                f"Session not found: user_id={user_id}, session_id={session_id}"
            )

        session = self._parse_session(redis_key, _decode_hash(data))

        # Verificar expiración
        if session.is_expired():
            # Eliminar sesión expirada
            self.redis.delete(redis_key)
            raise SessionExpiredError(f"Session expired: {session_id}")

        if (
            project_id is not None
            and session.project_id is not None
            and str(session.project_id) != str(project_id)
        ):
            raise SessionProjectMismatchError(
                f"Session not found for project: project_id={project_id}, session_id={session_id}"
            )

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

            # Crear config (el validador del modelo exige la confirmación de hostname si
            # tls_verify es false, así que una sesión sin verificar no se rehidrata sin ella)
            config = DBConnectionConfig(
                dialect=session.dialect, **credentials_dict  # type: ignore[arg-type]
            )
            # El flag en claro es solo metadata para listar: el blob cifrado manda
            if config.tls_verify != session.tls_verified:
                logger.error(f"TLS policy mismatch in session {session.session_id}")
                raise DBConnectionServiceError("Corrupted session data: TLS policy mismatch")
            return config

        except DecryptionError as e:
            logger.error(f"Failed to decrypt session credentials: {str(e)}")
            raise

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse credentials JSON: {str(e)}")
            raise DBConnectionServiceError(f"Corrupted session data: {str(e)}")

        except ValidationError as e:
            logger.error(f"Session credentials failed validation: {len(e.errors())} error(s)")
            raise DBConnectionServiceError("Corrupted session data: invalid configuration")

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
            ValueError: Si ttl_hours no está entre 1 y el máximo
        """
        # Validar TTL: con 0 o negativo EXPIRE borraba la sesión y el HSET siguiente la
        # recreaba solo con expires_at y sin TTL (clave huérfana que nunca caducaba)
        if ttl_hours < 1:
            raise ValueError("TTL must be at least 1 hour")
        if ttl_hours > self.MAX_TTL_HOURS:
            raise ValueError(f"TTL cannot exceed {self.MAX_TTL_HOURS} hours")

        # Verificar que existe
        self.get_session(user_id, session_id)

        # Extender TTL
        redis_key = self._get_redis_key(user_id, session_id)
        ttl_seconds = ttl_hours * 3600
        new_expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        # EXPIRE devuelve False si la clave ya no existe (caducó entre medias): no recrearla
        if not self.redis.expire(redis_key, ttl_seconds):
            raise SessionNotFoundError(
                f"Session not found: user_id={user_id}, session_id={session_id}"
            )
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
        sessions = []
        # scan_iter en lugar de KEYS: KEYS recorre todo Redis bloqueándolo
        for key in self.redis.scan_iter(match=pattern):
            data = self.redis.hgetall(key)
            if data:
                try:
                    session = self._parse_session(key, _decode_hash(data))
                    if not session.is_expired():
                        sessions.append(session)
                    else:
                        # Eliminar sesión expirada
                        self.redis.delete(key)
                except SessionRequiresReconnectError:
                    continue  # _parse_session ya la ha invalidado
                except Exception as e:
                    logger.warning(f"Failed to parse session {key}: {str(e)}")
                    continue

        return sessions
