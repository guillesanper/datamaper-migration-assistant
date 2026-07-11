"""
Background Tasks para Cleanup de Encriptación
==============================================

Sistema de tareas en background para limpieza automática de:
- Sesiones de encriptación expiradas
- Rate limiting de passphrases expirado
- Optimización de memoria

CORRECCIÓN DE VULNERABILIDAD: 🟡 MEDIA
- Previene memory leaks por sesiones expiradas
- Limpia automáticamente rate limiters antiguos
- Mejora el rendimiento del sistema

Configuración:
- ENCRYPTION_CLEANUP_INTERVAL_MINUTES: Intervalo de cleanup de sesiones (default: 15 min)
- RATE_LIMITER_CLEANUP_INTERVAL_MINUTES: Intervalo de cleanup de rate limiter (default: 60 min)

Autor: DataMap Security Team
Fecha: 2025-01-03
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

# Configuración
try:
    from app.config.security import security_settings

    ENCRYPTION_CLEANUP_INTERVAL = (
        security_settings.ENCRYPTION_CLEANUP_INTERVAL_MINUTES * 60
    )  # Convertir a segundos
    RATE_LIMITER_CLEANUP_INTERVAL = security_settings.RATE_LIMITER_CLEANUP_INTERVAL_MINUTES * 60
except ImportError:
    ENCRYPTION_CLEANUP_INTERVAL = 15 * 60  # 15 minutos
    RATE_LIMITER_CLEANUP_INTERVAL = 60 * 60  # 1 hora

logger = logging.getLogger(__name__)


class EncryptionCleanupService:
    """Servicio de limpieza para sesiones de encriptación"""

    def __init__(self):
        self.is_running = False
        self.cleanup_task: Optional[asyncio.Task] = None
        self.rate_limit_task: Optional[asyncio.Task] = None

    async def cleanup_encryption_sessions(self):
        """
        Tarea de limpieza de sesiones de encriptación expiradas

        Se ejecuta periódicamente según ENCRYPTION_CLEANUP_INTERVAL_MINUTES
        """
        from app.utils.redis_session_cache import get_encryption_session_cache

        try:
            cache = get_encryption_session_cache()
            removed_count = cache.cleanup_expired()

            if removed_count > 0:
                logger.info(
                    f"🧹 Encryption session cleanup: Removed {removed_count} expired sessions. "
                    f"Next cleanup in {ENCRYPTION_CLEANUP_INTERVAL / 60:.0f} minutes"
                )
            else:
                logger.debug(
                    f"🧹 Encryption session cleanup: No expired sessions found. "
                    f"Next cleanup in {ENCRYPTION_CLEANUP_INTERVAL / 60:.0f} minutes"
                )

            # Obtener estadísticas
            stats = cache.get_stats()
            logger.debug(
                f"📊 Encryption session stats: "
                f"Total={stats['total_sessions']}, "
                f"Active={stats['active_sessions']}, "
                f"Expired={stats['expired_sessions']}"
            )

        except Exception as e:
            logger.error(f"❌ Error in encryption session cleanup: {e}", exc_info=True)

    async def cleanup_rate_limiters(self):
        """
        Tarea de limpieza de rate limiters de passphrases

        Se ejecuta periódicamente según RATE_LIMITER_CLEANUP_INTERVAL_MINUTES
        """
        from app.utils.rate_limiter import get_passphrase_rate_limiter

        try:
            limiter = get_passphrase_rate_limiter()
            removed_count = limiter.cleanup_expired()

            if removed_count > 0:
                logger.info(
                    f"🧹 Rate limiter cleanup: Removed {removed_count} expired entries. "
                    f"Next cleanup in {RATE_LIMITER_CLEANUP_INTERVAL / 60:.0f} minutes"
                )
            else:
                logger.debug(
                    f"🧹 Rate limiter cleanup: No expired entries found. "
                    f"Next cleanup in {RATE_LIMITER_CLEANUP_INTERVAL / 60:.0f} minutes"
                )

            # Obtener estadísticas
            stats = limiter.get_stats()
            logger.debug(
                f"📊 Rate limiter stats: "
                f"Total tracked keys={stats['total_tracked_keys']}, "
                f"Currently locked={stats['currently_locked']}"
            )

        except Exception as e:
            logger.error(f"❌ Error in rate limiter cleanup: {e}", exc_info=True)

    async def encryption_cleanup_loop(self):
        """Loop principal de limpieza de sesiones de encriptación"""
        logger.info(
            f"🚀 Starting encryption session cleanup task "
            f"(interval: {ENCRYPTION_CLEANUP_INTERVAL / 60:.0f} minutes)"
        )

        while self.is_running:
            try:
                await self.cleanup_encryption_sessions()
                await asyncio.sleep(ENCRYPTION_CLEANUP_INTERVAL)
            except asyncio.CancelledError:
                logger.info("⏹️  Encryption session cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Critical error in encryption cleanup loop: {e}", exc_info=True)
                # Esperar un poco antes de reintentar para evitar loops infinitos de errores
                await asyncio.sleep(60)

    async def rate_limiter_cleanup_loop(self):
        """Loop principal de limpieza de rate limiters"""
        logger.info(
            f"🚀 Starting rate limiter cleanup task "
            f"(interval: {RATE_LIMITER_CLEANUP_INTERVAL / 60:.0f} minutes)"
        )

        while self.is_running:
            try:
                await self.cleanup_rate_limiters()
                await asyncio.sleep(RATE_LIMITER_CLEANUP_INTERVAL)
            except asyncio.CancelledError:
                logger.info("⏹️  Rate limiter cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Critical error in rate limiter cleanup loop: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def start(self):
        """Inicia todas las tareas de limpieza"""
        if self.is_running:
            logger.warning("⚠️  Cleanup tasks already running")
            return

        self.is_running = True

        # Ejecutar cleanup inmediato al inicio
        logger.info("🧹 Running initial cleanup...")
        await self.cleanup_encryption_sessions()
        await self.cleanup_rate_limiters()

        # Iniciar loops en background
        self.cleanup_task = asyncio.create_task(self.encryption_cleanup_loop())
        self.rate_limit_task = asyncio.create_task(self.rate_limiter_cleanup_loop())

        logger.info("✅ All encryption cleanup tasks started successfully")

    async def stop(self):
        """Detiene todas las tareas de limpieza"""
        if not self.is_running:
            logger.warning("⚠️  Cleanup tasks not running")
            return

        logger.info("🛑 Stopping cleanup tasks...")
        self.is_running = False

        # Cancelar tareas
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        if self.rate_limit_task:
            self.rate_limit_task.cancel()
            try:
                await self.rate_limit_task
            except asyncio.CancelledError:
                pass

        logger.info("✅ All cleanup tasks stopped")

    async def run_manual_cleanup(self):
        """
        Ejecuta cleanup manual de todas las tareas

        Use case: Admin ejecuta limpieza manual
        """
        logger.info("🧹 Running manual cleanup...")

        start_time = datetime.now(timezone.utc)

        await self.cleanup_encryption_sessions()
        await self.cleanup_rate_limiters()

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"✅ Manual cleanup completed in {elapsed:.2f} seconds")


# Instancia global del servicio
_cleanup_service = EncryptionCleanupService()


def get_cleanup_service() -> EncryptionCleanupService:
    """
    Obtiene la instancia global del servicio de limpieza

    Returns:
        EncryptionCleanupService: Instancia del servicio

    Example:
        ```python
        # En el startup de FastAPI
        from app.tasks.encryption_cleanup import get_cleanup_service

        @app.on_event("startup")
        async def startup():
            cleanup_service = get_cleanup_service()
            await cleanup_service.start()

        @app.on_event("shutdown")
        async def shutdown():
            cleanup_service = get_cleanup_service()
            await cleanup_service.stop()
        ```
    """
    return _cleanup_service


async def start_encryption_cleanup_tasks():
    """
    Función de conveniencia para iniciar todas las tareas de limpieza

    Use case: Llamar desde FastAPI startup event
    """
    service = get_cleanup_service()
    await service.start()


async def stop_encryption_cleanup_tasks():
    """
    Función de conveniencia para detener todas las tareas de limpieza

    Use case: Llamar desde FastAPI shutdown event
    """
    service = get_cleanup_service()
    await service.stop()


async def run_manual_cleanup():
    """
    Función de conveniencia para ejecutar limpieza manual

    Use case: Endpoint de admin para forzar limpieza
    """
    service = get_cleanup_service()
    await service.run_manual_cleanup()


# ===========================================================================
# Endpoint de Admin (opcional)
# ===========================================================================


async def get_cleanup_stats():
    """
    Obtiene estadísticas de las tareas de limpieza

    Returns:
        dict: Estadísticas de sesiones y rate limiters
    """
    from app.utils.rate_limiter import get_passphrase_rate_limiter
    from app.utils.redis_session_cache import get_encryption_session_cache

    try:
        cache = get_encryption_session_cache()
        limiter = get_passphrase_rate_limiter()

        session_stats = cache.get_stats()
        rate_limit_stats = limiter.get_stats()

        service = get_cleanup_service()

        return {
            "cleanup_service": {
                "is_running": service.is_running,
                "encryption_cleanup_interval_minutes": ENCRYPTION_CLEANUP_INTERVAL / 60,
                "rate_limiter_cleanup_interval_minutes": RATE_LIMITER_CLEANUP_INTERVAL / 60,
            },
            "encryption_sessions": session_stats,
            "rate_limiters": rate_limit_stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting cleanup stats: {e}")
        return {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    # Test de las tareas de limpieza
    async def test_cleanup():
        print("=== Test: Encryption Cleanup Tasks ===")

        service = get_cleanup_service()

        # Iniciar tareas
        await service.start()

        # Esperar un poco
        print("⏳ Waiting 5 seconds...")
        await asyncio.sleep(5)

        # Obtener stats
        stats = await get_cleanup_stats()
        print(f"📊 Stats: {stats}")

        # Ejecutar cleanup manual
        await service.run_manual_cleanup()

        # Detener tareas
        await service.stop()

        print("✅ Test completed")

    # Ejecutar test
    asyncio.run(test_cleanup())
