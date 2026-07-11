// src/components/dashboard/EditProjectModal.tsx
import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom';
import { X, Loader2, Lock, Eye, EyeOff, AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../ui/select';
import type { Project, UpdateProjectDTO, ProjectStatus } from '../../../types/project_types';
import { encryptionService } from '../../../services/encryption.service';
import { secureCleanupState } from '../../../utils/secureMemory';

interface EditProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  onSubmit: (projectId: string, data: UpdateProjectDTO) => Promise<void>;
  project: Project | null;
}

interface FormState {
  name: string;
  description: string;
  origin_db: string;
  destination_db: string;
  status: ProjectStatus;
  progress: number;
  budget: number;
}

export const EditProjectModal: React.FC<EditProjectModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  onSubmit,
  project,
}) => {
  const { t } = useTranslation(['dashboard', 'common']);
  const [formData, setFormData] = useState<FormState>({
    name: '',
    description: '',
    origin_db: '',
    destination_db: '',
    status: 'active',
    progress: 0,
    budget: 0,
  });

  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState<string>('');

  const [encryptionEnabled, setEncryptionEnabled] = useState(false);
  const [wantsToChangeEncryption, setWantsToChangeEncryption] = useState(false);
  const [passphrase, setPassphrase] = useState('');
  const [showPassphrase, setShowPassphrase] = useState(false);
  const [passphraseError, setPassphraseError] = useState<string>('');

  useEffect(() => {
    if (project) {
      setFormData({
        name: project.name,
        description: project.description || '',
        origin_db: project.origin_db,
        destination_db: project.destination_db,
        status: project.status,
        progress: project.progress,
        budget: project.budget,
      });

      setEncryptionEnabled(project.encryption_enabled || false);
      setWantsToChangeEncryption(false);
      setPassphrase('');
      setPassphraseError('');
    }
  }, [project]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !isLoading) {
        handleClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, isLoading]);

  // FASE 2.3: Auto-cleanup al desmontar componente
  useEffect(() => {
    return () => {
      secureCleanupState(setPassphrase);
    };
  }, []);

  const validateForm = (): boolean => {
    const newErrors: Partial<Record<keyof FormState, string>> = {};

    if (!formData.name.trim()) {
      newErrors.name = t('dashboard:modals.create.validation.nameRequired');
    } else if (formData.name.length < 3) {
      newErrors.name = t('dashboard:modals.create.validation.nameMin');
    } else if (formData.name.length > 100) {
      newErrors.name = t('dashboard:modals.create.validation.nameMax');
    }

    if (!formData.origin_db.trim()) {
      newErrors.origin_db = t('dashboard:modals.create.validation.originRequired');
    }

    if (!formData.destination_db.trim()) {
      newErrors.destination_db = t('dashboard:modals.create.validation.destRequired');
    }

    if (formData.progress < 0 || formData.progress > 100) {
      newErrors.progress = t('dashboard:modals.create.validation.progressRange');
    }

    if (formData.budget < 0) {
      newErrors.budget = t('dashboard:modals.create.validation.budgetNegative');
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError('');
    setPassphraseError('');

    if (!project) return;
    if (!validateForm()) return;

    if (wantsToChangeEncryption) {
      if (!passphrase.trim()) {
        setPassphraseError(t('dashboard:modals.edit.validation.passphraseForChange'));
        return;
      }

      if (encryptionEnabled && !project.encryption_enabled) {
        if (passphrase.length < 12) {
          setPassphraseError(t('dashboard:modals.create.validation.passphraseMin'));
          return;
        }

        const hasUpperCase = /[A-Z]/.test(passphrase);
        const hasLowerCase = /[a-z]/.test(passphrase);
        const hasNumber = /[0-9]/.test(passphrase);

        if (!hasUpperCase || !hasLowerCase) {
          setPassphraseError(t('dashboard:modals.create.validation.passphraseCasing'));
          return;
        }

        if (!hasNumber) {
          setPassphraseError(t('dashboard:modals.create.validation.passphraseNumber'));
          return;
        }
      }
    }

    setIsLoading(true);

    try {
      const updateData: UpdateProjectDTO = {
        name: formData.name.trim(),
        description: formData.description.trim(),
        origin_db: formData.origin_db.trim(),
        destination_db: formData.destination_db.trim(),
        status: formData.status,
        progress: formData.progress,
        budget: formData.budget,
      };

      await onSubmit(project.id, updateData);

      if (wantsToChangeEncryption && passphrase.trim()) {
        try {
          if (!encryptionEnabled && project.encryption_enabled) {
            await encryptionService.disableEncryption(project.id);
          } else if (encryptionEnabled && !project.encryption_enabled) {
            await encryptionService.setupEncryption(project.id, passphrase.trim());
          }

          secureCleanupState(setPassphrase);
        } catch (encryptionError: unknown) {
          console.error('[EditProjectModal] Error changing encryption state:', encryptionError);
          secureCleanupState(setPassphrase);
          setApiError(
            t('dashboard:modals.edit.encryptionError', {
              error: encryptionError instanceof Error
                ? encryptionError.message
                : t('common:errors.generic'),
            })
          );
          setIsLoading(false);
          return;
        }
      }

      handleClose();
      onSuccess();
    } catch (error: unknown) {
      setApiError(error instanceof Error ? error.message : t('common:errors.generic'));
    } finally {
      setIsLoading(false);
      secureCleanupState(setPassphrase);
    }
  };

  const handleClose = () => {
    secureCleanupState(setPassphrase);

    setErrors({});
    setApiError('');
    setPassphrase('');
    setPassphraseError('');
    setWantsToChangeEncryption(false);
    setShowPassphrase(false);
    onClose();
  };

  const handleEncryptionToggle = (newValue: boolean) => {
    if (!project) return;

    const hasChanged = newValue !== project.encryption_enabled;
    setEncryptionEnabled(newValue);
    setWantsToChangeEncryption(hasChanged);

    if (hasChanged) {
      secureCleanupState(setPassphrase);
      setPassphrase('');
      setPassphraseError('');
    }
  };

  const handleChange = (
    field: keyof FormState,
    value: string | number
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };

  if (!isOpen || !project) return null;

  return ReactDOM.createPortal(
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{t('dashboard:modals.edit.title')}</h2>
          <button
            onClick={handleClose}
            className="btn-icon"
            disabled={isLoading}
            aria-label={t('common:actions.close')}
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-body">
          {apiError && (
            <div className="alert alert-error">
              {apiError}
            </div>
          )}

          <div className="form-group">
            <label htmlFor="edit-name" className="form-label">
              {t('dashboard:modals.create.nameLabel')} <span className="text-red-500">*</span>
            </label>
            <input
              id="edit-name"
              type="text"
              className={`form-input ${errors.name ? 'form-input-error' : ''}`}
              placeholder={t('dashboard:modals.create.namePlaceholder')}
              value={formData.name}
              onChange={(e) => handleChange('name', e.target.value)}
              disabled={isLoading}
              maxLength={100}
            />
            {errors.name && (
              <span className="form-error">{errors.name}</span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="edit-description" className="form-label">
              {t('dashboard:modals.create.descLabel')}
            </label>
            <textarea
              id="edit-description"
              className="form-input form-textarea"
              placeholder={t('dashboard:modals.create.descPlaceholder')}
              value={formData.description}
              onChange={(e) => handleChange('description', e.target.value)}
              disabled={isLoading}
              rows={3}
              maxLength={500}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="edit-origin-db" className="form-label">
                {t('dashboard:modals.create.originLabel')} <span className="text-red-500">*</span>
              </label>
              <Select
                value={formData.origin_db}
                onValueChange={(val) => handleChange('origin_db', val)}
                disabled={isLoading}
              >
                <SelectTrigger
                  id="edit-origin-db"
                  className={`w-full ${errors.origin_db ? 'border-destructive' : ''}`}
                >
                  <SelectValue placeholder={t('dashboard:modals.create.originPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PostgreSQL">{t('dashboard:modals.create.db.postgres')}</SelectItem>
                  <SelectItem value="MySQL">{t('dashboard:modals.create.db.mysql')}</SelectItem>
                  <SelectItem value="SQL Server">{t('dashboard:modals.create.db.sqlserver')}</SelectItem>
                  <SelectItem value="Oracle">{t('dashboard:modals.create.db.oracle')}</SelectItem>
                  <SelectItem value="Otro">{t('dashboard:modals.create.db.other')}</SelectItem>
                </SelectContent>
              </Select>
              {errors.origin_db && (
                <span className="form-error">{errors.origin_db}</span>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="edit-destination-db" className="form-label">
                {t('dashboard:modals.create.destLabel')} <span className="text-red-500">*</span>
              </label>
              <Select
                value={formData.destination_db}
                onValueChange={(val) => handleChange('destination_db', val)}
                disabled={isLoading}
              >
                <SelectTrigger
                  id="edit-destination-db"
                  className={`w-full ${errors.destination_db ? 'border-destructive' : ''}`}
                >
                  <SelectValue placeholder={t('dashboard:modals.create.destPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PostgreSQL">{t('dashboard:modals.create.db.postgres')}</SelectItem>
                  <SelectItem value="MySQL">{t('dashboard:modals.create.db.mysql')}</SelectItem>
                  <SelectItem value="SQL Server">{t('dashboard:modals.create.db.sqlserver')}</SelectItem>
                  <SelectItem value="Oracle">{t('dashboard:modals.create.db.oracle')}</SelectItem>
                  <SelectItem value="Otro">{t('dashboard:modals.create.db.other')}</SelectItem>
                </SelectContent>
              </Select>
              {errors.destination_db && (
                <span className="form-error">{errors.destination_db}</span>
              )}
              {formData.destination_db && formData.destination_db !== 'Otro' && (
                <p className="text-xs text-muted-foreground mt-1">
                  {t('dashboard:modals.create.db.compatibleNote')}
                </p>
              )}
              {formData.destination_db === 'Otro' && (
                <p className="text-xs text-muted-foreground mt-1">
                  {t('dashboard:modals.create.db.incompatibleNote')}
                </p>
              )}
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="edit-status" className="form-label">
                {t('dashboard:modals.create.statusLabel')}
              </label>
              <Select
                value={formData.status}
                onValueChange={(val) => handleChange('status', val as ProjectStatus)}
                disabled={isLoading}
              >
                <SelectTrigger id="edit-status" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">{t('dashboard:projectRow.status.active')}</SelectItem>
                  <SelectItem value="paused">{t('dashboard:projectRow.status.paused')}</SelectItem>
                  <SelectItem value="completed">{t('dashboard:projectRow.status.completed')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="form-group">
              <label htmlFor="edit-progress" className="form-label">
                {t('dashboard:modals.create.progressLabel')}
              </label>
              <input
                id="edit-progress"
                type="number"
                className={`form-input ${errors.progress ? 'form-input-error' : ''}`}
                placeholder="0"
                min="0"
                max="100"
                value={formData.progress}
                onChange={(e) => handleChange('progress', Number(e.target.value))}
                disabled={isLoading}
              />
              {errors.progress && (
                <span className="form-error">{errors.progress}</span>
              )}
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="edit-budget" className="form-label">
              {t('dashboard:modals.create.budgetLabel')}
            </label>
            <input
              id="edit-budget"
              type="number"
              className={`form-input ${errors.budget ? 'form-input-error' : ''}`}
              placeholder="0"
              min="0"
              step="100"
              value={formData.budget}
              onChange={(e) => handleChange('budget', Number(e.target.value))}
              disabled={isLoading}
            />
            {errors.budget && (
              <span className="form-error">{errors.budget}</span>
            )}
          </div>

          {project.is_owner && (
            <div className="border-t pt-4 mt-4">
              <div className="flex items-center gap-2 mb-4">
                <Lock className="w-5 h-5 text-primary" />
                <h3 className="text-sm font-semibold">{t('dashboard:modals.create.encryptionSection')}</h3>
              </div>

              <div className="form-group">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={encryptionEnabled}
                    onChange={(e) => handleEncryptionToggle(e.target.checked)}
                    disabled={isLoading}
                    className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary"
                  />
                  <span className="text-sm">
                    {project.encryption_enabled
                      ? t('dashboard:modals.edit.encryptionActive')
                      : t('dashboard:modals.edit.encryptionActivate')}
                  </span>
                </label>
                <p className="text-xs text-muted-foreground mt-1 ml-6">
                  {project.encryption_enabled
                    ? t('dashboard:modals.edit.encryptionActiveDesc')
                    : t('dashboard:modals.edit.encryptionInactiveDesc')}
                </p>
              </div>

              {wantsToChangeEncryption && (
                <div className="mt-4 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                  <div className="flex items-start gap-2 mb-3">
                    <AlertCircle className="w-5 h-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold text-yellow-800 dark:text-yellow-200">
                        {encryptionEnabled
                          ? t('dashboard:modals.edit.activateEncryption')
                          : t('dashboard:modals.edit.deactivateEncryption')}
                      </p>
                      <p className="text-xs text-yellow-700 dark:text-yellow-300 mt-1">
                        {encryptionEnabled
                          ? t('dashboard:modals.edit.encryptedHint')
                          : t('dashboard:modals.edit.encryptDanger')}
                      </p>
                    </div>
                  </div>

                  <div className="form-group">
                    <label htmlFor="edit-passphrase" className="form-label">
                      {t('dashboard:modals.create.passphraseLabel')} <span className="text-red-500">*</span>
                    </label>
                    <div className="relative">
                      <input
                        id="edit-passphrase"
                        type={showPassphrase ? 'text' : 'password'}
                        className={`form-input pr-10 ${passphraseError ? 'form-input-error' : ''}`}
                        placeholder={encryptionEnabled
                          ? t('dashboard:modals.edit.newPassphrasePlaceholder')
                          : t('dashboard:modals.edit.confirmPassphrasePlaceholder')}
                        value={passphrase}
                        onChange={(e) => {
                          setPassphrase(e.target.value);
                          setPassphraseError('');
                        }}
                        disabled={isLoading}
                        autoComplete="new-password"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassphrase(!showPassphrase)}
                        disabled={isLoading}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                        tabIndex={-1}
                      >
                        {showPassphrase ? <EyeOff size={18} /> : <Eye size={18} />}
                      </button>
                    </div>
                    {encryptionEnabled && !project.encryption_enabled && (
                      <p className="text-xs text-muted-foreground mt-1">
                        {t('dashboard:modals.create.passphraseHint')}
                      </p>
                    )}
                    {passphraseError && (
                      <span className="form-error">{passphraseError}</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="modal-footer">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={isLoading}
            >
              {t('common:actions.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  {t('dashboard:modals.edit.savingBtn')}
                </>
              ) : (
                t('dashboard:modals.edit.submitBtn')
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
};
