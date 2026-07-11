# Version Control & Collaboration UI Components

Comprehensive set of React components for version control, collaboration, and real-time features.

## Components Overview

### 1. PermissionGuard (HOC)
Higher-Order Component for protecting UI elements based on user permissions.

**Usage:**
```tsx
import { PermissionGuard } from './version_control';

// Protect a button
<PermissionGuard userRole={user.role} requiredPermission="edit:mapping">
  <Button>Edit Mapping</Button>
</PermissionGuard>

// With fallback
<PermissionGuard
  userRole={user.role}
  requiredPermission="delete:mapping"
  fallback={<span>No tienes permiso</span>}
>
  <Button variant="destructive">Delete</Button>
</PermissionGuard>

// Using the hook
const { can, permissions } = usePermissionGuard(user.role);
{can('edit:mapping') && <Button>Edit</Button>}
```

**Props:**
- `userRole?: Role` - User's role (admin, editor, viewer)
- `requiredPermission?: string` - Single permission to check (e.g., "edit:mapping")
- `requiredPermissions?: Permissions` - Multiple permissions (must have all)
- `fallback?: ReactNode` - Element to show if permission denied
- `onUnauthorized?: () => void` - Callback when access is denied

---

### 2. EntityLockIndicator
Visual indicator for entity lock status with color coding.

**Usage:**
```tsx
import { EntityLockIndicator, LockStatusBadge } from './version_control';

// Badge variant (default)
<EntityLockIndicator
  lock={lockInfo}
  currentUserId={user.id}
  variant="badge"
  showDetails
/>

// Inline variant
<EntityLockIndicator
  lock={lockInfo}
  currentUserId={user.id}
  variant="inline"
/>

// Detailed card variant
<EntityLockIndicator
  lock={lockInfo}
  currentUserId={user.id}
  variant="detailed"
  showDetails
/>

// Status badge
<LockStatusBadge status="active" />
```

**Props:**
- `lock: Lock | null` - Lock information
- `currentUserId?: string` - Current user ID to check ownership
- `variant?: 'badge' | 'inline' | 'detailed'` - Display style
- `showDetails?: boolean` - Show additional details
- `className?: string` - Additional CSS classes

**Color Coding:**
- 🟢 Green: User owns the lock
- 🔴 Red: Locked by another user
- ⚪ Gray: Not locked

---

### 3. UserPresenceIndicator
Shows user online/offline status with real-time updates.

**Usage:**
```tsx
import {
  UserPresenceIndicator,
  UserPresenceList,
  OnlineCount
} from './version_control';

// Single user - dot only
<UserPresenceIndicator user={onlineUser} variant="dot" />

// Badge with username
<UserPresenceIndicator user={onlineUser} variant="badge" showLastSeen />

// Full card
<UserPresenceIndicator user={onlineUser} variant="card" showLastSeen />

// List of users
<UserPresenceList users={onlineUsers} variant="card" maxDisplay={5} />

// Online count
<OnlineCount count={onlineUsers.length} />
```

**Props (UserPresenceIndicator):**
- `user: OnlineUser` - User object with status
- `variant?: 'dot' | 'badge' | 'card'` - Display style
- `showLastSeen?: boolean` - Show last seen timestamp
- `className?: string` - Additional CSS classes

**Props (UserPresenceList):**
- `users: OnlineUser[]` - Array of users
- `maxDisplay?: number` - Maximum users to show (default: 5)
- `variant?: 'dot' | 'badge' | 'card'` - Display style for each user
- `className?: string` - Additional CSS classes

---

### 4. VersionHistory
Timeline view of entity versions with comparison and restore capabilities.

**Usage:**
```tsx
import { VersionHistory } from './version_control';

<VersionHistory
  versions={versions}
  currentVersionId={currentVersion?.id}
  onRestore={handleRestore}
  onCompare={handleCompare}
  onViewDetails={handleViewDetails}
  onAddTag={handleAddTag}
  onDeleteVersion={handleDelete}
  canRestore={hasPermission}
  canDelete={isAdmin}
/>
```

**Props:**
- `versions: Version[]` - Array of versions
- `currentVersionId?: string` - ID of current active version
- `onRestore?: (version) => void` - Restore version callback
- `onCompare?: (versionA, versionB) => void` - Compare callback
- `onViewDetails?: (version) => void` - View details callback
- `onAddTag?: (versionId) => void` - Add tag callback
- `onDeleteVersion?: (versionId) => void` - Delete version callback
- `loading?: boolean` - Loading state
- `canRestore?: boolean` - Show restore buttons
- `canDelete?: boolean` - Show delete buttons
- `className?: string` - Additional CSS classes

