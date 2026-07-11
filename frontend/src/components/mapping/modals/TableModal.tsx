// src/components/mapping/modals/TableModal.tsx
import React, { useState, useEffect } from 'react';
import { X, Database, AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { mappingService } from '../../../services/mapping_service';
import { toast } from '../../../utils/toast';
import type { Table, CreateTableData, UpdateTableData } from '../../../types/mapping-types';
import styles from '../../../styles/mapping/mapping.module.css';

interface TableModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  table?: Table;
  onSuccess: () => void;
}

export const TableModal: React.FC<TableModalProps> = ({
  isOpen,
  onClose,
  projectId,
  table,
  onSuccess
}) => {
  const { t } = useTranslation(['mapping', 'common']);

  const [name, setName] = useState('');
  const [type, setType] = useState<'origin' | 'destination'>('origin');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const isEditMode = !!table;

  useEffect(() => {
    if (table) {
      setName(table.name);
      setType(table.type);
    } else {
      setName('');
      setType('origin');
    }
    setError('');
  }, [table, isOpen]);

  const validateName = (value: string): string | null => {
    if (!value.trim()) {
      return t('tableModal.name.validation.required');
    }
    if (!/^[A-Za-z0-9_][A-Za-z0-9_]{0,62}$/.test(value)) {
      return t('tableModal.name.validation.format');
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const validationError = validateName(name);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSubmitting(true);

    try {
      if (isEditMode && table) {
        const updateData: UpdateTableData = { name: name.trim() };
        await mappingService.updateTable(projectId, table.id, updateData);
        toast.success(t('tableModal.toast.updated'));
      } else {
        const createData: CreateTableData = {
          project_id: projectId,
          name: name.trim(),
          type
        };
        await mappingService.createTable(projectId, createData);
        toast.success(t('tableModal.toast.created'));
      }

      onSuccess();
      handleClose();
    } catch (err: unknown) {
      console.error('Error al guardar tabla:', err);
      const errObj = err as Record<string, unknown>;
      const responseDetail = (errObj.response as Record<string, unknown> | undefined)?.data as Record<string, unknown> | undefined;
      const errorMessage = String(responseDetail?.detail ?? '') || (err instanceof Error ? err.message : '');
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setName('');
    setType('origin');
    setError('');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modalContent} style={{ maxWidth: '500px' }}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5" />
            <h2 className={styles.modalTitle}>
              {isEditMode ? t('tableModal.editTitle') : t('tableModal.createTitle')}
            </h2>
          </div>
          <button onClick={handleClose} className={styles.modalCloseButton}>
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit}>
          <div className={styles.modalBody}>
            {/* Nombre */}
            <div>
              <label className="text-sm font-medium mb-2 block">
                {t('tableModal.name.label')} <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setError('');
                }}
                placeholder={t('tableModal.name.placeholder')}
                className={`w-full px-3 py-2 border rounded-lg bg-background ${
                  error ? 'border-red-500' : 'border-border'
                } focus:outline-none focus:ring-2 focus:ring-primary`}
                disabled={isSubmitting}
                autoFocus
              />
              <p className="text-xs text-muted-foreground mt-1">
                {t('tableModal.name.hint')}
              </p>
            </div>

            {/* Tipo - Solo en modo creación */}
            {!isEditMode && (
              <div>
                <label className="text-sm font-medium mb-2 block">
                  {t('tableModal.typeLabel')} <span className="text-red-500">*</span>
                </label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      value="origin"
                      checked={type === 'origin'}
                      onChange={(e) => setType(e.target.value as 'origin')}
                      className="w-4 h-4"
                      disabled={isSubmitting}
                    />
                    <span className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                      {t('tableModal.typeOrigin')}
                    </span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      value="destination"
                      checked={type === 'destination'}
                      onChange={(e) => setType(e.target.value as 'destination')}
                      className="w-4 h-4"
                      disabled={isSubmitting}
                    />
                    <span className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-green-500"></div>
                      {t('tableModal.typeDest')}
                    </span>
                  </label>
                </div>
              </div>
            )}

            {/* Error message */}
            {error && (
              <div className={`${styles.alert} ${styles.alertInfo}`}>
                <div className={styles.alertContent}>
                  <AlertCircle className="w-4 h-4 text-red-500" />
                  <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
                </div>
              </div>
            )}

            {/* Info */}
            {!isEditMode && (
              <div className={`${styles.alert} ${styles.alertInfo}`}>
                <div className={styles.alertContent}>
                  <AlertCircle className={`${styles.alertIcon} ${styles.alertIconInfo}`} />
                  <div className={styles.alertBody}>
                    <p className="text-xs text-muted-foreground">
                      {t('tableModal.info')}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className={styles.modalFooter}>
            <div className={styles.modalFooterRight}>
              <button
                type="button"
                onClick={handleClose}
                className={styles.toolbarButton}
                disabled={isSubmitting}
              >
                {t('common:actions.cancel')}
              </button>
              <button
                type="submit"
                disabled={isSubmitting || !name.trim()}
                className={styles.toolbarButtonPrimary}
              >
                {isSubmitting ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                    {t('tableModal.savingBtn')}
                  </>
                ) : (
                  <>
                    <Database className="w-4 h-4" />
                    {isEditMode ? t('tableModal.updateBtn') : t('tableModal.createBtn')}
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
