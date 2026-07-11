"""
Redis Client Singleton
Maneja la conexión a Redis con connection pooling, retries y health checks.
"""

import logging
import os
import time
from typing import Optional

from redis import ConnectionPool, Redis, RedisError  # type: ignore[import-untyped]
from redis.backoff import ExponentialBackoff  # type: ignore[import-untyped]
from redis.connection import Connection, SSLConnection  # type: ignore[import-untyped]
from redis.retry import Retry  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Singleton para manejar la conexión a Redis.

    Características:
    - Connection pooling automático
    - Retry con exponential backoff
    - Soporte para Redis URL o parámetros individuales
    - SSL/TLS para producción
    - Health checks
    """

    _instance: Optional["RedisClient"] = None
    _redis: Optional[Redis] = None
    _pool: Optional[ConnectionPool] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Inicializar el cliente Redis (solo una vez)"""
        if self._redis is None:
            self._initialize_redis()

    def _initialize_redis(self) -> None:
        """Inicializa la conexión a Redis con retry logic"""
        redis_url = os.getenv("REDIS_URL")

        if redis_url:
            # Usar REDIS_URL (formato: redis://[:password@]host:port/db)
            logger.info(f"Conectando a Redis usando REDIS_URL")
            self._redis = self._create_redis_from_url(redis_url)
        else:
            # Usar parámetros individuales
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            password = os.getenv("REDIS_PASSWORD", "")
            db = int(os.getenv("REDIS_DB", "0"))
            use_ssl = os.getenv("REDIS_SSL", "false").lower() == "true"

            logger.info(f"Conectando a Redis en {host}:{port} (SSL: {use_ssl})")
            self._redis = self._create_redis_from_params(host, port, password, db, use_ssl)

        # Verificar conexión
        self._verify_connection()

    def _create_redis_from_url(self, redis_url: str) -> Redis:
        """Crea cliente Redis desde URL"""
        # Determinar si usar SSL
        use_ssl = redis_url.startswith("rediss://")
        connection_class = SSLConnection if use_ssl else Connection

        # Crear pool de conexiones
        self._pool = ConnectionPool.from_url(
            redis_url,
            decode_responses=True,  # Decodificar bytes a strings automáticamente
            max_connections=20,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=True,
            retry_on_timeout=True,
            connection_class=connection_class,
            retry=Retry(ExponentialBackoff(base=0.5, cap=3), retries=3),
        )

        return Redis(connection_pool=self._pool)

    def _create_redis_from_params(
        self, host: str, port: int, password: str, db: int, use_ssl: bool
    ) -> Redis:
        """Crea cliente Redis desde parámetros individuales"""
        connection_class = SSLConnection if use_ssl else Connection

        # Crear pool de conexiones
        self._pool = ConnectionPool(
            host=host,
            port=port,
            password=password if password else None,
            db=db,
            decode_responses=True,
            max_connections=20,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=True,
            retry_on_timeout=True,
            connection_class=connection_class,
            retry=Retry(ExponentialBackoff(base=0.5, cap=3), retries=3),
        )

        return Redis(connection_pool=self._pool)

    def _verify_connection(self, max_retries: int = 5, retry_delay: int = 2) -> None:
        """
        Verifica la conexión a Redis con retries.

        Args:
            max_retries: Número máximo de intentos
            retry_delay: Delay entre intentos (segundos)

        Raises:
            RedisError: Si no se puede conectar después de max_retries
        """
        for attempt in range(1, max_retries + 1):
            try:
                assert self._redis is not None
                self._redis.ping()
                logger.info(f"✓ Conexión a Redis establecida exitosamente")
                return
            except RedisError as e:
                if attempt == max_retries:
                    logger.error(
                        f"✗ No se pudo conectar a Redis después de {max_retries} intentos: {e}"
                    )
                    raise
                logger.warning(
                    f"Intento {attempt}/{max_retries} falló. Reintentando en {retry_delay}s..."
                )
                time.sleep(retry_delay)

    def get_client(self) -> Redis:
        """
        Obtiene el cliente Redis.

        Returns:
            Redis: Cliente Redis conectado

        Raises:
            RedisError: Si el cliente no está inicializado
        """
        if self._redis is None:
            raise RedisError("Redis client no inicializado")
        return self._redis

    def health_check(self) -> bool:
        """
        Verifica si Redis está disponible.

        Returns:
            bool: True si Redis responde, False en caso contrario
        """
        try:
            if self._redis is None:
                return False
            return bool(self._redis.ping())
        except RedisError as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    def close(self) -> None:
        """Cierra todas las conexiones del pool"""
        if self._pool:
            self._pool.disconnect()
            logger.info("Redis connection pool cerrado")

    def reset(self) -> None:
        """
        Resetea el singleton (útil para testing).
        ¡NO usar en producción!
        """
        if self._pool:
            self._pool.disconnect()
        RedisClient._instance = None
        RedisClient._redis = None
        RedisClient._pool = None
        logger.warning("Redis client reseteado")


# Singleton global
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> Redis:
    """
    Obtiene el cliente Redis (lazy initialization).

    Returns:
        Redis: Cliente Redis conectado

    Usage:
        ```python
        redis = get_redis_client()
        redis.set("key", "value")
        ```
    """
    global _redis_client

    if _redis_client is None:
        _redis_client = RedisClient()

    return _redis_client.get_client()


def redis_health_check() -> bool:
    """
    Verifica el estado de Redis.

    Returns:
        bool: True si Redis está disponible, False en caso contrario
    """
    try:
        redis = get_redis_client()
        return bool(redis.ping())
    except Exception as e:
        logger.error(f"Redis health check error: {e}")
        return False
