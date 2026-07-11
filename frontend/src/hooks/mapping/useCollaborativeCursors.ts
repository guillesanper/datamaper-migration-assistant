// src/hooks/mapping/useCollaborativeCursors.ts
import { useState, useEffect, useCallback, useRef } from 'react';
import { realtimeService } from '@/services/version_control/realtime.service';
import type { CursorPosition } from '@/types/realtime_types';

export interface CollaborativeCursor extends CursorPosition {
  actorId: string;
  actorName: string;
  lastUpdate: number;
  tableId?: string;
}

const CURSOR_TIMEOUT = 5000; // 5 segundos sin actualización = cursor desaparece

export function useCollaborativeCursors(projectId: string, enabled: boolean = true, currentUserId?: string) {
  const [cursors, setCursors] = useState<Map<string, CollaborativeCursor>>(new Map());
  const cleanupTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup de cursores obsoletos
  const cleanupOldCursors = useCallback(() => {
    const now = Date.now();
    setCursors((prev) => {
      const updated = new Map(prev);
      let hasChanges = false;

      for (const [userId, cursor] of updated.entries()) {
        if (now - cursor.lastUpdate > CURSOR_TIMEOUT) {
          updated.delete(userId);
          hasChanges = true;
        }
      }

      return hasChanges ? updated : prev;
    });
  }, []);

  // Iniciar timer de limpieza
  useEffect(() => {
    if (!enabled) return;

    cleanupTimerRef.current = setInterval(cleanupOldCursors, 1000);

    return () => {
      if (cleanupTimerRef.current) {
        clearInterval(cleanupTimerRef.current);
      }
    };
  }, [enabled, cleanupOldCursors]);

  // Limpiar el cursor del usuario actual si aparece en el estado
  useEffect(() => {
    if (!currentUserId) return;

    setCursors((prev) => {
      if (prev.has(currentUserId)) {
        console.log('[useCollaborativeCursors] Removing own cursor from state:', currentUserId);
        const updated = new Map(prev);
        updated.delete(currentUserId);
        return updated;
      }
      return prev;
    });
  }, [currentUserId]);

  // Suscribirse a eventos de cursores
  useEffect(() => {
    if (!enabled) return;

    interface CursorEventMessage {
      type: string;
      actor_id?: string;
      actor_name?: string;
      x?: number;
      y?: number;
      tableId?: string;
      viewport?: { x: number; y: number; zoom: number };
      payload?: {
        x?: number;
        y?: number;
        tableId?: string;
        viewport?: { x: number; y: number; zoom: number };
      };
    }
    const handleCursorEvent = (message: CursorEventMessage) => {
      console.log('[useCollaborativeCursors] Cursor event received:', message);

      // Manejar cursor_move
      if (message.type === 'cursor_move') {
        // El backend puede enviar datos directamente en el mensaje o en el payload
        const actor_id = message.actor_id;
        const actor_name = message.actor_name;
        const x = message.x ?? message.payload?.x;
        const y = message.y ?? message.payload?.y;
        const tableId = message.tableId ?? message.payload?.tableId;
        const viewport = message.viewport ?? message.payload?.viewport ?? { x: 0, y: 0, zoom: 1 };

        if (!actor_id) {
          console.warn('[useCollaborativeCursors] No actor_id in cursor_move event');
          return;
        }

        // FILTRAR: Ignorar el cursor del usuario actual
        if (currentUserId && actor_id === currentUserId) {
          console.log('[useCollaborativeCursors] Filtering out own cursor:', actor_id);
          return;
        }

        if (x === undefined || y === undefined) {
          console.warn('[useCollaborativeCursors] Missing x or y coordinates in cursor_move event');
          return;
        }

        setCursors((prev) => {
          const updated = new Map(prev);
          updated.set(actor_id, {
            x,
            y,
            tableId,
            user_id: actor_id,
            username: actor_name || 'Usuario',
            timestamp: new Date().toISOString(),
            viewport, // Usar el viewport recibido del otro usuario (aunque no se usa en el renderizado)
            actorId: actor_id,
            actorName: actor_name || 'Usuario',
            lastUpdate: Date.now(),
          });
          return updated;
        });
      }
      // Manejar cursor_leave
      else if (message.type === 'cursor_leave') {
        const actor_id = message.actor_id;

        if (!actor_id) {
          console.warn('[useCollaborativeCursors] No actor_id in cursor_leave event');
          return;
        }

        setCursors((prev) => {
          const updated = new Map(prev);
          updated.delete(actor_id);
          return updated;
        });
      }
    };

    // Suscribirse a eventos de cursor
    const unsubscribe = realtimeService.subscribeToCursors((message) => handleCursorEvent(message as CursorEventMessage));

    return () => {
      unsubscribe();
    };
  }, [projectId, enabled, currentUserId]);

  // Broadcast de posición de cursor (con throttling ya implementado en el servicio)
  const broadcastCursorPosition = useCallback(
    (position: CursorPosition) => {
      if (!enabled) return;

      // CRÍTICO: Verificar que el WebSocket esté conectado antes de enviar
      if (!realtimeService.isConnected()) {
        console.warn('[useCollaborativeCursors] Skipping cursor broadcast - not connected');
        return;
      }

      realtimeService.broadcastCursorPosition(projectId, position);
    },
    [projectId, enabled]
  );

  // Broadcast de salida de cursor
  const broadcastCursorLeave = useCallback(() => {
    if (!enabled) return;

    // ✅ CRÍTICO: Verificar que el WebSocket esté conectado antes de enviar
    if (!realtimeService.isConnected()) {
      console.warn('[useCollaborativeCursors] Skipping cursor leave - not connected');
      return;
    }

    realtimeService.broadcastCursorLeave(projectId);
  }, [projectId, enabled]);

  return {
    cursors: Array.from(cursors.values()),
    broadcastCursorPosition,
    broadcastCursorLeave,
  };
}
