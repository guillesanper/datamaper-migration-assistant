// src/components/version_control/CollaborationPanel.tsx
import React, { useState } from 'react';
import { Users, MessageSquare, History, Activity as ActivityIcon, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  EntityLockIndicator,
  UserPresenceList,
  VersionHistory,
  VersionCompare,
  CommentThread,
  ActivityFeed,
  PermissionGuard
} from './index';
import { useEntityLock } from '../../hooks/version_control/useEntityLock';
import { useVersionControl } from '../../hooks/version_control/useVersionControl';
import { useComments } from '../../hooks/version_control/useComments';
import { useRealtimeSync } from '../../hooks/version_control/useRealtimeSync';
import { useAuth } from '../../providers/AuthProvider';
import { Button } from '../ui/button';
import type { Version, EntityType } from '../../types/version_control_types';
import styles from '../../styles/version_control/collaboration-panel.module.css';

interface CollaborationPanelProps {
  projectId: string;
  entityId: string;
  entityType: EntityType;
  onClose?: () => void;
  className?: string;
}

type TabType = 'users' | 'comments' | 'versions' | 'activity';

export const CollaborationPanel: React.FC<CollaborationPanelProps> = ({
  projectId,
  entityId,
  entityType,
  onClose,
  className = ''
}) => {
  const { t } = useTranslation('version_control');
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<TabType>('comments');
  const [compareVersions, setCompareVersions] = useState<{
    versionA: Version;
    versionB: Version;
  } | null>(null);

  const { isLocked, isLockedByMe, lock, acquireLock, releaseLock } = useEntityLock(
    entityId,
    entityType
  );

  const {
    versions,
    loading: versionsLoading,
    restoreVersion
  } = useVersionControl(entityId, entityType);

  const {
    comments,
    addComment,
    editComment,
    deleteComment,
    addReaction,
    removeReaction
  } = useComments(entityId, entityType);

  const { onlineUsers, isConnected } = useRealtimeSync(projectId);

  const handleCompare = (versionA: Version, versionB: Version) => {
    setCompareVersions({ versionA, versionB });
  };

  const handleRestoreVersion = async (version: Version) => {
    if (window.confirm(t('version.restoreConfirm', { tag: version.version_number }))) {
      await restoreVersion(version.id);
    }
  };

  const tabs = [
    { id: 'users' as TabType, label: t('collaboration.tabs.users'), icon: Users, count: onlineUsers.length },
    { id: 'comments' as TabType, label: t('collaboration.tabs.comments'), icon: MessageSquare, count: comments.length },
    { id: 'versions' as TabType, label: t('collaboration.tabs.versions'), icon: History, count: versions.length },
    { id: 'activity' as TabType, label: t('collaboration.tabs.activity'), icon: ActivityIcon }
  ];

  return (
    <div className={`${styles.panel} ${className}`}>
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <h3 className={styles.title}>{t('collaboration.title')}</h3>

          <EntityLockIndicator
            lock={lock}
            currentUserId={user?.id}
            variant="badge"
            showDetails
          />

          {!isConnected && (
            <span className={styles.disconnected}>{t('collaboration.disconnected')}</span>
          )}
        </div>

        {onClose && (
          <Button size="icon-sm" variant="ghost" onClick={onClose}>
            <X size={18} />
          </Button>
        )}
      </div>

      {!isLocked && (
        <div className={styles.lockActions}>
          <PermissionGuard userRole={user?.role} requiredPermission="edit:mapping">
            <Button size="sm" onClick={()=>acquireLock} className={styles.lockButton}>
              {t('collaboration.startEditing')}
            </Button>
          </PermissionGuard>
        </div>
      )}

      {isLockedByMe && (
        <div className={styles.lockActions}>
          <Button size="sm" variant="outline" onClick={() => releaseLock()}>
            {t('collaboration.stopEditing')}
          </Button>
        </div>
      )}

      <div className={styles.tabs}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
              {tab.count !== undefined && (
                <span className={styles.tabCount}>{tab.count}</span>
              )}
            </button>
          );
        })}
      </div>

      <div className={styles.content}>
        {compareVersions && (
          <div className={styles.compareOverlay}>
            <VersionCompare
              versionA={compareVersions.versionA}
              versionB={compareVersions.versionB}
              onClose={() => setCompareVersions(null)}
            />
          </div>
        )}

        {activeTab === 'users' && (
          <div className={styles.tabContent}>
            <UserPresenceList
              users={onlineUsers}
              variant="card"
              maxDisplay={50}
            />
          </div>
        )}

        {activeTab === 'comments' && (
          <div className={styles.tabContent}>
            <CommentThread
              comments={comments}
              currentUserId={user?.id}
              onAddComment={addComment}
              onEditComment={editComment}
              onDeleteComment={deleteComment}
              onAddReaction={addReaction}
              onRemoveReaction={removeReaction}
            />
          </div>
        )}

        {activeTab === 'versions' && (
          <div className={styles.tabContent}>
            <VersionHistory
              versions={versions}
              loading={versionsLoading}
              onCompare={handleCompare}
              onRestore={handleRestoreVersion}
              canRestore={isLockedByMe}
            />
          </div>
        )}

        {activeTab === 'activity' && (
          <div className={styles.tabContent}>
            <ActivityFeed
              activities={[]}
              groupByDate
              showFilters
            />
          </div>
        )}
      </div>
    </div>
  );
};
