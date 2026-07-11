// src/services/version_control/index.ts
// Barrel file para exportar todos los servicios

export { versionControlService } from './versionControl.service';
export { lockingService } from './locking.service';
export { commentsService } from './comments.service';
export { activityService } from './activity.service';
export { realtimeService } from './realtime.service';

// Re-exportar clases para casos avanzados
export { default as VersionControlService } from './versionControl.service';
export { default as LockingService } from './locking.service';
export { default as CommentsService } from './comments.service';
export { default as ActivityService } from './activity.service';
export { default as RealtimeService } from './realtime.service';
