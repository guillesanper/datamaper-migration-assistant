"""
Rate Limiter - Security Module
================================

Sistema de rate limiting en memoria para prevenir ataques de fuerza bruta.

CORRECCIÓN DE VULNERABILIDAD: 🟡 MEDIA
- Previene ataques de fuerza bruta ilimitada en verificación de passphrase
- Implementa límites por usuario + proyecto
- Bloqueo temporal después de múltiples intentos fallidos

Características:
- Thread-safe con locks
- Auto-expiración de intentos antiguos
- Sliding window (ventana deslizante)
- Configurable vía variables de entorno

Configuración:
- PASSPHRASE_MAX_ATTEMPTS: Intentos máximos (default: 5)
- PASSPHRASE_WINDOW_SECONDS: Ventana de tiempo (default: 600 = 10 min)
- PASSPHRASE_LOCKOUT_SECONDS: Tiempo de bloqueo (default: 900 = 15 min)

Autor: DataMap Security Team
Fecha: 2025-01-03
"""

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter genérico con sliding window

    Estructura interna:
        {
            "key": {
                "attempts": [(timestamp1, success), (timestamp2, success), ...],
                "locked_until": timestamp or None
            }
        }
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 600,  # 10 minutos
        lockout_seconds: int = 900,  # 15 minutos
    ):
        """
        Inicializa el rate limiter

        Args:
            max_attempts: Número máximo de intentos fallidos permitidos
            window_seconds: Ventana de tiempo para contar intentos (sliding window)
            lockout_seconds: Tiempo de bloqueo después de exceder intentos
        """
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds

        self._cache: Dict[str, Dict] = {}
        self._lock = threading.Lock()

        logger.info(
            f"RateLimiter initialized: max_attempts={max_attempts}, "
            f"window={window_seconds}s, lockout={lockout_seconds}s"
        )

    def _cleanup_old_attempts(
        self, attempts: List[Tuple[datetime, bool]]
    ) -> List[Tuple[datetime, bool]]:
        """
        Elimina intentos fuera de la ventana de tiempo

        Args:
            attempts: Lista de tuplas (timestamp, success)

        Returns:
            Lista filtrada solo con intentos dentro de la ventana
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        return [(ts, success) for ts, success in attempts if ts > cutoff_time]

    def is_locked(self, key: str) -> Tuple[bool, Optional[int]]:
        """
        Verifica si una key está bloqueada

        Args:
            key: Identificador (e.g., "user:123:project:456")

        Returns:
            Tupla (is_locked: bool, seconds_remaining: int|None)

        Example:
            >>> locked, remaining = limiter.is_locked("user:abc:project:xyz")
            >>> if locked:
            >>>     print(f"Bloqueado por {remaining} segundos más")
        """
        with self._lock:
            entry = self._cache.get(key)

            if not entry:
                return False, None

            locked_until = entry.get("locked_until")

            if locked_until:
                now = datetime.now(timezone.utc)
                if now < locked_until:
                    # Aún bloqueado
                    remaining = int((locked_until - now).total_seconds())
                    return True, remaining
                else:
                    # Lockout expiró, limpiar
                    entry["locked_until"] = None
                    return False, None

            return False, None

    def record_attempt(self, key: str, success: bool) -> Dict[str, Any]:
        """
        Registra un intento de autenticación

        Args:
            key: Identificador único (e.g., "user:123:project:456")
            success: True si el intento fue exitoso, False si falló

        Returns:
            Dict con información del estado:
            {
                "allowed": bool,  # Si el intento fue permitido
                "remaining_attempts": int,  # Intentos restantes antes de lockout
                "locked": bool,  # Si ahora está bloqueado
                "locked_until": datetime|None,  # Timestamp de fin de bloqueo
                "retry_after": int|None  # Segundos hasta poder reintentar
            }

        Example:
            ```python
            result = limiter.record_attempt("user:abc:project:xyz", success=False)
            if result["locked"]:
                raise HTTPException(
                    status_code=429,
                    detail=f"Demasiados intentos. Reintenta en {result['retry_after']}s"
                )
            ```
        """
        now = datetime.now(timezone.utc)

        with self._lock:
            # Obtener o crear entry
            if key not in self._cache:
                self._cache[key] = {"attempts": [], "locked_until": None}

            entry = self._cache[key]

            # Verificar si está bloqueado
            if entry["locked_until"] and now < entry["locked_until"]:
                # Intentó durante lockout
                remaining = int((entry["locked_until"] - now).total_seconds())
                logger.warning(
                    f"Rate limit: Attempt during lockout for key {key[:32]}... "
                    f"({remaining}s remaining)"
                )
                return {
                    "allowed": False,
                    "remaining_attempts": 0,
                    "locked": True,
                    "locked_until": entry["locked_until"],
                    "retry_after": remaining,
                }

            # Si lockout expiró, limpiar
            if entry["locked_until"] and now >= entry["locked_until"]:
                entry["locked_until"] = None
                entry["attempts"] = []
                logger.info(f"Rate limit: Lockout expired for key {key[:32]}...")

            # Limpiar intentos antiguos (sliding window)
            entry["attempts"] = self._cleanup_old_attempts(entry["attempts"])

            # Registrar nuevo intento
            entry["attempts"].append((now, success))

            # Si fue exitoso, limpiar contador
            if success:
                entry["attempts"] = []
                logger.debug(f"Rate limit: Successful attempt for key {key[:32]}..., counter reset")
                return {
                    "allowed": True,
                    "remaining_attempts": self.max_attempts,
                    "locked": False,
                    "locked_until": None,
                    "retry_after": None,
                }

            # Contar intentos fallidos en la ventana
            failed_attempts = sum(1 for _, s in entry["attempts"] if not s)

            # Verificar si excedió el límite
            if failed_attempts >= self.max_attempts:
                # BLOQUEAR
                entry["locked_until"] = now + timedelta(seconds=self.lockout_seconds)
                logger.warning(
                    f"Rate limit: LOCKED key {key[:32]}... "
                    f"({failed_attempts} failed attempts) until {entry['locked_until']}"
                )
                return {
                    "allowed": False,
                    "remaining_attempts": 0,
                    "locked": True,
                    "locked_until": entry["locked_until"],
                    "retry_after": self.lockout_seconds,
                }

            # No bloqueado aún
            remaining = self.max_attempts - failed_attempts
            logger.debug(
                f"Rate limit: Failed attempt for key {key[:32]}... "
                f"({failed_attempts}/{self.max_attempts}, {remaining} remaining)"
            )
            return {
                "allowed": True,
                "remaining_attempts": remaining,
                "locked": False,
                "locked_until": None,
                "retry_after": None,
            }

    def reset(self, key: str) -> bool:
        """
        Resetea el contador de intentos para una key

        Use case: Admin desbloquea a un usuario manualmente

        Args:
            key: Identificador

        Returns:
            True si había una entry que se reseteó, False si no existía
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.info(f"Rate limit: Reset key {key[:32]}...")
                return True
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del rate limiter

        Returns:
            Dict con estadísticas
        """
        with self._lock:
            total_keys = len(self._cache)
            now = datetime.now(timezone.utc)

            locked_keys = sum(
                1
                for entry in self._cache.values()
                if entry["locked_until"] and now < entry["locked_until"]
            )

            return {
                "total_tracked_keys": total_keys,
                "currently_locked": locked_keys,
                "config": {
                    "max_attempts": self.max_attempts,
                    "window_seconds": self.window_seconds,
                    "lockout_seconds": self.lockout_seconds,
                },
            }

    def cleanup_expired(self) -> int:
        """
        Limpia entries expiradas del caché

        Returns:
            Número de entries eliminadas
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.lockout_seconds + self.window_seconds)

        with self._lock:
            keys_to_remove = []

            for key, entry in self._cache.items():
                # Si lockout expiró y no hay intentos recientes
                if entry["locked_until"] and now >= entry["locked_until"]:
                    entry["locked_until"] = None

                # Limpiar intentos antiguos
                entry["attempts"] = self._cleanup_old_attempts(entry["attempts"])

                # Si no tiene intentos y no está bloqueado, eliminar
                if not entry["attempts"] and not entry["locked_until"]:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._cache[key]

            if keys_to_remove:
                logger.debug(f"Rate limit: Cleaned up {len(keys_to_remove)} expired entries")

            return len(keys_to_remove)


