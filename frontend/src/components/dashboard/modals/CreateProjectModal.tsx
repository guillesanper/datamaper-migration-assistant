// src/components/dashboard/CreateProjectModal.tsx
import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom';
import { X, Loader2, Lock, Eye, EyeOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../ui/select';
import type { CreateProjectDTO, ProjectStatus } from '../../../types/project_types';
import { encryptionService } from '../../../services/encryption.service';
import { secureCleanupObject } from '../../../utils/secureMemory';

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  onSubmit: (data: CreateProjectDTO) => Promise<{ id: string; name: string }>;
}

interface FormState {
  name: string;
  description: string;
  origin_db: string;
  destination_db: string;
  status: ProjectStatus;
  progress: number;
  budget: number;
  enableEncryption: boolean;
  passphrase: string;
}

export const CreateProjectModal: React.FC<CreateProjectModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  onSubmit,
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
    enableEncryption: false,
    passphrase: '',
  });

  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState<string>('');
  const [showPassphrase, setShowPassphrase] = useState(false);

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
      secureCleanupObject(formData as unknown as Record<string, unknown>, ['passphrase']);
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

    if (formData.enableEncryption) {
      if (!formData.passphrase.trim()) {
        newErrors.passphrase = t('dashboard:modals.create.validation.passphraseRequired');
      } else if (formData.passphrase.length < 12) {
        newErrors.passphrase = t('dashboard:modals.create.validation.passphraseMin');
      } else {
        const hasUpperCase = /[A-Z]/.test(formData.passphrase);
        const hasLowerCase = /[a-z]/.test(formData.passphrase);
        const hasNumber = /[0-9]/.test(formData.passphrase);

        if (!hasUpperCase || !hasLowerCase) {
          newErrors.passphrase = t('dashboard:modals.create.validation.passphraseCasing');
        } else if (!hasNumber) {
          newErrors.passphrase = t('dashboard:modals.create.validation.passphraseNumber');
        }
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError('');

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);

    try {
      const projectData: CreateProjectDTO = {
        name: formData.name.trim(),
        description: formData.description.trim(),
        origin_db: formData.origin_db.trim(),
        destination_db: formData.destination_db.trim(),
        status: formData.status,
        progress: formData.progress,
        budget: formData.budget,
      };

      const createdProject = await onSubmit(projectData);

      if (formData.enableEncryption && formData.passphrase.trim()) {
        try {
          await encryptionService.setupEncryption(
            createdProject.id,
            formData.passphrase.trim()
          );
          secureCleanupObject(formData as unknown as Record<string, unknown>, ['passphrase']);
        } catch (encryptionError: unknown) {
          console.error('[CreateProjectModal] Error setting up encryption:', encryptionError);
          secureCleanupObject(formData as unknown as Record<string, unknown>, ['passphrase']);
          setApiError(
            t('dashboard:modals.create.encryptionError', {
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
      secureCleanupObject(formData as unknown as Record<string, unknown>, ['passphrase']);
    }
  };

  const handleClose = () => {
    secureCleanupObject(formData as unknown as Record<string, unknown>, ['passphrase']);

    setFormData({
      name: '',
      description: '',
      origin_db: '',
      destination_db: '',
      status: 'active',
      progress: 0,
      budget: 0,
      enableEncryption: false,
      passphrase: '',
    });
    setErrors({});
    setApiError('');
    setShowPassphrase(false);
    onClose();
  };

  const handleChange = (
    field: keyof FormState,
    value: string | number | boolean
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

  if (!isOpen) return null;

  return ReactDOM.createPortal(
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">{t('dashboard:modals.create.title')}</h2>
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
            <label htmlFor="name" className="form-label">
              {t('dashboard:modals.create.nameLabel')} <span className="text-red-500">*</span>
            </label>
            <input
              id="name"
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
            <label htmlFor="description" className="form-label">
              {t('dashboard:modals.create.descLabel')}
            </label>
            <textarea
              id="description"
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
              <label htmlFor="origin_db" className="form-label">
                {t('dashboard:modals.create.originLabel')} <span className="text-red-500">*</span>
              </label>
              <Select
                value={formData.origin_db}
                onValueChange={(val) => handleChange('origin_db', val)}
                disabled={isLoading}
              >
                <SelectTrigger
                  id="origin_db"
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
              <label htmlFor="destination_db" className="form-label">
                {t('dashboard:modals.create.destLabel')} <span className="text-red-500">*</span>
              </label>
              <Select
                value={formData.destination_db}
                onValueChange={(val) => handleChange('destination_db', val)}
                disabled={isLoading}
              >
                <SelectTrigger
                  id="destination_db"
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
              <label htmlFor="status" className="form-label">
                {t('dashboard:modals.create.statusLabel')}
              </label>
              <Select
                value={formData.status}
                onValueChange={(val) => handleChange('status', val as ProjectStatus)}
                disabled={isLoading}
              >
                <SelectTrigger id="status" className="w-full">
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
              <label htmlFor="progress" className="form-label">
                {t('dashboard:modals.create.progressLabel')}
              </label>
              <input
                id="progress"
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
            <label htmlFor="budget" className="form-label">
              {t('dashboard:modals.create.budgetLabel')}
            </label>
            <input
              id="budget"
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

          <div className="border-t pt-4 mt-4">
            <div className="flex items-center gap-2 mb-4">
              <Lock className="w-5 h-5 text-primary" />
              <h3 className="text-sm font-semibold">{t('dashboard:modals.create.encryptionSection')}</h3>
            </div>

            <div className="form-group">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.enableEncryption}
                  onChange={(e) => handleChange('enableEncryption', e.target.checked)}
                  disabled={isLoading}
                  className="w-4 h-4 text-primary border-gray-300 rounded focus:ring-primary"
                />
                <span className="text-sm">{t('dashboard:modals.create.encryptionToggle')}</span>
              </label>
              <p className="text-xs text-muted-foreground mt-1 ml-6">
                {t('dashboard:modals.create.encryptionHint')}
              </p>
            </div>

            {formData.enableEncryption && (
              <div className="form-group mt-3">
                <label htmlFor="passphrase" className="form-label">
                  {t('dashboard:modals.create.passphraseLabel')} <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <input
                    id="passphrase"
                    type={showPassphrase ? 'text' : 'password'}
                    className={`form-input pr-10 ${errors.passphrase ? 'form-input-error' : ''}`}
                    placeholder={t('dashboard:modals.create.passphrasePlaceholder')}
                    value={formData.passphrase}
                    onChange={(e) => handleChange('passphrase', e.target.value)}
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
                <p className="text-xs text-muted-foreground mt-1">
                  {t('dashboard:modals.create.passphraseHint')}
                </p>
                {errors.passphrase && (
                  <span className="form-error">{errors.passphrase}</span>
                )}
                <p className="text-xs text-muted-foreground mt-1">
                  {t('dashboard:modals.create.passphraseImportant')}
                </p>
              </div>
            )}
          </div>

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
                  {t('dashboard:modals.create.creatingBtn')}
                </>
              ) : (
                t('dashboard:modals.create.submitBtn')
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
};
