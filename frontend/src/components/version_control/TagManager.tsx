// src/components/version_control/TagManager.tsx
import React, { useState } from 'react';
import { Tag as TagIcon, Plus, X, Trash, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/button';
import type { Tag, CreateTagRequest } from '../../types/version_control_types';
import styles from '../../styles/version_control/version-filters.module.css';

interface TagManagerProps {
  versionId?: string;
  projectId: string;
  existingTags: Tag[];
  onCreateTag: (data: CreateTagRequest) => Promise<void>;
  onDeleteTag: (tagId: string) => Promise<void>;
  className?: string;
}

type ColorKey = 'red' | 'orange' | 'yellow' | 'green' | 'blue' | 'indigo' | 'purple' | 'pink' | 'gray';

const PRESET_COLORS: Array<{ key: ColorKey; value: string }> = [
  { key: 'red', value: '#ef4444' },
  { key: 'orange', value: '#f97316' },
  { key: 'yellow', value: '#eab308' },
  { key: 'green', value: '#22c55e' },
  { key: 'blue', value: '#3b82f6' },
  { key: 'indigo', value: '#6366f1' },
  { key: 'purple', value: '#a855f7' },
  { key: 'pink', value: '#ec4899' },
  { key: 'gray', value: '#6b7280' }
];

export const TagManager: React.FC<TagManagerProps> = ({
  versionId,
  existingTags,
  onCreateTag,
  onDeleteTag,
  className = ''
}) => {
  const { t } = useTranslation(['version_control', 'common']);
  const [isCreating, setIsCreating] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [newTagDescription, setNewTagDescription] = useState('');
  const [newTagColor, setNewTagColor] = useState(PRESET_COLORS[0].value);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!newTagName.trim()) {
      setError(t('version_control:tags.nameRequired'));
      return;
    }

    if (!versionId) {
      setError(t('version_control:tags.versionRequired'));
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await onCreateTag({
        version_id: versionId,
        name: newTagName.trim(),
        description: newTagDescription.trim() || undefined,
        color: newTagColor
      });

      setNewTagName('');
      setNewTagDescription('');
      setNewTagColor(PRESET_COLORS[0].value);
      setIsCreating(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('version_control:tags.createError'));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (tagId: string, tagName: string) => {
    if (!confirm(t('version_control:tags.deleteConfirm', { name: tagName }))) return;

    setLoading(true);
    setError(null);

    try {
      await onDeleteTag(tagId);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('version_control:tags.deleteError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`${styles.container} ${className}`}>
      <div className={styles.header}>
        <div className={styles.headerTitle}>
          <TagIcon size={18} />
          <h3>{t('version_control:tags.title')}</h3>
          <span className={styles.badge}>{existingTags.length}</span>
        </div>

        {versionId && !isCreating && (
          <Button
            size="sm"
            onClick={() => setIsCreating(true)}
            disabled={loading}
          >
            <Plus size={16} />
            {t('version_control:tags.create')}
          </Button>
        )}
      </div>

      {error && (
        <div className={styles.error}>
          <X size={16} />
          {error}
        </div>
      )}

      {isCreating && (
        <div className={styles.createForm}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>{t('version_control:tags.name.label')} *</label>
            <input
              type="text"
              className={styles.formInput}
              placeholder={t('version_control:tags.name.placeholder')}
              value={newTagName}
              onChange={(e) => setNewTagName(e.target.value)}
              maxLength={50}
              autoFocus
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.formLabel}>{t('version_control:tags.descLabel')}</label>
            <textarea
              className={styles.formTextarea}
              placeholder={t('version_control:tags.descPlaceholder')}
              value={newTagDescription}
              onChange={(e) => setNewTagDescription(e.target.value)}
              maxLength={200}
              rows={2}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.formLabel}>{t('version_control:tags.color.label')}</label>
            <div className={styles.colorPicker}>
              {PRESET_COLORS.map(({ key, value }) => (
                <button
                  key={value}
                  className={`${styles.colorOption} ${newTagColor === value ? styles.colorOptionActive : ''}`}
                  style={{ backgroundColor: value }}
                  onClick={() => setNewTagColor(value)}
                  title={t(`version_control:tags.colors.${key}`)}
                  type="button"
                >
                  {newTagColor === value && <Check size={14} color="white" />}
                </button>
              ))}
            </div>
          </div>

          <div className={styles.formActions}>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setIsCreating(false);
                setNewTagName('');
                setNewTagDescription('');
                setError(null);
              }}
              disabled={loading}
            >
              {t('common:actions.cancel')}
            </Button>
            <Button
              size="sm"
              onClick={handleCreate}
              disabled={loading || !newTagName.trim()}
            >
              {loading ? t('version_control:tags.creating') : t('version_control:tags.create')}
            </Button>
          </div>
        </div>
      )}

      <div className={styles.tagsList}>
        {existingTags.length === 0 ? (
          <div className={styles.emptyState}>
            <TagIcon size={32} />
            <p>{t('version_control:tags.empty')}</p>
            {versionId && (
              <p className={styles.emptyHint}>{t('version_control:tags.emptyHint')}</p>
            )}
          </div>
        ) : (
          existingTags.map(tag => (
            <div key={tag.id} className={styles.tagItem}>
              <div className={styles.tagItemContent}>
                <div
                  className={styles.tagItemColor}
                  style={{ backgroundColor: tag.color || '#6b7280' }}
                />
                <div className={styles.tagItemInfo}>
                  <div className={styles.tagItemName}>{tag.name}</div>
                  {tag.description && (
                    <div className={styles.tagItemDescription}>{tag.description}</div>
                  )}
                  <div className={styles.tagItemMeta}>
                    {t('version_control:tags.createdBy', {
                      name: tag.created_by_name || t('version_control:tags.unknownUser')
                    })}
                  </div>
                </div>
              </div>
              <Button
                size="icon-sm"
                variant="ghost"
                onClick={() => handleDelete(tag.id, tag.name)}
                disabled={loading}
                title={t('common:actions.delete')}
              >
                <Trash size={16} />
              </Button>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default TagManager;
