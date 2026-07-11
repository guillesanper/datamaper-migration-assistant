// src/hooks/mapping/useColumnLocks.ts

import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { ColumnLockInfo } from '@/types/locking_types';
import { toast } from '../../utils/toast';
import { getApiError } from '../../utils/apiError';

/**
 * Hook para gestionar locks de columnas individuales en mapeos
 *
 * Características:
 * - Auto-lock cuando usuario selecciona una columna
 * - Auto-release al desmontar o cambiar de columna
 * - Heartbeat automático cada 30s
 * - Escucha eventos de locks de otros usuarios via WebSocket
 */
export const useColumnLocks = (_projectId: string) => {
  const { t } = useTranslation('common');
  const [columnLocks, setColumnLocks] = useState<Map<string, ColumnLockInfo>>(new Map());
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const currentLockRef = useRef<{ tableName: string; columnName: string; lockId: string } | null>(null);

  /**
   * Adquiere lock de una columna
   */
  const acquireColumnLock = useCallback(async (
    tableName: string,
    columnName: string
  ): Promise<boolean> => {
    try {
      const entityId = `${tableName}:${columnName}`;

      // TODO: Llamar al endpoint de backend /api/locks/acquire
      // Por ahora, simulamos el éxito
      console.log(`[useColumnLocks] Acquiring lock for ${entityId}`);

      // Simular respuesta del backend
      const lockInfo: ColumnLockInfo = {
        tableName,
        columnName,
        isLocked: true,
        isLockedByMe: true,
        canEdit: true,
        expiresAt: new Date(Date.now() + 3 * 60 * 1000).toISOString(), // 3 minutos
      };

      setColumnLocks(prev => new Map(prev).set(entityId, lockInfo));
      currentLockRef.current = { tableName, columnName, lockId: 'temp-id' };

      // Iniciar heartbeat
      startHeartbeat(tableName, columnName);

      return true;
    } catch (error) {
      console.error('[useColumnLocks] Error acquiring lock:', error);
      toast.error(getApiError(error, t));
      return false;
    }
  }, []);

  /**
   * Libera lock de una columna
   */
  const releaseColumnLock = useCallback(async (
    tableName: string,
    columnName: string
  ): Promise<boolean> => {
    try {
      const entityId = `${tableName}:${columnName}`;

      console.log(`[useColumnLocks] Releasing lock for ${entityId}`);

      // TODO: Llamar al endpoint de backend /api/locks/release

      setColumnLocks(prev => {
        const next = new Map(prev);
        next.delete(entityId);
        return next;
      });

      if (currentLockRef.current?.tableName === tableName &&
          currentLockRef.current?.columnName === columnName) {
        currentLockRef.current = null;
        stopHeartbeat();
      }

      return true;
    } catch (error) {
      console.error('[useColumnLocks] Error releasing lock:', error);
      return false;
    }
  }, []);

  /**
   * Obtiene información de lock de una columna
   */
  const getColumnLockInfo = useCallback((
    tableName: string,
    columnName: string
  ): ColumnLockInfo => {
    const entityId = `${tableName}:${columnName}`;
    const lockInfo = columnLocks.get(entityId);

    if (lockInfo) {
      return lockInfo;
    }

    // No hay lock
    return {
      tableName,
      columnName,
      isLocked: false,
      isLockedByMe: false,
      canEdit: true,
    };
  }, [columnLocks]);

  /**
   * Verifica si una columna está bloqueada
   */
  const isColumnLocked = useCallback((
    tableName: string,
    columnName: string
  ): boolean => {
    const entityId = `${tableName}:${columnName}`;
    const lockInfo = columnLocks.get(entityId);
    return lockInfo?.isLocked && !lockInfo?.isLockedByMe || false;
  }, [columnLocks]);

  /**
   * Inicia heartbeat para renovar el lock
   */
  const startHeartbeat = (tableName: string, columnName: string) => {
    stopHeartbeat();

    heartbeatIntervalRef.current = setInterval(() => {
      console.log(`[useColumnLocks] Heartbeat for ${tableName}:${columnName}`);
      // TODO: Llamar endpoint /api/locks/{lock_id}/renew
    }, 30000); // 30 segundos
  };

  /**
   * Detiene heartbeat
   */
  const stopHeartbeat = () => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
  };

  /**
   * Escuchar eventos de locks via WebSocket
   * TEMPORALMENTE DESHABILITADO: Causa memory leaks con múltiples suscripciones
   * TODO: Mover esto a nivel de TwoColumnView y pasar locks como props
   */
  useEffect(() => {
    // Comentado temporalmente para evitar memory leaks
    // Cada TableNode se estaba suscribiendo, causando N suscripciones donde N = número de tablas

    // const unsubscribe = realtimeService.subscribeToLocks((lock: Lock) => {
    //   // Parsear entity_id para obtener tabla y columna
    //   if (lock.entity_type === 'column') {
    //     const parts = lock.entity_id.split(':', 2);
    //     if (parts.length === 2) {
    //       const [tableName, columnName] = parts;

    //       const lockInfo: ColumnLockInfo = {
    //         tableName,
    //         columnName,
    //         isLocked: true,
    //         lockedBy: {
    //           userId: lock.user_id,
    //           username: lock.username,
    //           email: lock.user_email,
    //           avatar: lock.user_avatar,
    //         },
    //         expiresAt: lock.expires_at,
    //         isLockedByMe: false, // TODO: Comparar con current user
    //         canEdit: false,
    //       };

    //       setColumnLocks(prev => new Map(prev).set(lock.entity_id, lockInfo));
    //     }
    //   }
    // });

    // return () => {
    //   unsubscribe();
    // };
  }, []);

  /**
   * Cleanup al desmontar: liberar lock actual
   */
  useEffect(() => {
    return () => {
      if (currentLockRef.current) {
        const { tableName, columnName } = currentLockRef.current;
        releaseColumnLock(tableName, columnName);
      }
      stopHeartbeat();
    };
  }, [releaseColumnLock]);

  return {
    acquireColumnLock,
    releaseColumnLock,
    getColumnLockInfo,
    isColumnLocked,
    columnLocks: Array.from(columnLocks.values()),
  };
};

export default useColumnLocks;
