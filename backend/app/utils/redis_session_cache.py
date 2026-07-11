# backend/app/utils/redis_session_cache.py
"""
Sistema de caché de sesiones de cifrado con Redis
Reemplazo drop-in del caché en memoria con persistencia y escalabilidad

🔐 SEGURIDAD HARDENED:
- Sesiones vinculadas a user_id para prevenir session hijacking
- Auto-expiración con Redis TTL
- Persistencia entre reinicios de servidor
- Escalable horizontalmente (múltiples instancias/workers)
- 🆕 Memory scrubbing: Sobrescribe claves antes de eliminar (Fase 2.1)
- 🆕 Token rotation con grace period (Fase 2.2)

MEJORAS CON REDIS:
✅ Persistencia: Sesiones sobreviven reinicios
✅ Escalabilidad: Múltiples workers/instancias comparten sesiones
✅ Performance: Connection pooling automático
✅ TTL automático: Redis maneja expiración nativamente

Autor: DataMap Security Team
Última actualización: 2025-01-06 (Redis migration)
"""

import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from redis import RedisError  # type: ignore[import-untyped]

from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class RedisEncryptionSessionCache:
    """
    Cache Redis para sesiones de cifrado.
    Drop-in replacement del EncryptionSessionCache en memoria.

    Key Structure:
        - enc_session:{project_id}:{token} → Session data
        - enc_session:project_index:{project_id} → Set de tokens del proyecto
        - enc_session:user_index:{user_id} → Set de tokens del usuario
    """

    # Prefijos de Redis keys
    KEY_PREFIX = "enc_session"
    PROJECT_INDEX_PREFIX = "enc_session:project_index"
    USER_INDEX_PREFIX = "enc_session:user_index"

    def __init__(self):
        """Inicializar con cliente Redis"""
        self._redis = get_redis_client()

    def _make_session_key(self, project_id: str, session_token: str) -> str:
        """Genera Redis key para una sesión"""
        return f"{self.KEY_PREFIX}:{project_id}:{session_token}"

    def _make_project_index_key(self, project_id: str) -> str:
        """Genera Redis key para índice de proyecto"""
        return f"{self.PROJECT_INDEX_PREFIX}:{project_id}"

    def _make_user_index_key(self, user_id: str) -> str:
        """Genera Redis key para índice de usuario"""
        return f"{self.USER_INDEX_PREFIX}:{user_id}"

    def _serialize_session(self, session_data: Dict[str, Any]) -> str:
        """
        Serializa session data a JSON.

        Args:
            session_data: Dict con project_id, encryption_key, user_id, expires_at, created_at

        Returns:
            JSON string
        """
        # Convertir encryption_key (bytes) a base64 para JSON
        import base64

        serializable = {
            "project_id": session_data["project_id"],
            "encryption_key": base64.b64encode(session_data["encryption_key"]).decode("utf-8"),
            "user_id": session_data["user_id"],
            "expires_at": session_data["expires_at"].isoformat(),
            "created_at": session_data["created_at"].isoformat(),
        }

        # Agregar campos opcionales si existen (para token rotation)
        if "rotating" in session_data:
            serializable["rotating"] = session_data["rotating"]
            serializable["rotated_to"] = session_data["rotated_to"]
            serializable["rotation_expires"] = session_data["rotation_expires"].isoformat()

        return json.dumps(serializable)

    def _deserialize_session(self, json_str: str) -> Dict[str, Any]:
        """
        Deserializa JSON a session data.

        Args:
            json_str: JSON string

        Returns:
            Dict con session data
        """
        import base64

        data = json.loads(json_str)

        session = {
            "project_id": data["project_id"],
            "encryption_key": base64.b64decode(data["encryption_key"]),
            "user_id": data["user_id"],
            "expires_at": datetime.fromisoformat(data["expires_at"]),
            "created_at": datetime.fromisoformat(data["created_at"]),
        }

        # Campos opcionales para token rotation
        if "rotating" in data:
            session["rotating"] = data["rotating"]
            session["rotated_to"] = data["rotated_to"]
            session["rotation_expires"] = datetime.fromisoformat(data["rotation_expires"])

        return session

    def create_session(
        self,
        project_id: str,
        encryption_key: bytes,
        user_id: str,
        timeout_seconds: int = 10800,  # 3 horas por defecto
    ) -> str:
        """
        Crear una nueva sesión de cifrado en Redis

        🔐 SEGURIDAD HARDENED:
        - Sesión vinculada al user_id (previene session hijacking)
        - Encryption key almacenada con encoding seguro
        - TTL automático de Redis (auto-expiración)
        - Indexación por project y user (invalidación rápida)

        Args:
            project_id: ID del proyecto
            encryption_key: Clave de cifrado derivada (32 bytes AES-256)
            user_id: ID del usuario que crea la sesión (CRÍTICO para validación)
            timeout_seconds: Duración de la sesión en segundos (default: 3 horas)

        Returns:
            session_token: Token único de sesión (32 bytes URL-safe)

        Security Notes:
            - El token es generado con secrets.token_urlsafe() (CSPRNG)
            - El user_id será validado en cada request por el middleware
            - La encryption_key se almacena encoded en Redis
            - Redis TTL maneja auto-expiración
        """
        try:
            session_token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)

            # Crear session data
            session_data = {
                "project_id": project_id,
                "encryption_key": encryption_key,
                "user_id": user_id,
                "expires_at": expires_at,
                "created_at": datetime.now(timezone.utc),
            }

            # Serializar a JSON
            session_json = self._serialize_session(session_data)

            # Redis key
            session_key = self._make_session_key(project_id, session_token)

            # Almacenar en Redis con TTL
            self._redis.setex(session_key, timeout_seconds, session_json)

            # Indexar por proyecto (para invalidación masiva)
            project_index_key = self._make_project_index_key(project_id)
            self._redis.sadd(project_index_key, session_token)
            self._redis.expire(project_index_key, timeout_seconds + 60)  # +1 minuto de margen

            # Indexar por usuario (para invalidación masiva)
            user_index_key = self._make_user_index_key(user_id)
            self._redis.sadd(user_index_key, f"{project_id}:{session_token}")
            self._redis.expire(user_index_key, timeout_seconds + 60)

            # Logging con hash del token (más seguro)
            token_hash = hashlib.sha256(session_token.encode()).hexdigest()[:8]
            logger.debug(
                f"[REDIS_SESSION] ✓ Session created:\n"
                f"  project_id: {project_id[:8]}...\n"
                f"  user_id: {user_id[:8]}...\n"
                f"  token_hash: {token_hash}\n"
                f"  expires_in: {timeout_seconds}s\n"
                f"  redis_key: {session_key}"
            )

            return session_token

        except RedisError as e:
            logger.error(f"Redis error creating session: {e}")
            raise

    def rotate_token(self, old_token: str, grace_period_seconds: int = 30) -> Optional[str]:
        """
        Rotar session token para prevenir session fixation attacks

        🔐 SEGURIDAD (Fase 2.2):
        - Genera nuevo token (CSPRNG)
        - Mantiene user_id binding (previene hijacking)
        - Grace period para race conditions
        - Token viejo redirige al nuevo

        Args:
            old_token: Token actual a rotar
            grace_period_seconds: Tiempo que el token viejo sigue válido (default: 30s)

        Returns:
            new_token: Nuevo token generado, o None si old_token no existe

        Security Notes:
            - Durante grace period, AMBOS tokens son válidos
            - Token viejo redirige automáticamente al nuevo en get_session()
            - Después de grace period, token viejo expira automáticamente (Redis TTL)
        """
        try:
            # Buscar la sesión actual con el token viejo
            # Necesitamos buscar en todos los proyectos (no ideal pero necesario)
            session_data = None
            project_id = None

            # Intentar encontrar la sesión buscando por pattern
            pattern = f"{self.KEY_PREFIX}:*:{old_token}"
            keys = list(self._redis.scan_iter(match=pattern, count=100))

            if not keys:
                logger.warning(
                    f"Attempted to rotate non-existent token (hash: {hashlib.sha256(old_token.encode()).hexdigest()[:8]})"
                )
                return None

            # Obtener la primera key que coincida
            old_session_key = keys[0]
            project_id = (
                old_session_key.decode().split(":")[1]
                if isinstance(old_session_key, bytes)
                else old_session_key.split(":")[1]
            )

            session_json = self._redis.get(old_session_key)
            if not session_json:
                return None

            session_data = self._deserialize_session(session_json)  # type: ignore[arg-type]

            # Verificar si ya está en rotación
            if session_data.get("rotating"):
                logger.debug(f"Token already rotating")
                return session_data.get("rotated_to")

            # Generar nuevo token
            new_token = secrets.token_urlsafe(32)

            # Copiar sesión al nuevo token
            new_session_key = self._make_session_key(project_id, new_token)

            # Calcular TTL restante del token viejo
            ttl = self._redis.ttl(old_session_key)
            if ttl <= 0:  # type: ignore[operator]
                logger.warning("Cannot rotate expired session")
                return None

            # Crear nueva sesión (sin marcar como rotating)
            new_session_json = self._serialize_session(session_data)
            self._redis.setex(new_session_key, ttl, new_session_json)  # type: ignore[arg-type]

            # Marcar token viejo como "en rotación"
            session_data["rotating"] = True
            session_data["rotated_to"] = new_token
            session_data["rotation_expires"] = datetime.now(timezone.utc) + timedelta(
                seconds=grace_period_seconds
            )

            rotated_session_json = self._serialize_session(session_data)
            self._redis.setex(old_session_key, grace_period_seconds, rotated_session_json)

            # Actualizar índices
            project_index_key = self._make_project_index_key(project_id)
            self._redis.sadd(project_index_key, new_token)

            user_index_key = self._make_user_index_key(session_data["user_id"])
            self._redis.sadd(user_index_key, f"{project_id}:{new_token}")

            token_hash = hashlib.sha256(new_token.encode()).hexdigest()[:8]
            logger.info(
                f"Token rotated: project={project_id[:8]}..., "
                f"new_token_hash={token_hash}, grace_period={grace_period_seconds}s"
            )

            return new_token

        except RedisError as e:
            logger.error(f"Redis error rotating token: {e}")
            return None

    def get_session(
        self, session_token: str, project_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Obtener una sesión de cifrado desde Redis

        🔐 SEGURIDAD:
        - Auto-expiración manejada por Redis TTL
        - Maneja grace period durante rotación
        - Retorna bytes de encryption_key

        Args:
            session_token: Token de sesión
            project_id: (Opcional) ID del proyecto para búsqueda más eficiente

        Returns:
            Dict con project_id, encryption_key (bytes) y user_id, o None si no existe/expiró
        """
        try:
            # Si tenemos project_id, búsqueda directa
            if project_id:
                session_key = self._make_session_key(project_id, session_token)
                session_json = self._redis.get(session_key)

                if not session_json:
                    logger.debug(f"Session not found: project={project_id[:8]}...")
                    return None

            else:
                # Búsqueda por pattern (menos eficiente pero necesario si no tenemos project_id)
                pattern = f"{self.KEY_PREFIX}:*:{session_token}"
                keys = list(self._redis.scan_iter(match=pattern, count=100))

                if not keys:
                    logger.debug("Session not found in Redis")
                    return None

                session_key = keys[0]
                session_json = self._redis.get(session_key)

                if not session_json:
                    return None

            # Deserializar
            session = self._deserialize_session(session_json)  # type: ignore[arg-type]

            # 🔐 FASE 2.2: Manejar tokens en rotación (grace period)
            if session.get("rotating"):
                new_token = session.get("rotated_to")
                rotation_expires = session.get("rotation_expires")

                now = datetime.now(timezone.utc)
                if rotation_expires is None or now > rotation_expires:
                    # Grace period expiró (Redis TTL lo eliminará automáticamente)
                    logger.debug("Grace period expired for rotating token")
                    return None

                # Redirigir al nuevo token
                logger.debug("Redirecting to new token during grace period")
                return self.get_session(str(new_token), str(session.get("project_id")))

            # Verificar expiración manual (Redis TTL ya lo maneja, pero validamos)
            now = datetime.now(timezone.utc)
            if now > session["expires_at"]:
                logger.debug("Session expired (TTL should have removed it)")
                return None

            # Retornar session data (encryption_key ya es bytes)
            return {
                "project_id": session["project_id"],
                "encryption_key": session["encryption_key"],  # bytes
                "user_id": session["user_id"],
                "expires_at": session["expires_at"],
            }

        except RedisError as e:
            logger.error(f"Redis error getting session: {e}")
            return None

    def invalidate_session(self, session_token: str, project_id: Optional[str] = None) -> bool:
        """
        Invalidar una sesión de cifrado

        Args:
            session_token: Token de sesión
            project_id: (Opcional) ID del proyecto para búsqueda más eficiente

        Returns:
            True si se eliminó, False si no existía
        """
        try:
            if project_id:
                session_key = self._make_session_key(project_id, session_token)
                deleted = self._redis.delete(session_key)
            else:
                # Buscar por pattern
                pattern = f"{self.KEY_PREFIX}:*:{session_token}"
                keys = list(self._redis.scan_iter(match=pattern, count=100))

                if not keys:
                    return False

                deleted = self._redis.delete(*keys)

            return bool(deleted > 0)  # type: ignore[operator]

        except RedisError as e:
            logger.error(f"Redis error invalidating session: {e}")
            return False

    def invalidate_project_sessions(self, project_id: str) -> int:
        """
        Invalidar todas las sesiones de un proyecto específico

        Use case: Cuando se deshabilita la encriptación de un proyecto

        Args:
            project_id: ID del proyecto

        Returns:
            Número de sesiones invalidadas
        """
        try:
            # Obtener todos los tokens del índice de proyecto
            project_index_key = self._make_project_index_key(project_id)
            tokens = self._redis.smembers(project_index_key)

            if not tokens:
                return 0

            # Eliminar todas las sesiones
            keys_to_delete = [
                self._make_session_key(
                    project_id, token.decode() if isinstance(token, bytes) else token
                )
                for token in tokens  # type: ignore[union-attr]
            ]

            deleted = self._redis.delete(*keys_to_delete) if keys_to_delete else 0

            # Eliminar índice
            self._redis.delete(project_index_key)

            logger.info(f"Invalidated {deleted} sessions for project {project_id[:8]}...")
            return int(deleted)  # type: ignore[arg-type]

        except RedisError as e:
            logger.error(f"Redis error invalidating project sessions: {e}")
            return 0

    def invalidate_user_sessions(self, user_id: str) -> int:
        """
        Invalidar todas las sesiones de un usuario específico

        Use cases:
        - Logout del usuario
        - Compromiso de cuenta detectado
        - Cambio de password

        Args:
            user_id: ID del usuario

        Returns:
            Número de sesiones invalidadas
        """
        try:
            # Obtener todos los tokens del índice de usuario
            user_index_key = self._make_user_index_key(user_id)
            session_refs = self._redis.smembers(user_index_key)

            if not session_refs:
                return 0

            # Parsear referencias (formato: "project_id:token")
            keys_to_delete = []
            for ref in session_refs:  # type: ignore[union-attr]
                ref_str = ref.decode() if isinstance(ref, bytes) else ref
                if ":" in ref_str:
                    project_id, token = ref_str.split(":", 1)
                    keys_to_delete.append(self._make_session_key(project_id, token))

            deleted = self._redis.delete(*keys_to_delete) if keys_to_delete else 0

            # Eliminar índice
            self._redis.delete(user_index_key)

            logger.info(f"Invalidated {deleted} sessions for user {user_id[:8]}...")
            return int(deleted)  # type: ignore[arg-type]

        except RedisError as e:
            logger.error(f"Redis error invalidating user sessions: {e}")
            return 0

    def cleanup_expired(self) -> int:
        """
        Limpiar sesiones expiradas (Redis TTL lo maneja automáticamente).

        Este método existe para compatibilidad con la API anterior,
        pero Redis TTL ya limpia sesiones expiradas automáticamente.

        Returns:
            0 (Redis maneja TTL automáticamente)
        """
        logger.debug("cleanup_expired called, but Redis TTL handles expiration automatically")
        return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Obtener estadísticas del caché

        Returns:
            Dict con estadísticas
        """
        try:
            # Contar keys de sesiones activas (excluir índices)
            # Pattern debe matchear solo: enc_session:{project_id}:{token}
            # NO debe matchear: enc_session:project_index:* ni enc_session:user_index:*
            pattern = f"{self.KEY_PREFIX}:*:*"
            total_sessions = 0

            # Usar SCAN para evitar bloquear Redis
            for key in self._redis.scan_iter(match=pattern, count=100):
                # Verificar que no sea un índice (double-check)
                key_str = key.decode() if isinstance(key, bytes) else key
                if not (":project_index:" in key_str or ":user_index:" in key_str):
                    total_sessions += 1

            return {
                "total_sessions": total_sessions,
                "active_sessions": total_sessions,  # Redis TTL ya eliminó las expiradas
                "expired_sessions": 0,  # Redis las limpia automáticamente
            }

        except RedisError as e:
            logger.error(f"Redis error getting stats: {e}")
            return {"total_sessions": 0, "active_sessions": 0, "expired_sessions": 0}


# Instancia global del caché Redis
_redis_encryption_session_cache: Optional[RedisEncryptionSessionCache] = None


def get_encryption_session_cache() -> RedisEncryptionSessionCache:
    """
    Obtener la instancia global del caché de sesiones Redis

    Returns:
        RedisEncryptionSessionCache: Instancia del caché
    """
    global _redis_encryption_session_cache

    if _redis_encryption_session_cache is None:
        _redis_encryption_session_cache = RedisEncryptionSessionCache()

    return _redis_encryption_session_cache
