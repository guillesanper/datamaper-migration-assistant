// src/components/mapping/modals/PrimaryKeyModal.tsx
import React, { useState, useEffect } from 'react';
import { X, Key, AlertCircle, CheckCircle2 } from '../../icons';
import { useTranslation } from 'react-i18next';
import { pkService, getPrimaryKeyColumnNames, validateConstraintName } from '../../../services/pk_service';
import { toast } from '../../../utils/toast';
import type { Column, PrimaryKeyConstraint } from '../../../types/mapping-types';
import styles from '../../../styles/mapping/mapping.module.css';
import { Button } from '../../ui/button';

const IS_DEV = import.meta.env.DEV;

interface PrimaryKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  tableId: string;
  tableName: string;
  columns: Column[];
  onSuccess: () => void;
}

const MAX_PK_COLUMNS = 5;

export const PrimaryKeyModal: React.FC<PrimaryKeyModalProps> = ({
  isOpen,
  onClose,
  projectId,
  tableId,
  tableName,
  columns,
  onSuccess
}) => {
  const { t } = useTranslation(['mapping', 'common']);
  const [selectedColumnIds, setSelectedColumnIds] = useState<string[]>([]);
  const [constraintName, setConstraintName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentPK, setCurrentPK] = useState<PrimaryKeyConstraint | null>(null);

  // Load current PK configuration when modal opens
  useEffect(() => {
    if (isOpen) {
      loadCurrentPK();
    } else {
      // Reset state when closing
      setSelectedColumnIds([]);
      setConstraintName('');
      setError('');
      setCurrentPK(null);
    }
  }, [isOpen, tableId]);

  const loadCurrentPK = async () => {
    setIsLoading(true);
    try {
      if (IS_DEV) console.log('[PrimaryKeyModal] Loading PK for table:', tableId);
      const pk = await pkService.getPrimaryKey(projectId, tableId);
      if (IS_DEV) console.log('[PrimaryKeyModal] PK loaded:', pk);
      setCurrentPK(pk);

      if (pk) {
        setSelectedColumnIds(pk.column_ids);
        setConstraintName(pk.constraint_name || '');
      } else {
        if (IS_DEV) console.log('[PrimaryKeyModal] No PK found, checking legacy columns');
        // Check for legacy is_primary columns
        const legacyPKColumns = columns.filter(col => col.is_primary);
        if (legacyPKColumns.length > 0) {
          if (IS_DEV) console.log('[PrimaryKeyModal] Found legacy PK columns:', legacyPKColumns.length);
          setSelectedColumnIds(legacyPKColumns.map(col => col.id));
        }
      }
    } catch (err: unknown) {
      if (IS_DEV) {
        console.error('[PrimaryKeyModal] Error loading PK:', err);
        const errObj = err as Record<string, unknown>;
        console.error('[PrimaryKeyModal] Error details:', {
          message: err instanceof Error ? err.message : String(err),
          stack: errObj.stack,
          tableId
        });
      }
      // Don't show error toast - allow modal to open with empty state
    } finally {
      setIsLoading(false);
    }
  };

  const toggleColumn = (columnId: string) => {
    setError('');

    if (selectedColumnIds.includes(columnId)) {
      setSelectedColumnIds(prev => prev.filter(id => id !== columnId));
    } else {
      if (selectedColumnIds.length >= MAX_PK_COLUMNS) {
        setError(t('mapping:primaryKey.validation.maxColumns', { max: MAX_PK_COLUMNS }));
        return;
      }
      setSelectedColumnIds(prev => [...prev, columnId]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (selectedColumnIds.length === 0) {
      setError(t('mapping:primaryKey.validation.required'));
      return;
    }

    if (constraintName.trim()) {
      const validationError = validateConstraintName(constraintName);
      if (validationError) {
        setError(validationError);
        return;
      }
    }

    setIsSubmitting(true);

    try {
      await pkService.setPrimaryKey(projectId, {
        table_id: tableId,
        column_ids: selectedColumnIds,
        constraint_name: constraintName.trim() || null
      });

      const isComposite = selectedColumnIds.length > 1;
      toast.success(
        isComposite
          ? t('mapping:primaryKey.toast.compositeSuccess', { count: selectedColumnIds.length })
          : t('mapping:primaryKey.toast.success')
      );

      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (IS_DEV) {
        console.error('Error setting PK:', err);
        console.error('Error details:', {
          message: err instanceof Error ? err.message : String(err),
          tableId,
          selectedColumnIds,
          constraintName
        });
      }
      setError(err instanceof Error ? err.message : t('mapping:primaryKey.toast.error'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRemovePK = async () => {
    if (!window.confirm(t('mapping:primaryKey.removeConfirm'))) {
      return;
    }

    setIsSubmitting(true);
    try {
      await pkService.removePrimaryKey(projectId, tableId);
      toast.success(t('mapping:primaryKey.toast.removed'));
      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (IS_DEV) console.error('Error removing PK:', err);
      setError(err instanceof Error ? err.message : t('mapping:primaryKey.toast.removeError'));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const isComposite = selectedColumnIds.length > 1;
  const hasChanges = currentPK
    ? (
        JSON.stringify(currentPK.column_ids.sort()) !== JSON.stringify(selectedColumnIds.sort()) ||
        (currentPK.constraint_name || '') !== constraintName.trim()
      )
    : selectedColumnIds.length > 0;

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5 text-yellow-500" />
            <h2 className={styles.modalTitle}>
              {t('mapping:primaryKey.titleWithTable', { table: tableName })}
            </h2>
          </div>
          <button
            onClick={onClose}
            className={styles.modalCloseButton}
            disabled={isSubmitting}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className={styles.modalBody}>
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          ) : (
            <>
              {/* Info Box */}
              <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-4">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-blue-900 dark:text-blue-100">
                    <p className="font-semibold mb-1">{t('mapping:primaryKey.info.title')}</p>
                    <p>{t('mapping:primaryKey.info.desc', { max: MAX_PK_COLUMNS })}</p>
                  </div>
                </div>
              </div>

              {/* Current PK Info */}
              {currentPK && !currentPK.is_legacy && (
                <div className="bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-lg p-3 mb-4">
                  <div className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                    <span className="text-green-900 dark:text-green-100">
                      <strong>{t('mapping:primaryKey.current')}</strong> {getPrimaryKeyColumnNames(currentPK)}
                      {currentPK.is_composite && ` (${t('mapping:primaryKey.type.composite')})`}
                    </span>
                  </div>
                </div>
              )}

              {/* Column Selection */}
              <div className="space-y-3">
                <label className="block text-sm font-medium">
                  {t('mapping:primaryKey.columns.selection', { count: selectedColumnIds.length, max: MAX_PK_COLUMNS })}
                </label>

                <div className="border rounded-lg divide-y max-h-80 overflow-y-auto">
                  {columns.length === 0 ? (
                    <div className="p-4 text-center text-muted-foreground text-sm">
                      {t('mapping:primaryKey.columns.empty')}
                    </div>
                  ) : (
                    columns.map((column) => {
                      const isSelected = selectedColumnIds.includes(column.id);
                      const selectionIndex = selectedColumnIds.indexOf(column.id);

                      return (
                        <label
                          key={column.id}
                          className={`
                            flex items-center gap-3 p-3 cursor-pointer transition-colors
                            hover:bg-muted/50
                            ${isSelected ? 'bg-blue-50 dark:bg-blue-950/30' : ''}
                          `}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleColumn(column.id)}
                            disabled={isSubmitting}
                            className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
                          />

                          {isSelected && (
                            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-500 text-white text-xs font-bold">
                              {selectionIndex + 1}
                            </span>
                          )}

                          <div className="flex-1 flex items-center gap-2">
                            <Key className={`w-4 h-4 ${isSelected ? 'text-yellow-500' : 'text-gray-400'}`} />
                            <span className="font-medium">{column.name}</span>
                            <span className="text-xs text-muted-foreground">
                              ({column.data_type || 'N/A'})
                            </span>
                            {!column.is_nullable && (
                              <span className="text-xs text-red-500">NOT NULL</span>
                            )}
                          </div>
                        </label>
                      );
                    })
                  )}
                </div>
              </div>

              {/* Constraint Name (Optional) */}
              <div className="space-y-2">
                <label htmlFor="constraint-name" className="block text-sm font-medium">
                  {t('mapping:primaryKey.constraintName.label')} <span className="text-muted-foreground">{t('mapping:primaryKey.constraintName.optional')}</span>
                </label>
                <input
                  id="constraint-name"
                  type="text"
                  value={constraintName}
                  onChange={(e) => {
                    setConstraintName(e.target.value);
                    setError('');
                  }}
                  disabled={isSubmitting}
                  placeholder={`pk_${tableName.toLowerCase()}`}
                  className="w-full px-3 py-2 border rounded-lg bg-background text-sm"
                />
                <p className="text-xs text-muted-foreground">
                  {t('mapping:primaryKey.constraintName.hint')}
                </p>
              </div>

              {/* Composite PK Info */}
              {isComposite && (
                <div className="bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    <Key className="w-4 h-4 text-yellow-500 flex-shrink-0 mt-0.5" />
                    <div className="text-sm text-yellow-900 dark:text-yellow-100">
                      <p className="font-semibold mb-1">{t('mapping:primaryKey.type.compositeTitle')}</p>
                      <p>{t('mapping:primaryKey.compositeInfo', { count: selectedColumnIds.length })}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Error Message */}
              {error && (
                <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg p-3">
                  <div className="flex items-center gap-2 text-sm text-red-900 dark:text-red-100">
                    <AlertCircle className="w-4 h-4 text-red-500" />
                    <span>{error}</span>
                  </div>
                </div>
              )}
            </>
          )}
        </form>

        {/* Footer */}
        <div className={styles.modalFooter}>
          <div className="flex items-center justify-between w-full">
            <div>
              {currentPK && (
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={handleRemovePK}
                  disabled={isSubmitting || isLoading}
                >
                  {t('mapping:primaryKey.removeBtn')}
                </Button>
              )}
            </div>

            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                disabled={isSubmitting}
              >
                {t('common:actions.cancel')}
              </Button>
              <Button
                type="submit"
                onClick={handleSubmit}
                disabled={isSubmitting || isLoading || !hasChanges || selectedColumnIds.length === 0}
              >
                {isSubmitting
                  ? t('mapping:primaryKey.savingBtn')
                  : currentPK
                    ? t('mapping:primaryKey.updateBtn')
                    : t('mapping:primaryKey.submitBtn')}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PrimaryKeyModal;
