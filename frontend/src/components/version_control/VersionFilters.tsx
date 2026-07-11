// src/components/version_control/VersionFilters.tsx
import React, { useState, useEffect } from 'react';
import { Filter, X, Calendar, User, Tag as TagIcon, FileType } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import type { VersionFilters as VersionFiltersType, EntityType, ChangeType } from '../../types/version_control_types';
import styles from '../../styles/version_control/version-filters.module.css';

interface VersionFiltersProps {
  filters: VersionFiltersType;
  onFiltersChange: (filters: VersionFiltersType) => void;
  availableUsers?: Array<{ id: string; name: string }>;
  availableTags?: Array<{ id: string; name: string }>;
  onReset?: () => void;
  className?: string;
}

export const VersionFilters: React.FC<VersionFiltersProps> = ({
  filters,
  onFiltersChange,
  availableUsers = [],
  availableTags = [],
  onReset,
  className = ''
}) => {
  const { t } = useTranslation('version_control');
  const [localFilters, setLocalFilters] = useState<VersionFiltersType>(filters);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    setLocalFilters(filters);
  }, [filters]);

  const handleFilterChange = (key: keyof VersionFiltersType, value: VersionFiltersType[keyof VersionFiltersType]) => {
    const newFilters = { ...localFilters, [key]: value };
    setLocalFilters(newFilters);
    onFiltersChange(newFilters);
  };

  const handleChangeTypeToggle = (changeType: ChangeType) => {
    const current = localFilters.change_type || [];
    const newTypes = current.includes(changeType)
      ? current.filter((ct: ChangeType) => ct !== changeType)
      : [...current, changeType];

    handleFilterChange('change_type', newTypes.length > 0 ? newTypes : undefined);
  };

  const handleReset = () => {
    const emptyFilters: VersionFiltersType = {};
    setLocalFilters(emptyFilters);
    onFiltersChange(emptyFilters);
    if (onReset) onReset();
  };

  const activeFiltersCount = Object.keys(localFilters).filter(
    key => localFilters[key as keyof VersionFiltersType] !== undefined
  ).length;

  const changeTypes: Array<{ value: ChangeType; label: string; color: string }> = [
    { value: 'create', label: t('version.changeTypes.create'), color: 'var(--success)' },
    { value: 'update', label: t('version.changeTypes.update'), color: 'var(--info)' },
    { value: 'delete', label: t('version.changeTypes.delete'), color: 'var(--destructive)' }
  ];

  const entityTypes: Array<{ value: EntityType; label: string }> = [
    { value: 'mapping', label: t('filters.entityTypes.mapping') },
    { value: 'table', label: t('filters.entityTypes.table') },
    { value: 'column', label: t('filters.entityTypes.column') },
    { value: 'transformation', label: t('filters.entityTypes.transformation') },
    { value: 'project', label: t('filters.entityTypes.project') }
  ];

  return (
    <div className={`${styles.container} ${className}`}>
      <div
        className={styles.header}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <button className={styles.toggleButton}>
          <Filter size={18} />
          <span>{t('filters.title')}</span>
          {activeFiltersCount > 0 && (
            <span className={styles.badge}>{activeFiltersCount}</span>
          )}
        </button>

        {activeFiltersCount > 0 && (
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              handleReset();
            }}
            className={styles.resetButton}
          >
            <X size={16} />
            {t('filters.clear')}
          </Button>
        )}
      </div>

      {isExpanded && (
        <div className={styles.panel}>
          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>
              <Filter size={14} />
              {t('filters.search')}
            </label>
            <input
              type="text"
              className={styles.searchInput}
              placeholder={t('filters.searchPlaceholder')}
              value={localFilters.search_term || ''}
              onChange={(e) => handleFilterChange('search_term', e.target.value || undefined)}
            />
          </div>

          {availableUsers.length > 0 && (
            <div className={styles.filterGroup}>
              <label className={styles.filterLabel}>
                <User size={14} />
                {t('filters.author.label')}
              </label>
              <Select
                value={localFilters.user_id || 'all'}
                onValueChange={(value) => handleFilterChange('user_id', value === 'all' ? undefined : value)}
              >
                <SelectTrigger className={styles.select}>
                  <SelectValue placeholder={t('filters.author.all')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('filters.author.all')}</SelectItem>
                  {availableUsers.map(user => (
                    <SelectItem key={user.id} value={user.id}>
                      {user.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>
              <FileType size={14} />
              {t('filters.changeType')}
            </label>
            <div className={styles.chipGroup}>
              {changeTypes.map(({ value, label, color }) => {
                const isActive = localFilters.change_type?.includes(value);
                return (
                  <button
                    key={value}
                    className={`${styles.chip} ${isActive ? styles.chipActive : ''}`}
                    style={isActive ? { borderColor: color, color } : {}}
                    onClick={() => handleChangeTypeToggle(value)}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>
              <FileType size={14} />
              {t('filters.entityType')}
            </label>
            <Select
              value={localFilters.entity_type || 'all'}
              onValueChange={(value) => handleFilterChange('entity_type', value === 'all' ? undefined : value as EntityType)}
            >
              <SelectTrigger className={styles.select}>
                <SelectValue placeholder={t('filters.allTypes')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('filters.allTypes')}</SelectItem>
                {entityTypes.map(({ value, label }) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>
              <Calendar size={14} />
              {t('filters.date.label')}
            </label>
            <div className={styles.dateRange}>
              <input
                type="date"
                className={styles.dateInput}
                value={localFilters.date_from || ''}
                onChange={(e) => handleFilterChange('date_from', e.target.value || undefined)}
                placeholder={t('filters.dateFrom')}
              />
              <span className={styles.dateSeparator}>—</span>
              <input
                type="date"
                className={styles.dateInput}
                value={localFilters.date_to || ''}
                onChange={(e) => handleFilterChange('date_to', e.target.value || undefined)}
                placeholder={t('filters.dateTo')}
              />
            </div>
          </div>

          {availableTags.length > 0 && (
            <div className={styles.filterGroup}>
              <label className={styles.filterLabel}>
                <TagIcon size={14} />
                {t('filters.tags.label')}
              </label>
              <div className={styles.chipGroup}>
                {availableTags.map(tag => {
                  const isActive = localFilters.tags?.includes(tag.id);
                  return (
                    <button
                      key={tag.id}
                      className={`${styles.chip} ${isActive ? styles.chipActive : ''}`}
                      onClick={() => {
                        const current = localFilters.tags || [];
                        const newTags = isActive
                          ? current.filter((id: string) => id !== tag.id)
                          : [...current, tag.id];
                        handleFilterChange('tags', newTags.length > 0 ? newTags : undefined);
                      }}
                    >
                      <TagIcon size={12} />
                      {tag.name}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {activeFiltersCount > 0 && (
            <div className={styles.summary}>
              <span className={styles.summaryText}>
                {t('filters.active', { count: activeFiltersCount })}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default VersionFilters;