# ============================================================================
# Rate Limiter Global para Passphrase Verification
# ============================================================================

# Importar configuración centralizada
try:
    from app.config.security import security_settings

    PASSPHRASE_MAX_ATTEMPTS = security_settings.PASSPHRASE_MAX_ATTEMPTS
    PASSPHRASE_WINDOW_SECONDS = security_settings.PASSPHRASE_WINDOW_SECONDS
    PASSPHRASE_LOCKOUT_SECONDS = security_settings.PASSPHRASE_LOCKOUT_SECONDS
except ImportError:
    # Fallback para cuando se ejecuta fuera del contexto de la app
    PASSPHRASE_MAX_ATTEMPTS = int(os.getenv("PASSPHRASE_MAX_ATTEMPTS", "5"))
    PASSPHRASE_WINDOW_SECONDS = int(os.getenv("PASSPHRASE_WINDOW_SECONDS", "600"))
    PASSPHRASE_LOCKOUT_SECONDS = int(os.getenv("PASSPHRASE_LOCKOUT_SECONDS", "900"))

# Instancia global
_passphrase_rate_limiter = RateLimiter(
    max_attempts=PASSPHRASE_MAX_ATTEMPTS,
    window_seconds=PASSPHRASE_WINDOW_SECONDS,
    lockout_seconds=PASSPHRASE_LOCKOUT_SECONDS,
)


