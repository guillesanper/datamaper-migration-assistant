// src/components/dashboard/DeleteConfirmModal.tsx
import React, { useState, useEffect } from 'react';
import { X, Loader2, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/button';
import type { Project } from '../../../types/project_types';
import { toast } from '../../../utils/toast';

interface DeleteConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (projectId: string) => Promise<void>;
  project: Project | null;
}

export const DeleteConfirmModal: React.FC<DeleteConfirmModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  project,
}) => {
  const { t } = useTranslation(['dashboard', 'common']);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string>('');
  const [confirmText, setConfirmText] = useState<string>('');

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !isDeleting) {
        handleClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, isDeleting]);

  const handleConfirm = async () => {
    if (!project) return;

    if (confirmText !== project.name) {
      setError(t('dashboard:modals.delete.confirmError'));
      return;
    }

    setIsDeleting(true);
    setError('');

    try {
      await onConfirm(project.id);
      toast.success(t('dashboard:modals.delete.success', { name: project.name }));
      handleClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('dashboard:modals.delete.error'));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleClose = () => {
    setConfirmText('');
    setError('');
    onClose();
  };

  if (!isOpen || !project) return null;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content modal-content-danger" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-100 dark:bg-red-900/20 rounded-lg">
              <AlertTriangle size={24} className="text-red-600 dark:text-red-400" />
            </div>
            <h2 className="modal-title">{t('dashboard:modals.delete.title')}</h2>
          </div>
          <button
            onClick={handleClose}
            className="btn-icon"
            disabled={isDeleting}
            aria-label={t('common:actions.close')}
          >
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {error && (
            <div className="alert alert-error">
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div className="p-4 bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-sm text-red-800 dark:text-red-200 font-medium mb-2">
                {t('dashboard:modals.delete.warning')}
              </p>
              <p className="text-sm text-red-700 dark:text-red-300">
                {t('dashboard:modals.delete.consequencesIntro')}
              </p>
              <ul className="mt-2 ml-4 text-sm text-red-700 dark:text-red-300 list-disc space-y-1">
                <li><strong>{t('dashboard:modals.delete.consequence1')}</strong></li>
                <li><strong>{t('dashboard:modals.delete.consequence2')}</strong></li>
                <li><strong>{t('dashboard:modals.delete.consequence3')}</strong></li>
              </ul>
            </div>

            <div>
              <p className="text-sm text-muted-foreground mb-2">
                {t('dashboard:modals.delete.aboutToDelete')}
              </p>
              <div className="p-3 bg-muted rounded-lg">
                <p className="font-medium text-foreground">{project.name}</p>
                {project.description && (
                  <p className="text-sm text-muted-foreground mt-1">
                    {project.description}
                  </p>
                )}
                <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
                  <span>{project.origin_db} → {project.destination_db}</span>
                  <span>•</span>
                  <span>{t('dashboard:modals.delete.progress', { percent: project.progress })}</span>
                </div>
              </div>
            </div>

            <div>
              <label htmlFor="confirm-text" className="form-label">
                {t('dashboard:modals.delete.confirmInstruction')} <strong>{project.name}</strong>
              </label>
              <input
                id="confirm-text"
                type="text"
                className="form-input"
                placeholder={t('dashboard:modals.delete.confirmPlaceholder')}
                value={confirmText}
                onChange={(e) => {
                  setConfirmText(e.target.value);
                  if (error) setError('');
                }}
                disabled={isDeleting}
                autoComplete="off"
              />
              {error && (
                <span className="form-error">{error}</span>
              )}
            </div>
          </div>

          <div className="modal-footer">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={isDeleting}
            >
              {t('common:actions.cancel')}
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleConfirm}
              disabled={isDeleting || !confirmText}
            >
              {isDeleting ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  {t('dashboard:modals.delete.deletingBtn')}
                </>
              ) : (
                t('dashboard:modals.delete.submitBtn')
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
