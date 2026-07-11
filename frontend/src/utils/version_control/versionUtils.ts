// src/utils/version_control/versionUtils.ts

import type { Version, VersionDiff, EntitySnapshot } from '@/types/versioning_types';

/**
 * Genera un hash único para una versión
 */
export const generateVersionHash = (snapshot: object): string => {
  const str = JSON.stringify(snapshot, Object.keys(snapshot).sort());
  return simpleHash(str);
};

/**
 * Hash simple (no criptográfico, solo para IDs únicos)
 */
const simpleHash = (str: string): string => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash).toString(36);
};

/**
 * Crea un snapshot JSON de una entidad
 */
export const createSnapshot = (entity: unknown): string => {
  try {
    // Ordenar keys para consistencia
    const sortedEntity = sortObjectKeys(entity);
    return JSON.stringify(sortedEntity, null, 0);
  } catch (error) {
    console.error('[versionUtils] Error creating snapshot:', error);
    throw new Error('Failed to create entity snapshot');
  }
};

/**
 * Parsea un snapshot JSON
 */
export const parseSnapshot = (snapshot: string): EntitySnapshot => {
  try {
    return JSON.parse(snapshot);
  } catch (error) {
    console.error('[versionUtils] Error parsing snapshot:', error);
    throw new Error('Failed to parse entity snapshot');
  }
};

/**
 * Ordena recursivamente las keys de un objeto
 */
const sortObjectKeys = (obj: unknown): unknown => {
  if (obj === null || typeof obj !== 'object') {
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map(sortObjectKeys);
  }

  const sorted: Record<string, unknown> = {};
  Object.keys(obj)
    .sort()
    .forEach(key => {
      sorted[key] = sortObjectKeys((obj as Record<string, unknown>)[key]);
    });

  return sorted;
};

/**
 * Calcula diferencias entre dos objetos
 */
export const calculateDiff = (oldObj: Record<string, unknown> | null | undefined, newObj: Record<string, unknown> | null | undefined, basePath = ''): VersionDiff => {
  const diff: VersionDiff = {
    added: [],
    removed: [],
    modified: []
  };

  const oldKeys = oldObj ? Object.keys(oldObj) : [];
  const newKeys = newObj ? Object.keys(newObj) : [];

  const allKeys = new Set([...oldKeys, ...newKeys]);

  allKeys.forEach(key => {
    const path = basePath ? `${basePath}.${key}` : key;
    const oldValue = oldObj?.[key];
    const newValue = newObj?.[key];

    const hasOld = oldObj && key in oldObj;
    const hasNew = newObj && key in newObj;

    if (!hasOld && hasNew) {
      // Añadido
      diff.added.push({ path, value: newValue });
    } else if (hasOld && !hasNew) {
      // Eliminado
      diff.removed.push({ path, value: oldValue });
    } else if (hasOld && hasNew) {
      // Verificar si cambió
      if (typeof oldValue === 'object' && typeof newValue === 'object' && oldValue !== null && newValue !== null) {
        // Recursivo para objetos
        const nestedDiff = calculateDiff(oldValue as Record<string, unknown>, newValue as Record<string, unknown>, path);
        diff.added.push(...nestedDiff.added);
        diff.removed.push(...nestedDiff.removed);
        diff.modified.push(...nestedDiff.modified);
      } else if (oldValue !== newValue) {
        // Valor primitivo modificado
        diff.modified.push({
          path,
          old_value: oldValue,
          new_value: newValue
        });
      }
    }
  });

  return diff;
};

/**
 * Aplica un diff a un objeto
 */
export const applyDiff = (obj: Record<string, unknown>, diff: VersionDiff): Record<string, unknown> => {
  const result = JSON.parse(JSON.stringify(obj)); // Deep clone

  // Aplicar eliminaciones
  diff.removed.forEach(entry => {
    deleteByPath(result, entry.path);
  });

  // Aplicar modificaciones
  diff.modified.forEach(entry => {
    setByPath(result, entry.path, entry.new_value);
  });

  // Aplicar adiciones
  diff.added.forEach(entry => {
    setByPath(result, entry.path, entry.value);
  });

  return result;
};

/**
 * Establece un valor en un objeto usando un path de string
 */
const setByPath = (obj: Record<string, unknown>, path: string, value: unknown): void => {
  const keys = path.split('.');
  const lastKey = keys.pop()!;

  let current: Record<string, unknown> = obj;
  for (const key of keys) {
    if (!(key in current)) {
      current[key] = {};
    }
    current = current[key] as Record<string, unknown>;
  }

  current[lastKey] = value;
};

