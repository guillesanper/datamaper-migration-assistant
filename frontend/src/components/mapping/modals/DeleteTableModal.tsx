// src/components/mapping/modals/DeleteTableModal.tsx
import React, { useState } from 'react';
import { X, AlertTriangle, Database } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { mappingService } from '../../../services/mapping_service';
import { toast } from '../../../utils/toast';
import type { Table } from '../../../types/mapping-types';
import styles from '../../../styles/mapping/mapping.module.css';

interface DeleteTableModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  table: Table | null;
  onSuccess: () => void;
}

export const DeleteTableModal: React.FC<DeleteTableModalProps> = ({
  isOpen,
  onClose,
  projectId,
  table,
  onSuccess
}) => {
  const { t } = useTranslation(['mapping', 'common']);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    if (!table) return;

    setIsDeleting(true);

    try {
      const result = await mappingService.deleteTable(projectId, table.id);
      toast.success(t('deleteTable.toast.success', {
        columns: result.columns_deleted,
        mappings: result.mappings_deleted,
      }));
      onSuccess();
      onClose();
    } catch (err: unknown) {
      console.error('Error al eliminar tabla:', err);
      const errObj = err as Record<string, unknown>;
      const responseDetail = (errObj.response as Record<string, unknown> | undefined)?.data as Record<string, unknown> | undefined;
      const errorMessage = String(responseDetail?.detail ?? '') || (err instanceof Error ? err.message : '') || t('deleteTable.toast.error');
      toast.error(errorMessage);
    } finally {
      setIsDeleting(false);
    }
  };

  if (!isOpen || !table) return null;

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modalContent} style={{ maxWidth: '500px' }}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-500" />
            <h2 className={styles.modalTitle}>{t('deleteTable.title')}</h2>
          </div>
          <button onClick={onClose} className={styles.modalCloseButton} disabled={isDeleting}>
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className={styles.modalBody}>
          <div className="space-y-4">
            {/* Tabla info */}
            <div className="bg-muted p-4 rounded-lg border-l-4 border-l-red-500">
              <div className="flex items-center gap-3">
                <Database className={`w-6 h-6 ${
                  table.type === 'origin' ? 'text-blue-500' : 'text-green-500'
                }`} />
                <div>
                  <p className="font-semibold">{table.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {table.type === 'origin' ? t('deleteTable.tableType.origin') : t('deleteTable.tableType.dest')}
                  </p>
                </div>
              </div>
            </div>

            {/* Warning */}
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <div className="flex gap-3">
                <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-red-900 dark:text-red-100">
                    {t('deleteTable.irreversible')}
                  </p>
                  <ul className="text-sm text-red-800 dark:text-red-200 space-y-1 list-disc list-inside">
                    <li>{t('deleteTable.consequence1')}</li>
                    <li>{t('deleteTable.consequence2')}</li>
                    <li>{t('deleteTable.consequence3')}</li>
                  </ul>
                </div>
              </div>
            </div>

            {/* Confirmation */}
            <p className="text-sm text-muted-foreground">
              {t('deleteTable.warning', { name: table.name })}
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className={styles.modalFooter}>
          <div className={styles.modalFooterRight}>
            <button
              onClick={onClose}
              className={styles.toolbarButton}
              disabled={isDeleting}
            >
              {t('common:actions.cancel')}
            </button>
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isDeleting ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                  {t('deleteTable.deletingBtn')}
                </>
              ) : (
                <>
                  <AlertTriangle className="w-4 h-4" />
                  {t('deleteTable.submitBtn')}
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
