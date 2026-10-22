// src/components/mapping/modals/TlsSkipConfirmModal.tsx
import React, { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { confirmsHostname } from '../../../utils/tls';
import styles from '../../../styles/mapping/mapping-modals.module.css';

interface TlsSkipConfirmModalProps {
  isOpen: boolean;
  /** Host de la conexión: hay que escribirlo para confirmar */
  host: string;
  onConfirm: (typedHostname: string) => void;
  onCancel: () => void;
}

/**
 * Confirmación para desactivar la verificación del certificado.
 *
 * Es solo ayuda de UX: el backend exige confirm_hostname == host en /test y /sessions, así
 * que una llamada directa a la API tampoco puede saltarse la verificación sin confirmarlo.
 */
export const TlsSkipConfirmModal: React.FC<TlsSkipConfirmModalProps> = ({
  isOpen,
  host,
  onConfirm,
  onCancel,
}) => {
  const { t } = useTranslation('mapping');
  const [typed, setTyped] = useState('');
  const [showMismatch, setShowMismatch] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setTyped('');
      setShowMismatch(false);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  const matches = confirmsHostname(typed, host);

  const handleConfirm = () => {
    if (!matches) {
      setShowMismatch(true);
      return;
    }
    onConfirm(typed);
  };

  return (
    <div
      className={styles.modalOverlay}
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        className={styles.modalContent}
        style={{ maxWidth: '32rem' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tls-skip-confirm-title"
      >
        <div className={styles.modalHeader}>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-100 dark:bg-amber-900/20 rounded-lg">
              <AlertTriangle size={22} className="text-amber-600 dark:text-amber-400" />
            </div>
            <h2 id="tls-skip-confirm-title" className={styles.modalTitle}>
              {t('db.tls.confirm.title')}
            </h2>
          </div>
          <button onClick={onCancel} className={styles.modalCloseButton} aria-label={t('db.tls.confirm.cancel')}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className={styles.modalBody}>
          <div className="p-4 bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800 rounded-lg">
            <p className="text-sm text-amber-900 dark:text-amber-200 font-medium">
              {t('db.tls.confirm.warning')}
            </p>
            <p className="text-sm text-amber-800 dark:text-amber-300 mt-2">
              {t('db.tls.confirm.description')}
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="tls-skip-confirm-host" className="text-sm font-medium">
              {t('db.tls.confirm.hostLabel')} <strong>{host}</strong>
            </label>
            <input
              id="tls-skip-confirm-host"
              type="text"
              value={typed}
              onChange={(e) => {
                setTyped(e.target.value);
                if (showMismatch) setShowMismatch(false);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleConfirm();
              }}
              placeholder={t('db.tls.confirm.placeholder')}
              autoComplete="off"
              autoFocus
              className={`px-3 py-2 border rounded-md bg-background ${
                showMismatch ? 'border-red-500' : 'border-border'
              }`}
            />
            {showMismatch && (
              <span className="text-xs text-red-500">{t('db.tls.confirm.mismatch')}</span>
            )}
          </div>
        </div>

        <div className={styles.modalFooter}>
          <div className={styles.modalFooterLeft} />
          <div className={styles.modalFooterRight}>
            <button
              onClick={onCancel}
              className="px-4 py-2 border border-border rounded-md hover:bg-muted transition-colors"
            >
              {t('db.tls.confirm.cancel')}
            </button>
            <button
              onClick={handleConfirm}
              disabled={!typed}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('db.tls.confirm.confirmButton')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
