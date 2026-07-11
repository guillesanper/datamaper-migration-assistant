// src/components/version_control/VersionHistory.tsx
import React, { useState } from 'react';
import {
  Clock,
  User,
  GitBranch,
  Tag as TagIcon,
  RotateCcw,
  Eye,
  MoreVertical,
  Plus,
  Trash
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Version, ChangeType } from '../../types/version_control_types';
import { formatVersionDate } from '../../utils/version_control/versionUtils';
import { Button } from '../ui/button';
import styles from '../../styles/version_control/version-history.module.css';

interface VersionHistoryProps {
  versions: Version[];
  currentVersionId?: string;
  onRestore?: (version: Version) => void;
  onCompare?: (versionA: Version, versionB: Version) => void;
  onViewDetails?: (version: Version) => void;
  onAddTag?: (versionId: string) => void;
  onDeleteVersion?: (versionId: string) => void;
  loading?: boolean;
  canRestore?: boolean;
  canDelete?: boolean;
  className?: string;
}

export const VersionHistory: React.FC<VersionHistoryProps> = ({
  versions,
  currentVersionId,
  onRestore,
  onCompare,
  onViewDetails,
  onAddTag,
  onDeleteVersion,
  loading = false,
  canRestore = false,
  canDelete = false,
  className = ''
}) => {
  const { t } = useTranslation(['version_control', 'common']);
  const [selectedForCompare, setSelectedForCompare] = useState<string | null>(null);
  const [expandedVersions, setExpandedVersions] = useState<Set<string>>(new Set());

  const toggleExpanded = (versionId: string) => {
    const newExpanded = new Set(expandedVersions);
    if (newExpanded.has(versionId)) {
      newExpanded.delete(versionId);
    } else {
      newExpanded.add(versionId);
    }
    setExpandedVersions(newExpanded);
  };

  const handleCompareSelect = (version: Version) => {
    if (!selectedForCompare) {
      setSelectedForCompare(version.id);
    } else {
      const firstVersion = versions.find((v) => v.id === selectedForCompare);
      if (firstVersion && onCompare) {
        onCompare(firstVersion, version);
      }
      setSelectedForCompare(null);
    }
  };

  const getChangeTypeConfig = (changeType: ChangeType) => {
    const configs: Record<ChangeType, { label: string; className: string }> = {
      create: { label: t('version_control:version.changeTypes.create'), className: styles.changeCreate },
      update: { label: t('version_control:version.changeTypes.update'), className: styles.changeUpdate },
      delete: { label: t('version_control:version.changeTypes.delete'), className: styles.changeDelete }
    };
    return configs[changeType];
  };

  if (loading) {
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.loading}>{t('version_control:history.loading')}</div>
      </div>
    );
  }

  if (versions.length === 0) {
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.empty}>
          <GitBranch size={48} />
          <p>{t('version_control:history.empty')}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.container} ${className}`}>
      <div className={styles.timeline}>
        {versions.map((version, index) => {
          const changeConfig = getChangeTypeConfig(version.change_type);
          const isCurrentVersion = version.id === currentVersionId;
          const isSelectedForCompare = version.id === selectedForCompare;
          const isExpanded = expandedVersions.has(version.id);
          const isFirst = index === 0;

          return (
            <div
              key={version.id}
              className={`${styles.timelineItem} ${
                isCurrentVersion ? styles.currentVersion : ''
              } ${isSelectedForCompare ? styles.selectedForCompare : ''}`}
            >
              {!isFirst && <div className={styles.timelineConnector} />}

              <div className={`${styles.timelineDot} ${changeConfig.className}`}>
                <GitBranch size={14} />
              </div>

              <div className={styles.timelineContent}>
                <div className={styles.versionHeader}>
                  <div className={styles.versionInfo}>
                    <span className={styles.versionNumber}>v{version.version_number}</span>
                    <span className={`${styles.changeTypeBadge} ${changeConfig.className}`}>
                      {changeConfig.label}
                    </span>
                    {isCurrentVersion && (
                      <span className={styles.currentBadge}>{t('version_control:history.current')}</span>
                    )}
                  </div>

                  <div className={styles.versionActions}>
                    {onCompare && versions.length > 1 && (
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        onClick={() => handleCompareSelect(version)}
                        title={isSelectedForCompare ? t('version_control:version.cancelCompare') : t('version_control:version.compare')}
                      >
                        <Eye size={16} />
                      </Button>
                    )}

                    {canRestore && onRestore && !isCurrentVersion && (
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        onClick={() => onRestore(version)}
                        title={t('version_control:version.restore')}
                      >
                        <RotateCcw size={16} />
                      </Button>
                    )}

                    <Button
                      size="icon-sm"
                      variant="ghost"
                      onClick={() => toggleExpanded(version.id)}
                      title={t('version_control:version.viewDetails')}
                    >
                      <MoreVertical size={16} />
                    </Button>
                  </div>
                </div>

                <div className={styles.versionMeta}>
                  <div className={styles.metaItem}>
                    <User size={14} />
                    <span>{version.username}</span>
                  </div>
                  <div className={styles.metaItem}>
                    <Clock size={14} />
                    <span>{formatVersionDate(version.created_at)}</span>
                  </div>
                </div>

                {version.message && (
                  <div className={styles.versionMessage}>{version.message}</div>
                )}

                {version.tags && version.tags.length > 0 && (
                  <div className={styles.tagList}>
                    {version.tags.map((tag) => (
                      <span key={tag.id} className={styles.tag}>
                        <TagIcon size={12} />
                        {tag.name}
                      </span>
                    ))}
                    {onAddTag && (
                      <button
                        className={styles.addTagButton}
                        onClick={() => onAddTag(version.id)}
                        title={t('version_control:version.addTag')}
                      >
                        <Plus size={12} />
                      </button>
                    )}
                  </div>
                )}

                {isExpanded && (
                  <div className={styles.expandedDetails}>
                    <div className={styles.detailRow}>
                      <span className={styles.detailLabel}>Hash:</span>
                      <code className={styles.detailValue}>{version.hash.slice(0, 12)}...</code>
                    </div>
                    {version.parent_version_id && (
                      <div className={styles.detailRow}>
                        <span className={styles.detailLabel}>{t('version_control:version.parentVersion')}:</span>
                        <span className={styles.detailValue}>{version.parent_version_id.slice(0, 8)}</span>
                      </div>
                    )}
                    <div className={styles.detailActions}>
                      {onViewDetails && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => onViewDetails(version)}
                        >
                          <Eye size={14} />
                          {t('version_control:version.viewDetails')}
                        </Button>
                      )}
                      {canDelete && onDeleteVersion && !isCurrentVersion && (
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => onDeleteVersion(version.id)}
                        >
                          <Trash size={14} />
                          {t('common:actions.delete')}
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {selectedForCompare && (
        <div className={styles.compareHint}>
          <Eye size={16} />
          {t('version_control:history.compareHint')}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSelectedForCompare(null)}
          >
            {t('version_control:history.cancelCompare')}
          </Button>
        </div>
      )}
    </div>
  );
};
