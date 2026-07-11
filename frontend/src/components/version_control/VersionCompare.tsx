// src/components/version_control/VersionCompare.tsx
import React, { useMemo } from 'react';
import { ArrowRight, Plus, Minus, Edit2, Clock, User, GitBranch, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Version, VersionDiff } from '../../types/version_control_types';
import { calculateDiff, formatVersionDate } from '../../utils/version_control/versionUtils';
import { Button } from '../ui/button';
import styles from '../../styles/version_control/version-compare.module.css';

interface VersionCompareProps {
  versionA: Version;
  versionB: Version;
  onClose?: () => void;
  className?: string;
}

export const VersionCompare: React.FC<VersionCompareProps> = ({
  versionA,
  versionB,
  onClose,
  className = ''
}) => {
  const { t } = useTranslation('version_control');

  const diff: VersionDiff = useMemo(() => {
    try {
      const snapshotA = JSON.parse(versionA.snapshot);
      const snapshotB = JSON.parse(versionB.snapshot);
      return calculateDiff(snapshotA, snapshotB);
    } catch (error) {
      console.error('[VersionCompare] Error calculating diff:', error);
      return { added: [], removed: [], modified: [] };
    }
  }, [versionA.snapshot, versionB.snapshot]);

  const hasChanges = diff.added.length > 0 || diff.removed.length > 0 || diff.modified.length > 0;

  const renderValue = (value: unknown): React.ReactNode => {
    if (value === null) return <span className={styles.nullValue}>null</span>;
    if (value === undefined) return <span className={styles.undefinedValue}>undefined</span>;
    if (typeof value === 'boolean') {
      return <span className={styles.booleanValue}>{value.toString()}</span>;
    }
    if (typeof value === 'number') {
      return <span className={styles.numberValue}>{value}</span>;
    }
    if (typeof value === 'string') {
      return <span className={styles.stringValue}>"{value}"</span>;
    }
    if (typeof value === 'object') {
      return <span className={styles.objectValue}>{JSON.stringify(value, null, 2)}</span>;
    }
    return String(value);
  };

  return (
    <div className={`${styles.container} ${className}`}>
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <GitBranch size={20} />
          <h3 className={styles.title}>{t('compare.title')}</h3>
        </div>
        {onClose && (
          <Button size="icon-sm" variant="ghost" onClick={onClose}>
            <X size={18} />
          </Button>
        )}
      </div>

      <div className={styles.versionCards}>
        <div className={styles.versionCard}>
          <div className={styles.versionCardHeader}>
            <span className={styles.versionNumber}>v{versionA.version_number}</span>
            <span className={styles.versionLabel}>{t('compare.versionA')}</span>
          </div>
          <div className={styles.versionCardBody}>
            <div className={styles.versionMeta}>
              <User size={14} />
              <span>{versionA.username}</span>
            </div>
            <div className={styles.versionMeta}>
              <Clock size={14} />
              <span>{formatVersionDate(versionA.created_at)}</span>
            </div>
            {versionA.message && (
              <div className={styles.versionMessage}>{versionA.message}</div>
            )}
          </div>
        </div>

        <div className={styles.arrowContainer}>
          <ArrowRight size={24} />
        </div>

        <div className={styles.versionCard}>
          <div className={styles.versionCardHeader}>
            <span className={styles.versionNumber}>v{versionB.version_number}</span>
            <span className={styles.versionLabel}>{t('compare.versionB')}</span>
          </div>
          <div className={styles.versionCardBody}>
            <div className={styles.versionMeta}>
              <User size={14} />
              <span>{versionB.username}</span>
            </div>
            <div className={styles.versionMeta}>
              <Clock size={14} />
              <span>{formatVersionDate(versionB.created_at)}</span>
            </div>
            {versionB.message && (
              <div className={styles.versionMessage}>{versionB.message}</div>
            )}
          </div>
        </div>
      </div>

      <div className={styles.summary}>
        <div className={styles.summaryItem}>
          <Plus size={16} />
          <span>{t('compare.summary.added', { count: diff.added.length })}</span>
        </div>
        <div className={styles.summaryItem}>
          <Minus size={16} />
          <span>{t('compare.summary.removed', { count: diff.removed.length })}</span>
        </div>
        <div className={styles.summaryItem}>
          <Edit2 size={16} />
          <span>{t('compare.summary.modified', { count: diff.modified.length })}</span>
        </div>
      </div>

      <div className={styles.diffContainer}>
        {!hasChanges ? (
          <div className={styles.noChanges}>
            <p>{t('compare.noChanges')}</p>
          </div>
        ) : (
          <>
            {diff.added.length > 0 && (
              <div className={styles.diffSection}>
                <div className={`${styles.diffSectionHeader} ${styles.added}`}>
                  <Plus size={16} />
                  <h4>{t('compare.section.added', { count: diff.added.length })}</h4>
                </div>
                <div className={styles.diffList}>
                  {diff.added.map((change, index) => (
                    <div key={index} className={`${styles.diffItem} ${styles.addedItem}`}>
                      <div className={styles.diffPath}>
                        <code>{change.path}</code>
                      </div>
                      <div className={styles.diffValue}>
                        <div className={styles.valueContainer}>
                          <span className={styles.valueLabel}>{t('compare.diff.newValue')}</span>
                          {renderValue(change.new_value)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {diff.removed.length > 0 && (
              <div className={styles.diffSection}>
                <div className={`${styles.diffSectionHeader} ${styles.removed}`}>
                  <Minus size={16} />
                  <h4>{t('compare.section.removed', { count: diff.removed.length })}</h4>
                </div>
                <div className={styles.diffList}>
                  {diff.removed.map((change, index) => (
                    <div key={index} className={`${styles.diffItem} ${styles.removedItem}`}>
                      <div className={styles.diffPath}>
                        <code>{change.path}</code>
                      </div>
                      <div className={styles.diffValue}>
                        <div className={styles.valueContainer}>
                          <span className={styles.valueLabel}>{t('compare.diff.oldValue')}</span>
                          {renderValue(change.old_value)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {diff.modified.length > 0 && (
              <div className={styles.diffSection}>
                <div className={`${styles.diffSectionHeader} ${styles.modified}`}>
                  <Edit2 size={16} />
                  <h4>{t('compare.section.modified', { count: diff.modified.length })}</h4>
                </div>
                <div className={styles.diffList}>
                  {diff.modified.map((change, index) => (
                    <div key={index} className={`${styles.diffItem} ${styles.modifiedItem}`}>
                      <div className={styles.diffPath}>
                        <code>{change.path}</code>
                      </div>
                      <div className={styles.diffValue}>
                        <div className={`${styles.valueContainer} ${styles.oldValue}`}>
                          <span className={styles.valueLabel}>{t('compare.diff.before')}</span>
                          {renderValue(change.old_value)}
                        </div>
                        <ArrowRight size={16} className={styles.changeArrow} />
                        <div className={`${styles.valueContainer} ${styles.newValue}`}>
                          <span className={styles.valueLabel}>{t('compare.diff.after')}</span>
                          {renderValue(change.new_value)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
