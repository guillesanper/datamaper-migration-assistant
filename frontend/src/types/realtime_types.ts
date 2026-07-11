// src/types/realtime_types.ts

import type { Lock } from './locking_types';
import type { Comment } from './comments_types';
import type { OnlineUser, Collaborator } from './collaboration_types';
import type { Activity } from './activity_types';

/**
 * Tipos de mensajes WebSocket
 */
export type RealtimeMessageType =
  | 'hello'
  | 'user_joined'
  | 'user_left'
  | 'user_presence'
  | 'entity_locked'
  | 'entity_unlocked'
  | 'comment_added'
  | 'comment_updated'
  | 'comment_deleted'
  | 'comment_resolved'
  | 'reaction_added'
  | 'version_created'
  | 'activity_logged'
  | 'typing_start'
  | 'typing_stop'
  | 'member_added'
  | 'member_removed'
  | 'member_role_changed'
  | 'mapping_added'
  | 'mapping_deleted'
  | 'cursor_move'
  | 'cursor_leave'
  | 'ping'
  | 'pong';

/**
 * Mensaje WebSocket base
 */
export interface RealtimeMessage {
  type: RealtimeMessageType;
  project_id: string;
  actor_id?: string; // Usuario que generó el evento
  actor_name?: string;
  timestamp: string;
  payload?: unknown;
}

/**
 * Mensaje de bienvenida
 */
export interface HelloMessage extends RealtimeMessage {
  type: 'hello';
  payload: {
    project_id: string;
    actor_id: string;
    online_users: OnlineUser[];
  };
}

/**
 * Mensaje de usuario conectado/desconectado
 */
export interface UserPresenceMessage extends RealtimeMessage {
  type: 'user_joined' | 'user_left' | 'user_presence';
  payload: {
    user: OnlineUser;
    online_users_count: number;
  };
}

/**
 * Mensaje de lock
 */
export interface LockMessage extends RealtimeMessage {
  type: 'entity_locked' | 'entity_unlocked';
  payload: {
    lock: Lock;
  };
}

/**
 * Mensaje de comentario
 */
export interface CommentMessage extends RealtimeMessage {
  type: 'comment_added' | 'comment_updated' | 'comment_deleted' | 'comment_resolved';
  payload: {
    comment: Comment;
  };
}

/**
 * Mensaje de reacción
 */
export interface ReactionMessage extends RealtimeMessage {
  type: 'reaction_added';
  payload: {
    comment_id: string;
    emoji: string;
    user_id: string;
    username: string;
  };
}

/**
 * Mensaje de versión
 */
export interface VersionMessage extends RealtimeMessage {
  type: 'version_created';
  payload: {
    version_id: string;
    entity_id: string;
    entity_type: string;
    version_number: number;
  };
}

/**
 * Mensaje de actividad
 */
export interface ActivityMessage extends RealtimeMessage {
  type: 'activity_logged';
  payload: {
    activity: Activity;
  };
}

/**
 * Mensaje de typing indicator
 */
export interface TypingMessage extends RealtimeMessage {
  type: 'typing_start' | 'typing_stop';
  payload: {
    user_id: string;
    username: string;
    entity_id: string;
    entity_type: string;
  };
}

/**
 * Mensaje de miembro
 */
export interface MemberMessage extends RealtimeMessage {
  type: 'member_added' | 'member_removed' | 'member_role_changed';
  payload: {
    member: Collaborator;
    old_role?: string;
    new_role?: string;
  };
}

/**
 * Mensaje de mapeo
 */
export interface MappingMessage extends RealtimeMessage {
  type: 'mapping_added' | 'mapping_deleted';
  mapping: {
    project_id: string;
    origin_table: string;
    origin_column: string;
    destination_table: string;
    destination_column: string;
  };
}

/**
 * Posición de cursor colaborativo
 */
export interface CursorPosition {
  user_id: string;
  username: string;
  avatar?: string;
  x: number;
  y: number;
  viewport: {
    x: number;
    y: number;
    zoom: number;
  };
  timestamp: string;
}

/**
 * Mensaje de cursor
 */
export interface CursorMessage extends RealtimeMessage {
  type: 'cursor_move' | 'cursor_leave';
  payload: {
    cursor?: CursorPosition;
  };
}

/**
 * Callback de suscripción
 */
export type RealtimeCallback<T = unknown> = (message: T) => void;

/**
 * Función para desuscribirse
 */
export type UnsubscribeFn = () => void;

/**
 * Estado de conexión WebSocket
 */
export type ConnectionState = 'connecting' | 'connected' | 'disconnecting' | 'disconnected' | 'error';

/**
 * Configuración de WebSocket
 */
export interface WebSocketConfig {
  url: string;
  reconnect_attempts?: number;
  reconnect_delay?: number;
  heartbeat_interval?: number;
  connect_timeout?: number;
}

/**
 * Estado de WebSocket
 */
export interface WebSocketState {
  connection_state: ConnectionState;
  online_users: OnlineUser[];
  is_connected: boolean;
  last_error?: string;
  reconnect_attempt?: number;
}
