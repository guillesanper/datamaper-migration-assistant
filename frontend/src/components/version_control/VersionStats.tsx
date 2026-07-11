// src/components/version_control/VersionStats.tsx
import React, { useState, useEffect } from 'react';
import { GitBranch, Clock, Users, Tag as TagIcon, TrendingUp, Calendar } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Version, Tag } from '../../types/version_control_types';
import { formatVersionDate } from '../../utils/version_control/versionUtils';
import { projectService } from '../../services/project_service';
import styles from '../../styles/version_control/version-stats.module.css';

interface VersionStatsProps {
  versions: Version[];
  tags: Tag[];
  projectId: string;
  className?: string;
}

export const VersionStats: React.FC<VersionStatsProps> = ({
  versions,
  tags,
  projectId,
  className = ''
}) => {
  const { t, i18n } = useTranslation('version_control');
  const [totalCollaborators, setTotalCollaborators] = useState<number>(0);

  useEffect(() => {
    const loadCollaborators = async () => {
      try {
        const members = await projectService.getProjectMembers(projectId);
        setTotalCollaborators(members.length + 1);
      } catch (error) {
        console.error('[VersionStats] Error loading collaborators:', error);
        setTotalCollaborators(new Set(versions.map(v => v.user_id)).size);
      }
    };

    loadCollaborators();
  }, [projectId, versions]);

  const totalVersions = versions.length;
  const totalTags = tags.length;

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const versionsToday = versions.filter(v =>
    new Date(v.created_at) >= todayStart
  ).length;

  const lastVersion = versions.length > 0 ? versions[0] : null;

  const changeTypeStats = versions.reduce((acc, v) => {
    acc[v.change_type] = (acc[v.change_type] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const changeTypePercentages = {
    create: totalVersions > 0 ? Math.round((changeTypeStats.create || 0) / totalVersions * 100) : 0,
    update: totalVersions > 0 ? Math.round((changeTypeStats.update || 0) / totalVersions * 100) : 0,
    delete: totalVersions > 0 ? Math.round((changeTypeStats.delete || 0) / totalVersions * 100) : 0
  };

  const last7Days = Array.from({ length: 7 }, (_, i) => {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    return date.toISOString().split('T')[0];
  }).reverse();

  const activityByDay = last7Days.map(date => {
    const count = versions.filter(v =>
      v.created_at.split('T')[0] === date
    ).length;
    return { date, count };
  });

  const maxDailyActivity = Math.max(...activityByDay.map(d => d.count), 1);

  return (
    <div className={`${styles.container} ${className}`}>
      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <div className={styles.statIcon}>
            <GitBranch size={20} />
          </div>
          <div className={styles.statContent}>
            <div className={styles.statValue}>{totalVersions}</div>
            <div className={styles.statLabel}>{t('stats.totalVersions')}</div>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statIcon}>
            <TrendingUp size={20} />
          </div>
          <div className={styles.statContent}>
            <div className={styles.statValue}>{versionsToday}</div>
            <div className={styles.statLabel}>{t('stats.today')}</div>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statIcon}>
            <TagIcon size={20} />
          </div>
          <div className={styles.statContent}>
            <div className={styles.statValue}>{totalTags}</div>
            <div className={styles.statLabel}>{t('stats.tags')}</div>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statIcon}>
            <Users size={20} />
          </div>
          <div className={styles.statContent}>
            <div className={styles.statValue}>{totalCollaborators}</div>
            <div className={styles.statLabel}>{t('stats.contributors')}</div>
          </div>
        </div>
      </div>

      {lastVersion && (
        <div className={styles.lastVersion}>
          <div className={styles.lastVersionIcon}>
            <Clock size={16} />
          </div>
          <div className={styles.lastVersionContent}>
            <div className={styles.lastVersionLabel}>{t('stats.lastVersion')}</div>
            <div className={styles.lastVersionInfo}>
              <span className={styles.lastVersionUser}>{lastVersion.username}</span>
              <span className={styles.lastVersionSeparator}>•</span>
              <span className={styles.lastVersionTime}>
                {formatVersionDate(lastVersion.created_at)}
              </span>
            </div>
          </div>
        </div>
      )}

      <div className={styles.distribution}>
        <div className={styles.distributionHeader}>
          <span className={styles.distributionTitle}>{t('stats.distribution.title')}</span>
        </div>
        <div className={styles.distributionBars}>
          {changeTypePercentages.create > 0 && (
            <div
              className={`${styles.distributionBar} ${styles.barCreate}`}
              style={{ width: `${changeTypePercentages.create}%` }}
              title={t('stats.distribution.tooltip.create', { percent: changeTypePercentages.create })}
            />
          )}
          {changeTypePercentages.update > 0 && (
            <div
              className={`${styles.distributionBar} ${styles.barUpdate}`}
              style={{ width: `${changeTypePercentages.update}%` }}
              title={t('stats.distribution.tooltip.update', { percent: changeTypePercentages.update })}
            />
          )}
          {changeTypePercentages.delete > 0 && (
            <div
              className={`${styles.distributionBar} ${styles.barDelete}`}
              style={{ width: `${changeTypePercentages.delete}%` }}
              title={t('stats.distribution.tooltip.delete', { percent: changeTypePercentages.delete })}
            />
          )}
        </div>
        <div className={styles.distributionLegend}>
          <div className={styles.legendItem}>
            <span className={`${styles.legendDot} ${styles.dotCreate}`} />
            <span className={styles.legendLabel}>{t('stats.distribution.create', { percent: changeTypePercentages.create })}</span>
          </div>
          <div className={styles.legendItem}>
            <span className={`${styles.legendDot} ${styles.dotUpdate}`} />
            <span className={styles.legendLabel}>{t('stats.distribution.update', { percent: changeTypePercentages.update })}</span>
          </div>
          <div className={styles.legendItem}>
            <span className={`${styles.legendDot} ${styles.dotDelete}`} />
            <span className={styles.legendLabel}>{t('stats.distribution.delete', { percent: changeTypePercentages.delete })}</span>
          </div>
        </div>
      </div>

      <div className={styles.activity}>
        <div className={styles.activityHeader}>
          <Calendar size={16} />
          <span className={styles.activityTitle}>{t('stats.activity.title')}</span>
        </div>
        <div className={styles.activityChart}>
          {activityByDay.map(({ date, count }) => {
            const dayName = new Date(date + 'T00:00:00').toLocaleDateString(i18n.language, { weekday: 'short' });
            const height = (count / maxDailyActivity) * 100;

            return (
              <div key={date} className={styles.activityBar}>
                <div
                  className={styles.activityBarFill}
                  style={{ height: `${height}%` }}
                  title={t('stats.activity.tooltip', { day: dayName, count })}
                >
                  {count > 0 && <span className={styles.activityBarLabel}>{count}</span>}
                </div>
                <div className={styles.activityBarDay}>{dayName}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default VersionStats;
