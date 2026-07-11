// src/components/version_control/ActivityFeed.tsx
import React, { useMemo } from 'react';
import {
  Activity as ActivityIcon,
  User,
  Clock,
  GitBranch,
  Lock,
  MessageSquare,
  Tag,
  UserPlus,
  UserMinus,
  Edit,
  Trash2,
  Plus,
  FileText,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Activity, ActivityType } from '../../types/version_control_types';
import { Button } from '../ui/button';
import styles from '../../styles/version_control/activity-feed.module.css';

interface ActivityDateGroup {
  date: string;
  activities: Activity[];
}

interface ActivityFeedProps {
  activities: Activity[];
  groupByDate?: boolean;
  showFilters?: boolean;
  maxItems?: number;
  onLoadMore?: () => void;
  loading?: boolean;
  hasMore?: boolean;
  className?: string;
}

export const ActivityFeed: React.FC<ActivityFeedProps> = ({
  activities,
  groupByDate = true,
  showFilters = false,
  maxItems,
  onLoadMore,
  loading = false,
  hasMore = false,
  className = ''
}) => {
  const { t, i18n } = useTranslation('version_control');
  const [filterType, setFilterType] = React.useState<ActivityType | 'all'>('all');

  const filteredActivities = useMemo(() => {
    let filtered = activities;
    if (filterType !== 'all') {
      filtered = filtered.filter((a) => a.activity_type === filterType);
    }
    if (maxItems) {
      filtered = filtered.slice(0, maxItems);
    }
    return filtered;
  }, [activities, filterType, maxItems]);

  const groupedActivities = useMemo(() => {
    if (!groupByDate) return null;

    const groups: ActivityDateGroup[] = [];
    const dateMap = new Map<string, Activity[]>();

    filteredActivities.forEach((activity) => {
      const date = new Date(activity.created_at);
      const dateKey = date.toISOString().split('T')[0];

      if (!dateMap.has(dateKey)) {
        dateMap.set(dateKey, []);
      }
      dateMap.get(dateKey)!.push(activity);
    });

    dateMap.forEach((acts, date) => {
      groups.push({ date, activities: acts });
    });

    return groups.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  }, [filteredActivities, groupByDate]);

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return t('activityFeed.today');
    }
    if (date.toDateString() === yesterday.toDateString()) {
      return t('activityFeed.yesterday');
    }

    return date.toLocaleDateString(i18n.language, {
      day: 'numeric',
      month: 'long',
      year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined
    });
  };

  const formatTime = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString(i18n.language, {
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getActivityConfig = (type: ActivityType) => {
    const configs: Record<
      ActivityType,
      { icon: React.ElementType; label: string; className: string }
    > = {
      version_created: {
        icon: GitBranch,
        label: t('activityFeed.types.version_created'),
        className: styles.activityVersion
      },
      version_restored: {
        icon: GitBranch,
        label: t('activityFeed.types.version_restored'),
        className: styles.activityVersion
      },
      tag_created: {
        icon: Tag,
        label: t('activityFeed.types.tag_created'),
        className: styles.activityTag
      },
      lock_acquired: {
        icon: Lock,
        label: t('activityFeed.types.lock_acquired'),
        className: styles.activityLock
      },
      lock_released: {
        icon: Lock,
        label: t('activityFeed.types.lock_released'),
        className: styles.activityUnlock
      },
      comment_added: {
        icon: MessageSquare,
        label: t('activityFeed.types.comment_added'),
        className: styles.activityComment
      },
      member_added: {
        icon: UserPlus,
        label: t('activityFeed.types.member_added'),
        className: styles.activityMember
      },
      member_removed: {
        icon: UserMinus,
        label: t('activityFeed.types.member_removed'),
        className: styles.activityMember
      },
      member_role_changed: {
        icon: User,
        label: t('activityFeed.types.member_role_changed'),
        className: styles.activityMember
      },
      project_updated: {
        icon: Edit,
        label: t('activityFeed.types.project_updated'),
        className: styles.activityEdit
      },
      mapping_created: {
        icon: Plus,
        label: t('activityFeed.types.mapping_created'),
        className: styles.activityVersion
      },
      mapping_updated: {
        icon: Edit,
        label: t('activityFeed.types.mapping_updated'),
        className: styles.activityEdit
      },
      mapping_deleted: {
        icon: Trash2,
        label: t('activityFeed.types.mapping_deleted'),
        className: styles.activityDelete
      },
      table_imported: {
        icon: FileText,
        label: t('activityFeed.types.table_imported'),
        className: styles.activityVersion
      }
    };
    return configs[type] || {
      icon: ActivityIcon,
      label: t('activityFeed.types.default'),
      className: styles.activityDefault
    };
  };

  const renderActivity = (activity: Activity) => {
    const config = getActivityConfig(activity.activity_type);
    const Icon = config.icon;

    return (
      <div key={activity.id} className={styles.activityItem}>
        <div className={`${styles.activityIcon} ${config.className}`}>
          <Icon size={16} />
        </div>

        <div className={styles.activityContent}>
          <div className={styles.activityHeader}>
            <span className={styles.activityUser}>{activity.username}</span>
            <span className={styles.activityAction}>{config.label}</span>
          </div>

          {activity.description && (
            <div className={styles.activityDetails}>{activity.description}</div>
          )}

          <div className={styles.activityMeta}>
            <Clock size={12} />
            <span>{formatTime(activity.created_at)}</span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className={`${styles.container} ${className}`}>
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <ActivityIcon size={20} />
          <h3 className={styles.title}>{t('activityFeed.title')}</h3>
        </div>

        {showFilters && (
          <div className={styles.filters}>
            <Button
              size="sm"
              variant={filterType === 'all' ? 'default' : 'ghost'}
              onClick={() => setFilterType('all')}
            >
              {t('activityFeed.filters.all')}
            </Button>
            <Button
              size="sm"
              variant={filterType === 'version_created' ? 'default' : 'ghost'}
              onClick={() => setFilterType('version_created')}
            >
              <GitBranch size={14} />
              {t('activityFeed.filters.versions')}
            </Button>
            <Button
              size="sm"
              variant={filterType === 'comment_added' ? 'default' : 'ghost'}
              onClick={() => setFilterType('comment_added')}
            >
              <MessageSquare size={14} />
              {t('activityFeed.filters.comments')}
            </Button>
            <Button
              size="sm"
              variant={filterType === 'lock_acquired' ? 'default' : 'ghost'}
              onClick={() => setFilterType('lock_acquired')}
            >
              <Lock size={14} />
              {t('activityFeed.filters.locks')}
            </Button>
          </div>
        )}
      </div>

      <div className={styles.feed}>
        {loading && filteredActivities.length === 0 ? (
          <div className={styles.loading}>{t('activityFeed.loading')}</div>
        ) : filteredActivities.length === 0 ? (
          <div className={styles.empty}>
            <FileText size={48} />
            <p>{t('activityFeed.empty')}</p>
          </div>
        ) : groupByDate && groupedActivities ? (
          groupedActivities.map((group) => (
            <div key={group.date} className={styles.dateGroup}>
              <div className={styles.dateHeader}>
                <span className={styles.dateLabel}>{formatDate(group.date)}</span>
                <div className={styles.dateLine} />
              </div>
              <div className={styles.activityList}>
                {group.activities.map((activity) => renderActivity(activity))}
              </div>
            </div>
          ))
        ) : (
          <div className={styles.activityList}>
            {filteredActivities.map((activity) => renderActivity(activity))}
          </div>
        )}

        {hasMore && onLoadMore && (
          <div className={styles.loadMore}>
            <Button
              variant="outline"
              onClick={onLoadMore}
              disabled={loading}
            >
              {loading ? t('activityFeed.loadingMore') : t('history.loadMore')}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
