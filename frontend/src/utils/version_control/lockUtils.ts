// src/utils/version_control/lockUtils.ts

import type { Lock } from '@/types/locking_types';

/**
 * Duración por defecto de un lock (15 minutos en milisegundos)
 */
export const LOCK_DURATION = 15 * 60 * 1000;

/**
 * Intervalo de heartbeat (30 segundos en milisegundos)
 */
export const HEARTBEAT_INTERVAL = 30 * 1000;

/**
 * Umbral de advertencia (2 minutos antes de expirar)
 */
export const WARNING_THRESHOLD = 2 * 60 * 1000;

/**
 * Verifica si un lock ha expirado
 */
export const isLockExpired = (lock: Lock): boolean => {
  return new Date(lock.expires_at).getTime() < Date.now();
};

/**
 * Calcula el tiempo restante de un lock en milisegundos
 */
export const calculateTimeRemaining = (lock: Lock): number => {
  const expiresAt = new Date(lock.expires_at).getTime();
  return Math.max(0, expiresAt - Date.now());
};

/**
 * Formatea la duración restante de un lock
 */
export const formatLockDuration = (milliseconds: number): string => {
  const seconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`;
  } else if (minutes > 0) {
    return `${minutes} ${minutes === 1 ? 'minuto' : 'minutos'}`;
  } else {
    return `${seconds} ${seconds === 1 ? 'segundo' : 'segundos'}`;
  }
};

/**
 * Verifica si un lock está cerca de expirar
 */
export const isLockExpiringSoon = (lock: Lock): boolean => {
  const remaining = calculateTimeRemaining(lock);
  return remaining > 0 && remaining <= WARNING_THRESHOLD;
};

/**
 * Obtiene el porcentaje de tiempo transcurrido de un lock
 */
export const getLockProgress = (lock: Lock): number => {
  const acquired = new Date(lock.acquired_at).getTime();
  const expires = new Date(lock.expires_at).getTime();
  const now = Date.now();

  const total = expires - acquired;
  const elapsed = now - acquired;

  return Math.min(100, Math.max(0, (elapsed / total) * 100));
};

/**
 * Formatea el tiempo desde que se adquirió el lock
 */
export const formatLockAge = (lock: Lock): string => {
  const acquired = new Date(lock.acquired_at);
  const now = new Date();
  const diffMs = now.getTime() - acquired.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) {
    return 'hace menos de un minuto';
  } else if (diffMins === 1) {
    return 'hace 1 minuto';
  } else if (diffMins < 60) {
    return `hace ${diffMins} minutos`;
  } else {
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours === 1) {
      return 'hace 1 hora';
    } else {
      return `hace ${diffHours} horas`;
    }
  }
};

/**
 * Obtiene un mensaje descriptivo del estado del lock
 */
export const getLockStatusMessage = (lock: Lock, currentUserId: string): string => {
  const isOwnLock = lock.user_id === currentUserId;
  const remaining = formatLockDuration(calculateTimeRemaining(lock));

  if (isOwnLock) {
    return `Estás editando (quedan ${remaining})`;
  } else {
    return `${lock.username} está editando (quedan ${remaining})`;
  }
};

/**
 * Obtiene el color del indicador de lock según el estado
 */
export const getLockIndicatorColor = (lock: Lock, currentUserId: string): string => {
  const isOwnLock = lock.user_id === currentUserId;
  const isExpiringSoon = isLockExpiringSoon(lock);

  if (isOwnLock) {
    return isExpiringSoon ? '#f59e0b' : '#3b82f6'; // orange : blue
  } else {
    return '#ef4444'; // red
  }
};

/**
 * Crea un identificador único de entidad para locks
 */
export const createEntityKey = (entityId: string, entityType: string): string => {
  return `${entityType}:${entityId}`;
};

/**
 * Parsea un entity key
 */
export const parseEntityKey = (key: string): { entityId: string; entityType: string } | null => {
  const parts = key.split(':');
  if (parts.length !== 2) return null;

  return {
    entityType: parts[0],
    entityId: parts[1]
  };
};