**Features:**
- Chronological timeline with connecting lines
- Change type indicators (create, update, delete)
- Version comparison selection
- Tag display and management
- Expandable details
- Permission-based actions

---

### 5. VersionCompare
Side-by-side comparison of two versions with diff highlighting.

**Usage:**
```tsx
import { VersionCompare } from './version_control';

<VersionCompare
  versionA={olderVersion}
  versionB={newerVersion}
  onClose={() => setComparing(false)}
/>
```

**Props:**
- `versionA: Version` - Older version (left side)
- `versionB: Version` - Newer version (right side)
- `onClose?: () => void` - Close callback
- `className?: string` - Additional CSS classes

**Features:**
- Deep diff algorithm
- Added/removed/modified sections
- Type-aware value rendering
- Collapsible diff sections
- Metadata comparison

**Diff Colors:**
- 🟢 Green: Added fields
- 🔴 Red: Removed fields
- 🔵 Blue: Modified fields

---

### 6. CommentThread
Threaded comments with replies, @mentions, and emoji reactions.

**Usage:**
```tsx
import { CommentThread } from './version_control';

<CommentThread
  comments={comments}
  currentUserId={user.id}
  onAddComment={handleAddComment}
  onEditComment={handleEditComment}
  onDeleteComment={handleDeleteComment}
  onAddReaction={handleAddReaction}
  onRemoveReaction={handleRemoveReaction}
  placeholder="Escribe tu comentario..."
  maxDepth={3}
/>
```

**Props:**
- `comments: Comment[]` - Array of comments
- `currentUserId?: string` - Current user ID
- `onAddComment?: (content, parentId?) => Promise<void>` - Add comment callback
- `onEditComment?: (commentId, content) => Promise<void>` - Edit callback
- `onDeleteComment?: (commentId) => Promise<void>` - Delete callback
- `onAddReaction?: (commentId, emoji) => Promise<void>` - Add reaction callback
- `onRemoveReaction?: (commentId, emoji) => Promise<void>` - Remove reaction callback
- `placeholder?: string` - Input placeholder text
- `maxDepth?: number` - Maximum nesting depth (default: 3)
- `className?: string` - Additional CSS classes

**Features:**
- Nested replies with visual threading
- @mention support with highlighting
- Emoji reactions (grouped by type)
- Edit/delete for own comments
- Optimistic updates
- Tree structure building

---

### 7. ActivityFeed
Chronological feed of project activities with filtering and grouping.

**Usage:**
```tsx
import { ActivityFeed } from './version_control';

<ActivityFeed
  activities={activities}
  groupByDate
  showFilters
  maxItems={50}
  onLoadMore={loadMoreActivities}
  loading={isLoading}
  hasMore={hasMoreItems}
/>
```

**Props:**
- `activities: Activity[]` - Array of activities
- `groupByDate?: boolean` - Group by date (default: true)
- `showFilters?: boolean` - Show filter buttons
- `maxItems?: number` - Maximum activities to display
- `onLoadMore?: () => void` - Load more callback (infinite scroll)
- `loading?: boolean` - Loading state
- `hasMore?: boolean` - More items available
- `className?: string` - Additional CSS classes

**Activity Types:**
- `version_created`, `version_restored`, `version_tagged`
- `lock_acquired`, `lock_released`
- `comment_created`, `comment_edited`, `comment_deleted`
- `member_added`, `member_removed`, `role_changed`

**Features:**
- Date grouping (Today, Yesterday, dates)
- Type-based filtering
- Color-coded activity icons
- Timeline connector lines
- Load more / infinite scroll

---

### 8. CollaborationPanel (Complete Integration)
Unified panel combining all collaboration features in a tabbed interface.

**Usage:**
```tsx
import { CollaborationPanel } from './version_control';

<CollaborationPanel
  projectId={project.id}
  entityId={entity.id}
  entityType="mapping"
  onClose={handleClose}
/>
```

**Props:**
- `projectId: string` - Project ID for WebSocket connection
- `entityId: string` - Entity being collaborated on
- `entityType: string` - Type of entity (e.g., "mapping", "table")
- `onClose?: () => void` - Close panel callback
- `className?: string` - Additional CSS classes

**Features:**
- Four tabs: Users, Comments, Versions, Activity
- Real-time connection status
- Entity lock management
- Inline version comparison
- Permission-based UI
- Complete integration example

**Tabs:**
1. **Users**: Live presence with UserPresenceList
2. **Comments**: Full CommentThread with reactions
3. **Versions**: VersionHistory with comparison
4. **Activity**: ActivityFeed with filters

---

## Styling

All components use CSS Modules located in `src/styles/version_control/`:

