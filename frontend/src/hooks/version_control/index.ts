// src/hooks/version_control/index.ts
// Barrel file para exportar todos los hooks

export { useVersionControl } from './useVersionControl';
export { useEntityLock } from './useEntityLock';
export { useComments } from './useComments';
export { useRealtimeSync } from './useRealtimeSync';

// Re-exportar defaults
export { default as _useVersionControl } from './useVersionControl';
export { default as _useEntityLock } from './useEntityLock';
export { default as _useComments } from './useComments';
export { default as _useRealtimeSync } from './useRealtimeSync';
