// src/services/version_control/locking.service.ts

import { apiService } from '../api.service';
import type {
  Lock,
  LockStatus,
  LockResponse,
  AcquireLockRequest,
  ForceUnlockRequest
} from '@/types/locking_types';
import { LOCK_DURATION, HEARTBEAT_INTERVAL } from '@/utils/version_control/lockUtils';

/**
 * Servicio para gestión de bloqueos de entidades
 * REUTILIZA: apiService existente
 */
class LockingService {
  private readonly BASE_PATH = '/api/locks';
  private heartbeatTimers: Map<string, ReturnType<typeof setInterval>> = new Map();

  /**
   * Adquiere un lock sobre una entidad
   */
  async acquireLock(data: AcquireLockRequest): Promise<Lock> {
    try {
      const response = await apiService.post<LockResponse>(this.BASE_PATH, {
        entity_id: data.entity_id,
        entity_type: data.entity_type,
        duration: data.duration || LOCK_DURATION / 1000 // Convertir a segundos
      });

      if (!response.success || !response.data?.lock) {
        throw new Error(response.message || 'Error al adquirir lock');
      }

      // Iniciar heartbeat automático
      this.startHeartbeat(response.data.lock);

      return response.data.lock;
    } catch (error: unknown) {
      console.error('[LockingService] Error acquiring lock:', error);
      throw error;
    }
  }

  /**
   * Libera un lock
   */
  async releaseLock(entityId: string, entityType: string): Promise<void> {
    try {
      const response = await apiService.delete<LockResponse>(
        `${this.BASE_PATH}/${entityType}/${entityId}`
      );

      if (!response.success) {
        throw new Error(response.message || 'Error al liberar lock');
      }

      // Detener heartbeat
      this.stopHeartbeat(entityId, entityType);
    } catch (error: unknown) {
      console.error('[LockingService] Error releasing lock:', error);
      throw error;
    }
  }

  /**
   * Verifica el estado de lock de una entidad
   */
  async checkLockStatus(entityId: string, entityType: string): Promise<LockStatus> {
    try {
      const response = await apiService.get<LockResponse>(
        `${this.BASE_PATH}/${entityType}/${entityId}/status`
      );

      if (!response.success || !response.data?.status) {
        throw new Error(response.message || 'Error al verificar lock');
      }

      return response.data.status;
    } catch (error: unknown) {
      console.error('[LockingService] Error checking lock status:', error);
      throw error;
    }
  }

  /**
   * Renueva un lock (extiende su duración)
   */
  async renewLock(lockId: string): Promise<Lock> {
    try {
      const response = await apiService.post<LockResponse>(
        `${this.BASE_PATH}/${lockId}/renew`
      );

      if (!response.success || !response.data?.lock) {
        throw new Error(response.message || 'Error al renovar lock');
      }

      return response.data.lock;
    } catch (error: unknown) {
      console.error('[LockingService] Error renewing lock:', error);
      throw error;
    }
  }

  /**
   * Fuerza el unlock de una entidad (solo admins)
   */
  async forceUnlock(entityId: string, entityType: string, reason?: string): Promise<void> {
    try {
      const response = await apiService.post<LockResponse>(
        `${this.BASE_PATH}/${entityType}/${entityId}/force-unlock`,
        { reason } as ForceUnlockRequest
      );

      if (!response.success) {
        throw new Error(response.message || 'Error al forzar unlock');
      }

      // Detener heartbeat si existía
      this.stopHeartbeat(entityId, entityType);
    } catch (error: unknown) {
      console.error('[LockingService] Error forcing unlock:', error);
      throw error;
    }
  }

  /**
   * Obtiene todos los locks activos de un proyecto
   */
  async getActiveLocks(projectId: string): Promise<Lock[]> {
    try {
      const response = await apiService.get<LockResponse>(
        `${this.BASE_PATH}/project/${projectId}`
      );

      if (!response.success || !response.data?.locks) {
        throw new Error(response.message || 'Error al obtener locks');
      }

      return response.data.locks;
    } catch (error: unknown) {
      console.error('[LockingService] Error getting active locks:', error);
      throw error;
    }
  }

  /**
   * Inicia el heartbeat automático para mantener un lock activo
   * @private
   */
  private startHeartbeat(lock: Lock): void {
    const key = this.getLockKey(lock.entity_id, lock.entity_type);

    // Limpiar heartbeat anterior si existe
    this.stopHeartbeat(lock.entity_id, lock.entity_type);

    // Crear nuevo heartbeat
    const timerId = setInterval(async () => {
      try {
        await this.renewLock(lock.id);
        console.log(`[LockingService] Heartbeat sent for lock ${lock.id}`);
      } catch (error) {
        console.error('[LockingService] Heartbeat failed:', error);
        // Si falla, detener heartbeat
        this.stopHeartbeat(lock.entity_id, lock.entity_type);
      }
    }, HEARTBEAT_INTERVAL);

    this.heartbeatTimers.set(key, timerId);
  }

  /**
   * Detiene el heartbeat de un lock
   * @private
   */
  private stopHeartbeat(entityId: string, entityType: string): void {
    const key = this.getLockKey(entityId, entityType);
    const timerId = this.heartbeatTimers.get(key);

    if (timerId) {
      clearInterval(timerId);
      this.heartbeatTimers.delete(key);
      console.log(`[LockingService] Heartbeat stopped for ${key}`);
    }
  }

  /**
   * Genera una key única para un lock
   * @private
   */
  private getLockKey(entityId: string, entityType: string): string {
    return `${entityType}:${entityId}`;
  }

  /**
   * Detiene todos los heartbeats activos (para cleanup)
   */
  stopAllHeartbeats(): void {
    this.heartbeatTimers.forEach((timerId) => {
      clearInterval(timerId);
    });
    this.heartbeatTimers.clear();
    console.log('[LockingService] All heartbeats stopped');
  }
}

// Exportar instancia singleton
export const lockingService = new LockingService();
export default LockingService;
