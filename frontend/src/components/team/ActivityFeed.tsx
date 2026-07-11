// src/components/team/ActivityFeed.tsx
import React, { useState, useEffect } from 'react';
import { Activity as ActivityIcon, Loader2, RefreshCw, GitBranch, FileEdit, Trash2, UserPlus, UserMinus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { type TFunction } from 'i18next';
import { Button } from '../ui/button';
import { activityService } from '../../services/activity_service';
import type { Activity } from '../../services/activity_service';
import { toast } from '../../utils/toast';

interface ActivityFeedProps {
  projectId?: string;
  limit?: number;
}

function getActivityMessage(activity: Activity, t: TFunction<['team', 'common']>): string {
  const user = activity.user_username || activity.user_email?.split('@')[0] || 'Usuario';
  const entityTypeMap: Record<string, string> = {
    project: t('activity.entity.project'),
    mapping: t('activity.entity.mapping'),
    table: t('activity.entity.table'),
    column: t('activity.entity.column'),
    member: t('activity.entity.member'),
  };
  const entity = entityTypeMap[activity.entity_type] ?? activity.entity_type;

  switch (activity.activity_type) {
    case 'created': return t('activity.event.created', { user, entity });
    case 'updated': return t('activity.event.updated', { user, entity });
    case 'deleted': return t('activity.event.deleted', { user, entity });
    case 'member_added': return t('activity.event.memberAdded', { user });
    case 'member_removed': return t('activity.event.memberRemoved', { user });
    case 'role_updated': return t('activity.event.roleUpdated', { user });
    case 'version_created': return t('activity.event.versionCreated', { user });
    case 'version_restored': return t('activity.event.versionRestored', { user });
    default: return t('activity.event.unknown', { user });
  }
}

function formatTime(dateString: string, t: TFunction<['team', 'common']>): string {
  const date = new Date(dateString);
  const diff = Math.floor((Date.now() - date.getTime()) / 60000);
  const hours = Math.floor(diff / 60);
  const days = Math.floor(hours / 24);
  if (diff < 1) return t('common:time.now');
  if (diff < 60) return t('common:time.minutes', { count: diff });
  if (hours < 24) return t('common:time.hours', { count: hours });
  return t('common:time.days', { count: days });
}

export const ActivityFeed: React.FC<ActivityFeedProps> = ({ projectId, limit = 20 }) => {
  const { t } = useTranslation<['team', 'common']>(['team', 'common']);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    loadActivities();
  }, [projectId]);

  const loadActivities = async (showRefreshLoader = false) => {
    try {
      if (showRefreshLoader) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }

      const data = projectId
        ? await activityService.getProjectActivity(projectId, { limit })
        : await activityService.getGlobalActivity({ limit });
      setActivities(data);
    } catch (error: unknown) {
      console.error('Error loading activities:', error);
      toast.error(t('activity.errors.load'));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  const handleRefresh = () => {
    loadActivities(true);
  };

  const getActivityIcon = (type: string) => {
    const icons: Record<string, React.ReactElement> = {
      created: <FileEdit className="w-4 h-4 text-green-500" />,
      updated: <FileEdit className="w-4 h-4 text-blue-500" />,
      deleted: <Trash2 className="w-4 h-4 text-red-500" />,
      member_added: <UserPlus className="w-4 h-4 text-green-500" />,
      member_removed: <UserMinus className="w-4 h-4 text-red-500" />,
      version_created: <GitBranch className="w-4 h-4 text-purple-500" />,
      version_restored: <GitBranch className="w-4 h-4 text-orange-500" />
    };
    return icons[type] || <ActivityIcon className="w-4 h-4 text-gray-500" />;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">{t('activity.title')}</h3>
          <p className="text-sm text-muted-foreground">
            {projectId ? t('activity.subtitle.project') : t('activity.subtitle.all')}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          {t('activity.refresh')}
        </Button>
      </div>

      {/* Activity List */}
      <div className="space-y-1">
        {activities.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <ActivityIcon className="w-12 h-12 mx-auto mb-2 opacity-20" />
            <p>{t('activity.empty')}</p>
          </div>
        ) : (
          activities.map((activity) => (
            <div
              key={activity.id}
              className="flex items-start gap-3 p-3 rounded-lg hover:bg-muted/50 transition-colors"
            >
              {/* Icon */}
              <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center flex-shrink-0 mt-0.5">
                {getActivityIcon(activity.activity_type)}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm">{getActivityMessage(activity, t)}</p>
                {!!(activity.metadata?.message) && (
                  <p className="text-xs text-muted-foreground mt-0.5 truncate">
                    {String(activity.metadata.message)}
                  </p>
                )}
              </div>

              {/* Time */}
              <span className="text-xs text-muted-foreground flex-shrink-0">
                {formatTime(activity.created_at, t)}
              </span>
            </div>
          ))
        )}
      </div>

      {/* Load More */}
      {activities.length >= limit && (
        <div className="text-center pt-2">
          <Button variant="ghost" size="sm" className="text-xs">
            {t('activity.viewMore')}
          </Button>
        </div>
      )}
    </div>
  );
};
