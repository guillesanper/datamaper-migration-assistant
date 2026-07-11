// src/hooks/version_control/useEntityLock.ts

import { useState, useCallback, useEffect, useRef } from 'react';
import { lockingService } from '@/services/version_control';
import type { LockStatus } from '@/types/locking_types';
import { useAuth } from '@/providers/AuthProvider';

/**
 * Hook para gestión de locks de una entidad
 * REUTILIZA: useAuth existente, patrón de hooks del proyecto
 */
export const useEntityLock = (entityId: string, entityType: string) => {
  useAuth();
  const [lockStatus, setLockStatus] = useState<LockStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const checkIntervalRef = useRef<number | null>(null);

  /**
   * Verifica el estado del lock
   */
  const checkLockStatus = useCallback(async () => {
    try {
      const status = await lockingService.checkLockStatus(entityId, entityType);
      setLockStatus(status);
      return status;
    } catch (err: unknown) {
      console.error('[useEntityLock] Check status error:', err);
      return null;
    }
  }, [entityId, entityType]);

  /**
   * Adquiere el lock
   */
  const acquireLock = useCallback(async (duration?: number): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      const lock = await lockingService.acquireLock({
        entity_id: entityId,
        entity_type: entityType,
        duration
      });

      // Actualizar estado local
      setLockStatus({
        is_locked: true,
        lock,
        can_edit: true,
        can_force_unlock: false,
        is_locked_by_me: true
      });

      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al adquirir lock');
      console.error('[useEntityLock] Acquire error:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [entityId, entityType]);

  /**
   * Libera el lock
   */
  const releaseLock = useCallback(async (): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      await lockingService.releaseLock(entityId, entityType);

      // Actualizar estado local
      setLockStatus({
        is_locked: false,
        can_edit: true,
        can_force_unlock: false,
        is_locked_by_me: false
      });

      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al liberar lock');
      console.error('[useEntityLock] Release error:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [entityId, entityType]);

  /**
   * Fuerza el unlock (solo admins)
   */
  const forceUnlock = useCallback(async (reason?: string): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      await lockingService.forceUnlock(entityId, entityType, reason);

      // Actualizar estado local
      setLockStatus({
        is_locked: false,
        can_edit: true,
        can_force_unlock: true,
        is_locked_by_me: false
      });

      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al forzar unlock');
      console.error('[useEntityLock] Force unlock error:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [entityId, entityType]);

  /**
   * Limpia el error
   */
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Computed values
  const isLocked = lockStatus?.is_locked || false;
  const isLockedByMe = lockStatus?.is_locked_by_me || false;
  const canEdit = lockStatus?.can_edit || false;
  const canForceUnlock = lockStatus?.can_force_unlock || false;
  const lock = lockStatus?.lock || null;

  // Verificar estado periódicamente
  useEffect(() => {
    checkLockStatus();

    // Verificar cada 10 segundos
    checkIntervalRef.current = window.setInterval(() => {
      checkLockStatus();
    }, 10000);

    return () => {
      if (checkIntervalRef.current) {
        clearInterval(checkIntervalRef.current);
      }
    };
  }, [checkLockStatus]);

  // Cleanup: liberar lock al desmontar si lo tenemos
  useEffect(() => {
    return () => {
      if (isLockedByMe) {
        // Intentar liberar (sin await porque es cleanup)
        lockingService.releaseLock(entityId, entityType).catch(err => {
          console.error('[useEntityLock] Cleanup release error:', err);
        });
      }
    };
  }, [isLockedByMe, entityId, entityType]);

  return {
    lockStatus,
    loading,
    error,
    isLocked,
    isLockedByMe,
    canEdit,
    canForceUnlock,
    lock,
    acquireLock,
    releaseLock,
    forceUnlock,
    checkLockStatus,
    clearError
  };
};

export default useEntityLock;
