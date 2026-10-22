// src/components/mapping/TlsUnverifiedBadge.tsx
import React from 'react';
import { ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface TlsUnverifiedBadgeProps {
  className?: string;
}

/**
 * Marca una conexión que se creó sin verificar el certificado del servidor.
 * El backend la mantiene durante toda la vida de la sesión (tls_verified=false).
 */
export const TlsUnverifiedBadge: React.FC<TlsUnverifiedBadgeProps> = ({ className = '' }) => {
  const { t } = useTranslation('mapping');

  return (
    <span
      role="status"
      title={t('db.tls.unverifiedTooltip')}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-700 ${className}`}
    >
      <ShieldAlert className="w-3 h-3" aria-hidden="true" />
      {t('db.tls.unverifiedBadge')}
    </span>
  );
};
