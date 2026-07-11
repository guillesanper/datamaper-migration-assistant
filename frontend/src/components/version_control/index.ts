// src/components/version_control/index.ts
// Barrel file for version control components

// Permission & Access Control
export { PermissionGuard, usePermissionGuard } from './PermissionGuard';

// Lock Indicators
export { EntityLockIndicator, LockStatusBadge } from './EntityLockIndicator';

// User Presence
export {
  UserPresenceIndicator,
  UserPresenceList,
  OnlineCount
} from './UserPresenceIndicator';

// Version Management
export { VersionHistory } from './VersionHistory';
export { VersionCompare } from './VersionCompare';
export { VersionFilters } from './VersionFilters';
export { VersionStats } from './VersionStats';
export { TagManager } from './TagManager';
export { HelpGuide } from './HelpGuide';

// Comments
export { CommentThread } from './CommentThread';

// Activity Feed
export { ActivityFeed } from './ActivityFeed';

// Unified Panel
export { CollaborationPanel } from './CollaborationPanel';
