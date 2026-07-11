// src/types/locking_types.ts

/**
 * Lock de una entidad
 */
export interface Lock {
  id: string;
  entity_id: string;
  entity_type: string;
  project_id: string;
  user_id: string;
  username: string;
  user_email?: string;
  user_avatar?: string;
  acquired_at: string;
  expires_at: string;
  last_heartbeat: string;
  reason?: string;
}

/**
 * Estado de lock de una entidad
 */
export interface LockStatus {
  is_locked: boolean;
  lock?: Lock;
  can_edit: boolean;
  can_force_unlock: boolean;
  is_locked_by_me: boolean;
}

/**
 * Estado de un lock individual (para badges)
 */
export type LockState = 'active' | 'expired' | 'released';

/**
 * Request para adquirir lock
 */
export interface AcquireLockRequest {
  entity_id: string;
  entity_type: string;
  duration?: number; // Duración en segundos, default 900 (15 min)
}

/**
 * Request para renovar lock
 */
export interface RenewLockRequest {
  lock_id: string;
}

/**
 * Request para forzar unlock (solo admins)
 */
export interface ForceUnlockRequest {
  entity_id: string;
  entity_type: string;
  reason?: string;
}

/**
 * Response de operaciones de lock
 */
export interface LockResponse {
  success: boolean;
  message?: string;
  data?: {
    lock?: Lock;
    status?: LockStatus;
    locks?: Lock[];
  };
}

/**
 * Configuración de locks
 */
export interface LockConfig {
  default_duration: number; // segundos
  heartbeat_interval: number; // segundos
  warning_threshold: number; // segundos antes de expirar para mostrar warning
}

/**
 * Evento de lock (para WebSocket)
 */
export interface LockEvent {
  type: 'lock_acquired' | 'lock_released' | 'lock_expired' | 'lock_renewed';
  lock: Lock;
  timestamp: string;
}

/**
 * Conflicto de lock
 */
export interface LockConflict {
  entity_id: string;
  entity_type: string;
  current_lock: Lock;
  requested_by: string;
  requested_at: string;
}

/**
 * Información de lock de columna
 */
export interface ColumnLockInfo {
  tableName: string;
  columnName: string;
  isLocked: boolean;
  lockedBy?: {
    userId: string;
    username: string;
    email?: string;
    avatar?: string;
  };
  expiresAt?: string;
  isLockedByMe: boolean;
  canEdit: boolean;
}

/**
 * Helpers para locks de columnas
 */
export const makeColumnEntityId = (tableName: string, columnName: string): string => {
  return `${tableName}:${columnName}`;
};

export const parseColumnEntityId = (entityId: string): { tableName: string; columnName: string } | null => {
  const parts = entityId.split(':', 2);
  if (parts.length === 2) {
    return { tableName: parts[0], columnName: parts[1] };
  }
  return null;
};
