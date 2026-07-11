// src/services/version_control/realtime.service.ts

import type {
  RealtimeMessage,
  RealtimeCallback,
  UnsubscribeFn,
  WebSocketState
} from '@/types/realtime_types';
import type { OnlineUser } from '@/types/collaboration_types';
import type { Lock } from '@/types/locking_types';
import type { Comment } from '@/types/comments_types';

/**
 * Servicio de WebSocket para comunicación en tiempo real
 * INTEGRA: con WebSocket existente en backend (realtime.py)
 */
class RealtimeService {
  private ws: WebSocket | null = null;
  private projectId: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;

  // Subscribers
  private subscribers: Map<string, Set<RealtimeCallback>> = new Map();

  // Estado
  private state: WebSocketState = {
    connection_state: 'disconnected',
    online_users: [],
    is_connected: false
  };

  /**
   * Conecta al WebSocket del proyecto
   */
  async connect(projectId: string): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('[RealtimeService] Already connected');
      return;
    }

    this.projectId = projectId;

    this.updateState({ connection_state: 'connecting' });

    const wsUrl = this.getWebSocketUrl(projectId);
    console.log(`[RealtimeService] Connecting to: ${wsUrl}`);

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('[RealtimeService] ✅ WebSocket connection established');
    
        this.reconnectAttempts = 0;
        this.updateState({
          connection_state: 'connected',
          is_connected: true
        });
        this.startHeartbeat();
        this.notifySubscribers('connection', { type: 'connected' });
      };

      this.ws.onmessage = (event) => {
        try {
          const message: RealtimeMessage = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('[RealtimeService] Error parsing message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[RealtimeService] WebSocket error:', error);
        this.updateState({
          connection_state: 'error',
          last_error: 'WebSocket error'
        });
      };

      this.ws.onclose = (event) => {
        const closeReasons: Record<number, string> = {
          1000: 'Normal closure',
          1001: 'Going away',
          1002: 'Protocol error',
          1003: 'Unsupported data',
          1006: 'Abnormal closure',
          1008: 'Policy violation (possibly authentication)',
          1011: 'Server error',
        };

        const reason = closeReasons[event.code] || event.reason || 'Unknown reason';
        console.log(`[RealtimeService] ❌ WebSocket closed (code: ${event.code}, reason: ${reason})`);

        // Si es error de autenticación (1008), no reintentar
        if (event.code === 1008) {
          console.error('[RealtimeService] Authentication failed - WebSocket rejected connection');
      
          this.updateState({
            connection_state: 'error',
            is_connected: false,
            last_error: 'Authentication failed'
          });
          this.stopHeartbeat();
          return;
        }

    
        this.updateState({
          connection_state: 'disconnected',
          is_connected: false
        });
        this.stopHeartbeat();
        this.attemptReconnect();
      };
    } catch (error) {
      console.error('[RealtimeService] Connection error:', error);
  
      this.updateState({
        connection_state: 'error',
        last_error: String(error)
      });
      throw error;
    }
  }

  /**
   * Desconecta del WebSocket
   */
  disconnect(): void {
    if (this.ws) {
      this.stopHeartbeat();
      this.ws.close();
      this.ws = null;
    }


    this.projectId = null;
    this.reconnectAttempts = 0;
    this.updateState({
      connection_state: 'disconnected',
      is_connected: false,
      online_users: []
    });
  }

  /**
   * Suscribe a eventos de presencia de usuarios
   */
  subscribeToUserPresence(callback: RealtimeCallback<OnlineUser[]>): UnsubscribeFn {
    return this.subscribe('user_presence', callback as RealtimeCallback);
  }

  /**
   * Suscribe a eventos de locks
   */
  subscribeToLocks(callback: RealtimeCallback<Lock>): UnsubscribeFn {
    return this.subscribe('entity_locked', callback as RealtimeCallback);
  }

  /**
   * Suscribe a eventos de comentarios en una entidad
   */
  subscribeToComments(entityId: string, callback: RealtimeCallback<Comment>): UnsubscribeFn {
    return this.subscribe(`comment:${entityId}`, callback as RealtimeCallback);
  }

  /**
   * Suscribe a actividad del proyecto
   */
  subscribeToActivity(callback: RealtimeCallback): UnsubscribeFn {
    return this.subscribe('activity_logged', callback);
  }

  /**
   * Suscribe a eventos de mapeos (creación/eliminación)
   */
  subscribeToMappings(callback: RealtimeCallback): UnsubscribeFn {
    return this.subscribe('mappings', callback);
  }

  /**
   * Suscribe a eventos de cursores colaborativos
   */
  subscribeToCursors(callback: RealtimeCallback): UnsubscribeFn {
    return this.subscribe('cursors', callback);
  }

  /**
   * Broadcast de "usuario escribiendo"
   */
  broadcastTyping(entityId: string, entityType: string): void {
    this.send({
      type: 'typing_start',
      project_id: this.projectId!,
      timestamp: new Date().toISOString(),
      payload: {
        entity_id: entityId,
        entity_type: entityType
      }
    });
  }

  /**
   * Stop typing indicator
   */
  stopTyping(entityId: string, entityType: string): void {
    this.send({
      type: 'typing_stop',
      project_id: this.projectId!,
      timestamp: new Date().toISOString(),
      payload: {
        entity_id: entityId,
        entity_type: entityType
      }
    });
  }

  /**
   * Broadcast de posición de cursor (throttled)
   */
  private lastCursorBroadcast = 0;
  private readonly CURSOR_THROTTLE_MS = 50; // 20 fps

  broadcastCursorPosition(projectId: string, position: { x: number; y: number; tableId?: string; viewport?: { x: number; y: number; zoom: number } }): void {
    const now = Date.now();
    if (now - this.lastCursorBroadcast < this.CURSOR_THROTTLE_MS) {
      return; // Throttle
    }
    this.lastCursorBroadcast = now;

    this.send({
      type: 'cursor_move',
      project_id: projectId,
      timestamp: new Date().toISOString(),
      payload: {
        x: position.x,
        y: position.y,
        tableId: position.tableId,
        viewport: position.viewport
      }
    });
  }

  /**
   * Broadcast cuando el cursor sale del canvas
   */
  broadcastCursorLeave(projectId: string): void {
    this.send({
      type: 'cursor_leave',
      project_id: projectId,
      timestamp: new Date().toISOString(),
      payload: {}
    });
  }

  /**
   * Obtiene el estado actual
   */
  getState(): WebSocketState {
    return { ...this.state };
  }

  /**
   * Verifica si está conectado
   */
  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  // ==================== Métodos privados ====================

  /**
   * Envía un mensaje al WebSocket
   */
  private send(message: RealtimeMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
      console.log(`[RealtimeService] Message sent: ${message.type}`);
    } else {
      const state = this.ws ? `readyState=${this.ws.readyState}` : 'ws=null';
      console.warn(`[RealtimeService] Cannot send message (type: ${message.type}), not connected (${state})`);
    }
  }

  /**
   * Maneja mensajes entrantes
   */
  private handleMessage(message: RealtimeMessage): void {
    console.log('[RealtimeService] Message received:', message.type);

    switch (message.type) {
      case 'hello': {
        const helloPayload = message.payload as { online_users: OnlineUser[] } | undefined;
        this.state.online_users = helloPayload?.online_users || [];
        this.notifySubscribers('user_presence', this.state.online_users);
        break;
      }

      case 'user_joined':
      case 'user_left':
      case 'user_presence': {
        const presencePayload = message.payload as { user?: OnlineUser } | undefined;
        if (presencePayload?.user) {
          this.updateOnlineUsers(message);
        }
        this.notifySubscribers('user_presence', this.state.online_users);
        break;
      }

      case 'entity_locked':
      case 'entity_unlocked': {
        const lockPayload = message.payload as { lock?: unknown } | undefined;
        this.notifySubscribers('entity_locked', lockPayload?.lock);
        break;
      }

      case 'comment_added':
      case 'comment_updated':
      case 'comment_deleted':
      case 'comment_resolved': {
        const commentPayload = message.payload as { comment?: { entity_id: string } } | undefined;
        const comment = commentPayload?.comment;
        if (comment) {
          this.notifySubscribers(`comment:${comment.entity_id}`, comment);
        }
        break;
      }

      case 'activity_logged': {
        const activityPayload = message.payload as { activity?: unknown } | undefined;
        this.notifySubscribers('activity_logged', activityPayload?.activity);
        break;
      }

      case 'version_created':
        this.notifySubscribers('version_created', message.payload);
        break;

      case 'typing_start':
      case 'typing_stop':
        this.notifySubscribers('typing', message.payload);
        break;

      case 'mapping_added':
      case 'mapping_deleted':
        this.notifySubscribers('mappings', message);
        break;

      case 'cursor_move':
      case 'cursor_leave':
        // Backend sends cursor data directly in message, not in payload
        this.notifySubscribers('cursors', message);
        break;

      case 'pong':
        // Heartbeat response
        break;

      default:
        console.warn('[RealtimeService] Unknown message type:', message.type);
    }
  }

  /**
   * Actualiza lista de usuarios online
   */
  private updateOnlineUsers(message: RealtimeMessage): void {
    const user = (message.payload as { user: OnlineUser } | undefined)?.user;

    if (!user) return;

    if (message.type === 'user_joined') {
      const exists = this.state.online_users.some(u => u.user_id === user.user_id);
      if (!exists) {
        this.state.online_users.push(user);
      }
    } else if (message.type === 'user_left') {
      this.state.online_users = this.state.online_users.filter(
        u => u.user_id !== user.user_id
      );
    }
  }

  /**
   * Suscribe a un tipo de evento
   */
  private subscribe(eventType: string, callback: RealtimeCallback): UnsubscribeFn {
    if (!this.subscribers.has(eventType)) {
      this.subscribers.set(eventType, new Set());
    }

    this.subscribers.get(eventType)!.add(callback);
    console.log(`[RealtimeService] Subscribed to '${eventType}'. Total subscribers: ${this.subscribers.get(eventType)!.size}`);

    // Retorna función para desuscribirse
    return () => {
      const callbacks = this.subscribers.get(eventType);
      if (callbacks) {
        callbacks.delete(callback);
        console.log(`[RealtimeService] Unsubscribed from '${eventType}'. Remaining subscribers: ${callbacks.size}`);
        if (callbacks.size === 0) {
          this.subscribers.delete(eventType);
        }
      }
    };
  }

  /**
   * Notifica a los subscribers de un evento
   */
  private notifySubscribers(eventType: string, data: unknown): void {
    const callbacks = this.subscribers.get(eventType);
    if (callbacks) {
      console.log(`[RealtimeService] Notifying ${callbacks.size} subscriber(s) for event '${eventType}'`);
      callbacks.forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error('[RealtimeService] Error in subscriber callback:', error);
        }
      });
    }
  }

  /**
   * Actualiza el estado interno
   */
  private updateState(updates: Partial<WebSocketState>): void {
    this.state = { ...this.state, ...updates };
    this.notifySubscribers('state_change', this.state);
  }

  /**
   * Intenta reconectar
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[RealtimeService] Max reconnect attempts reached');
      this.updateState({ connection_state: 'error', last_error: 'Max reconnect attempts' });
      return;
    }

    if (!this.projectId) {
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    console.log(`[RealtimeService] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    this.updateState({ reconnect_attempt: this.reconnectAttempts });

    setTimeout(() => {
      if (this.projectId) {
        this.connect(this.projectId);
      }
    }, delay);
  }

  /**
   * Inicia heartbeat
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();

    this.heartbeatInterval = setInterval(() => {
      this.send({
        type: 'ping',
        project_id: this.projectId!,
        timestamp: new Date().toISOString()
      });
    }, 30000); // 30 segundos
  }

  /**
   * Detiene heartbeat
   */
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Obtiene URL del WebSocket
   * La autenticación se maneja mediante cookies (session cookie)
   */
  private getWebSocketUrl(projectId: string): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';

    // Usar el mismo host del backend que las APIs REST
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const host = apiUrl.replace(/^https?:\/\//, '');

    console.log(`[RealtimeService] Building WebSocket URL - protocol: ${protocol}, host: ${host}`);

    return `${protocol}//${host}/ws/projects/${projectId}`;
  }
}

// Exportar instancia singleton
export const realtimeService = new RealtimeService();
export default RealtimeService;