- `lock-indicator.module.css`
- `presence-indicator.module.css`
- `version-history.module.css`
- `version-compare.module.css`
- `comment-thread.module.css`
- `activity-feed.module.css`
- `collaboration-panel.module.css`

### Theme Support
All components support light/dark mode through CSS variables:
- `--foreground`, `--background`
- `--card`, `--muted`, `--border`
- `--primary`, `--destructive`

### Responsive Design
All components are mobile-responsive with breakpoints at:
- `640px` (sm) - Mobile adjustments
- `768px` (md) - Tablet adjustments

---

## Integration with Hooks

These components are designed to work seamlessly with the custom hooks:

```tsx
import { useEntityLock } from '../../hooks/version_control/useEntityLock';
import { useVersionControl } from '../../hooks/version_control/useVersionControl';
import { useComments } from '../../hooks/version_control/useComments';
import { useRealtimeSync } from '../../hooks/version_control/useRealtimeSync';

function MyComponent({ entityId, projectId }) {
  // Locking
  const { isLocked, isLockedByMe, lockInfo, acquireLock, releaseLock } =
    useEntityLock(entityId, 'mapping');

  // Versions
  const { versions, loading, createVersion, restoreVersion } =
    useVersionControl(entityId, 'mapping');

  // Comments
  const { comments, addComment, editComment, deleteComment, addReaction } =
    useComments(entityId, 'mapping');

  // Real-time
  const { onlineUsers, isConnected, subscribe } =
    useRealtimeSync(projectId);

  return (
    <>
      <EntityLockIndicator lock={lockInfo} currentUserId={user.id} />
      <UserPresenceList users={onlineUsers} />
      <VersionHistory versions={versions} onRestore={restoreVersion} />
      <CommentThread comments={comments} onAddComment={addComment} />
    </>
  );
}
```

---

## Example: Full Integration

```tsx
import React from 'react';
import { CollaborationPanel } from './version_control';

function MappingView({ projectId, mappingId }) {
  const [showCollaboration, setShowCollaboration] = React.useState(false);

  return (
    <div className="mapping-container">
      <header>
        <h1>Data Mapping</h1>
        <button onClick={() => setShowCollaboration(!showCollaboration)}>
          Toggle Collaboration
        </button>
      </header>

      <main className="mapping-canvas">
        {/* Your mapping UI */}
      </main>

      {showCollaboration && (
        <aside className="collaboration-sidebar">
          <CollaborationPanel
            projectId={projectId}
            entityId={mappingId}
            entityType="mapping"
            onClose={() => setShowCollaboration(false)}
          />
        </aside>
      )}
    </div>
  );
}
```

---

## Accessibility

All components follow accessibility best practices:
- Semantic HTML elements
- ARIA labels and roles
- Keyboard navigation support
- Focus management
- Screen reader friendly

---

## Performance

Optimization techniques used:
- React.memo for expensive components
- useMemo for computed values
- useCallback for event handlers
- Virtualization ready (ActivityFeed, VersionHistory)
- Lazy loading support

---

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

---

## Dependencies

- React 19+
- Lucide React (icons)
- class-variance-authority (button variants)
- Radix UI primitives (via shadcn/ui)

---

## File Structure

```
src/
├── components/
│   └── version_control/
│       ├── PermissionGuard.tsx
│       ├── EntityLockIndicator.tsx
│       ├── UserPresenceIndicator.tsx
│       ├── VersionHistory.tsx
│       ├── VersionCompare.tsx
│       ├── CommentThread.tsx
│       ├── ActivityFeed.tsx
│       ├── CollaborationPanel.tsx
│       ├── index.ts (barrel exports)
│       └── README.md (this file)
└── styles/
    └── version_control/
        ├── lock-indicator.module.css
        ├── presence-indicator.module.css
        ├── version-history.module.css
        ├── version-compare.module.css
        ├── comment-thread.module.css
        ├── activity-feed.module.css
        └── collaboration-panel.module.css
```

---

## Next Steps

To complete the collaboration system:

1. **Backend Endpoints** - Implement FastAPI endpoints for:
   - Version CRUD operations
   - Lock management
   - Comment operations
   - Activity feed

2. **Real-time Integration** - Ensure WebSocket events are properly handled

3. **Testing** - Add unit and integration tests for components

4. **Documentation** - Add Storybook stories for component showcase

---

## Support

For questions or issues, refer to:
- Main documentation: `/COLLABORATION_SYSTEM_README.md`
- Types documentation: `/src/types/version_control_types.ts`
- Hooks documentation: `/src/hooks/version_control/`
- Utils documentation: `/src/utils/version_control/`