def get_passphrase_rate_limiter() -> RateLimiter:
    """
    Obtiene el rate limiter global para verificación de passphrase

    Returns:
        RateLimiter: Instancia del rate limiter

    Example:
        ```python
        from app.utils.rate_limiter import get_passphrase_rate_limiter

        limiter = get_passphrase_rate_limiter()

        # Antes de verificar passphrase
        locked, remaining = limiter.is_locked(f"user:{user_id}:project:{project_id}")
        if locked:
            raise HTTPException(
                status_code=429,
                detail=f"Demasiados intentos. Reintenta en {remaining} segundos"
            )

        # Verificar passphrase
        is_valid = verify_passphrase(...)

        # Registrar resultado
        result = limiter.record_attempt(
            f"user:{user_id}:project:{project_id}",
            success=is_valid
        )

        if result["locked"]:
            raise HTTPException(status_code=429, ...)
        ```
    """
    return _passphrase_rate_limiter


def create_rate_limit_key(user_id: str, project_id: str) -> str:
    """
    Crea una key de rate limiting para verificación de passphrase

    Args:
        user_id: ID del usuario
        project_id: ID del proyecto

    Returns:
        String key para rate limiting

    Security Note:
        La key combina user_id + project_id para que los límites sean
        por usuario Y por proyecto (no globales por proyecto)
    """
    return f"passphrase:user:{user_id}:project:{project_id}"


if __name__ == "__main__":
    # Tests básicos
    print("=== Test: Rate Limiter ===")

    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)

    test_key = "test:user:123:project:456"

    # 3 intentos fallidos
    for i in range(3):
        result = limiter.record_attempt(test_key, success=False)
        print(f"Intento {i+1}: {result}")

    # Cuarto intento (debe bloquear)
    result = limiter.record_attempt(test_key, success=False)
    print(f"Intento 4 (lockout): {result}")

    # Verificar que está bloqueado
    locked, remaining = limiter.is_locked(test_key)
    print(f"¿Bloqueado? {locked}, Segundos restantes: {remaining}")

    # Resetear
    limiter.reset(test_key)
    print(f"Reset exitoso")

    # Verificar que ya no está bloqueado
    locked, remaining = limiter.is_locked(test_key)
    print(f"¿Bloqueado después de reset? {locked}")

    # Stats
    print(f"Stats: {limiter.get_stats()}")