/**
 * Elimina un valor de un objeto usando un path de string
 */
const deleteByPath = (obj: Record<string, unknown>, path: string): void => {
  const keys = path.split('.');
  const lastKey = keys.pop()!;

  let current: Record<string, unknown> = obj;
  for (const key of keys) {
    if (!(key in current)) {
      return;
    }
    current = current[key] as Record<string, unknown>;
  }

  delete current[lastKey];
};

/**
 * Formatea un mensaje de versión para display
 */
export const formatVersionMessage = (version: Version): string => {
  const action = version.change_type === 'create' ? 'creó'
    : version.change_type === 'update' ? 'actualizó'
    : 'eliminó';

  const timeAgo = formatTimeAgo(new Date(version.created_at));

  return `${version.username} ${action} ${version.entity_type} hace ${timeAgo}`;
};

/**
 * Formatea tiempo relativo (hace X minutos/horas/días)
 */
export const formatTimeAgo = (date: Date): string => {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) {
    return 'unos segundos';
  } else if (diffMins < 60) {
    return `${diffMins} ${diffMins === 1 ? 'minuto' : 'minutos'}`;
  } else if (diffHours < 24) {
    return `${diffHours} ${diffHours === 1 ? 'hora' : 'horas'}`;
  } else if (diffDays < 30) {
    return `${diffDays} ${diffDays === 1 ? 'día' : 'días'}`;
  } else {
    return date.toLocaleDateString();
  }
};

/**
 * Obtiene un color para un tipo de cambio
 */
export const getChangeTypeColor = (changeType: string): string => {
  switch (changeType) {
    case 'create':
      return '#10b981'; // green
    case 'update':
      return '#3b82f6'; // blue
    case 'delete':
      return '#ef4444'; // red
    default:
      return '#6b7280'; // gray
  }
};

/**
 * Obtiene un icono para un tipo de cambio (lucide-react icon name)
 */
export const getChangeTypeIcon = (changeType: string): string => {
  switch (changeType) {
    case 'create':
      return 'Plus';
    case 'update':
      return 'Edit';
    case 'delete':
      return 'Trash2';
    default:
      return 'FileText';
  }
};

/**
 * Agrupa versiones por día
 */
export const groupVersionsByDay = (versions: Version[]): Record<string, Version[]> => {
  const grouped: Record<string, Version[]> = {};

  versions.forEach(version => {
    const date = new Date(version.created_at);
    const dateKey = date.toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });

    if (!grouped[dateKey]) {
      grouped[dateKey] = [];
    }

    grouped[dateKey].push(version);
  });

  return grouped;
};

/**
 * Verifica si dos snapshots son idénticos
 */
export const areSnapshotsEqual = (snapshot1: string, snapshot2: string): boolean => {
  try {
    const obj1 = parseSnapshot(snapshot1);
    const obj2 = parseSnapshot(snapshot2);
    return JSON.stringify(sortObjectKeys(obj1)) === JSON.stringify(sortObjectKeys(obj2));
  } catch {
    return false;
  }
};

/**
 * Obtiene el tamaño de un diff
 */
export const getDiffSize = (diff: VersionDiff): number => {
  return diff.added.length + diff.removed.length + diff.modified.length;
};

/**
 * Verifica si un diff está vacío
 */
export const isDiffEmpty = (diff: VersionDiff): boolean => {
  return getDiffSize(diff) === 0;
};

/**
 * Formatea la fecha de una versión para visualización
 */
export const formatVersionDate = (dateStr: string): string => {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  // Hace menos de 1 minuto
  if (diffMins < 1) {
    return 'Ahora mismo';
  }

  // Hace menos de 1 hora
  if (diffMins < 60) {
    return `Hace ${diffMins} ${diffMins === 1 ? 'minuto' : 'minutos'}`;
  }

  // Hace menos de 24 horas
  if (diffHours < 24) {
    return `Hace ${diffHours} ${diffHours === 1 ? 'hora' : 'horas'}`;
  }

  // Hace menos de 7 días
  if (diffDays < 7) {
    return `Hace ${diffDays} ${diffDays === 1 ? 'día' : 'días'}`;
  }

  // Fecha completa
  return date.toLocaleDateString('es-ES', {
    day: 'numeric',
    month: 'short',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
    hour: '2-digit',
    minute: '2-digit'
  });
};
