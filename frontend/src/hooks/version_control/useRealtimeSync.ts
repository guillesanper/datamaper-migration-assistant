// src/hooks/version_control/useRealtimeSync.ts

import { useState, useEffect, useCallback, useRef } from 'react';
import { realtimeService } from '@/services/version_control';
import type { WebSocketState, RealtimeCallback } from '@/types/realtime_types';
import type { OnlineUser } from '@/types/collaboration_types';

/**
 * Hook para sincronización en tiempo real con WebSocket
 * INTEGRA: con WebSocket existente del backend
 */
export const useRealtimeSync = (projectId: string) => {
  const [state, setState] = useState<WebSocketState>(realtimeService.getState());
  const [onlineUsers, setOnlineUsers] = useState<OnlineUser[]>([]);
  const hasConnectedRef = useRef(false);

  /**
   * Conecta al WebSocket
   */
  const connect = useCallback(async () => {
    if (hasConnectedRef.current) {
      console.log('[useRealtimeSync] Already connected or connecting');
      return;
    }

    hasConnectedRef.current = true;

    try {
      await realtimeService.connect(projectId);
    } catch (error) {
      console.error('[useRealtimeSync] Connection error:', error);
      hasConnectedRef.current = false;
    }
  }, [projectId]);

  /**
   * Desconecta del WebSocket
   */
  const disconnect = useCallback(() => {
    realtimeService.disconnect();
    hasConnectedRef.current = false;
  }, []);

  /**
   * Reconecta manualmente
   */
  const reconnect = useCallback(async () => {
    disconnect();
    hasConnectedRef.current = false;
    await connect();
  }, [connect, disconnect]);

  // Suscribirse a cambios de estado
  useEffect(() => {
    const unsubscribe = realtimeService['subscribe']('state_change', ((newState: WebSocketState) => {
      setState(newState);
    }) as RealtimeCallback);

    return unsubscribe;
  }, []);

  // Suscribirse a presencia de usuarios
  useEffect(() => {
    const unsubscribe = realtimeService.subscribeToUserPresence((users: OnlineUser[]) => {
      setOnlineUsers(users);
    });

    return unsubscribe;
  }, []);

  // Auto-conectar al montar
  useEffect(() => {
    connect();

    // Desconectar al desmontar
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Computed values
  const isConnected = state.is_connected;
  const isConnecting = state.connection_state === 'connecting';
  const isError = state.connection_state === 'error';
  const lastError = state.last_error;
  const onlineCount = onlineUsers.length;

  return {
    state,
    onlineUsers,
    onlineCount,
    isConnected,
    isConnecting,
    isError,
    lastError,
    connect,
    disconnect,
    reconnect
  };
};

export default useRealtimeSync;
