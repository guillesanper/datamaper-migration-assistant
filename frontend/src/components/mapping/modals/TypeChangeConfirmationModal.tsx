// frontend/src/components/mapping/modals/TypeChangeConfirmationModal.tsx
import React from "react";
import { AlertTriangle, Info, Shield, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TypeValidationResult } from "../../../types/mapping-types";

interface TypeChangeConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  validation: TypeValidationResult | null;
  isLoading?: boolean;
}

export const TypeChangeConfirmationModal: React.FC<TypeChangeConfirmationModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  validation,
  isLoading = false
}) => {
  const { t } = useTranslation(['mapping', 'common']);

  if (!isOpen || !validation) return null;

  const { risk_level, message, recommendation, old_type, new_type, affected_rows, examples } = validation;

  const getRiskLevelConfig = () => {
    switch (risk_level) {
      case 'danger':
        return {
          icon: <AlertTriangle className="w-12 h-12 text-red-500" />,
          title: t('mapping:typeChange.riskLevel.danger'),
          borderColor: 'border-red-500',
          bgColor: 'bg-red-50',
          textColor: 'text-red-700',
          buttonColor: 'bg-red-600 hover:bg-red-700'
        };
      case 'warning':
        return {
          icon: <AlertTriangle className="w-12 h-12 text-yellow-500" />,
          title: t('mapping:typeChange.riskLevel.warning'),
          borderColor: 'border-yellow-500',
          bgColor: 'bg-yellow-50',
          textColor: 'text-yellow-700',
          buttonColor: 'bg-yellow-600 hover:bg-yellow-700'
        };
      default:
        return {
          icon: <Info className="w-12 h-12 text-blue-500" />,
          title: t('mapping:typeChange.riskLevel.info'),
          borderColor: 'border-blue-500',
          bgColor: 'bg-blue-50',
          textColor: 'text-blue-700',
          buttonColor: 'bg-blue-600 hover:bg-blue-700'
        };
    }
  };

  const config = getRiskLevelConfig();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
      <div className="bg-background rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className={`flex items-center justify-between p-6 border-b-4 ${config.borderColor}`}>
          <div className="flex items-center gap-4">
            {config.icon}
            <div>
              <h2 className="text-2xl font-bold">{config.title}</h2>
              {validation.column_name && validation.table_name && (
                <p className="text-sm text-muted-foreground mt-1">
                  {t('mapping:typeChange.column', { table: validation.table_name, column: validation.column_name })}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-muted rounded-lg transition-colors"
            disabled={isLoading}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Type Change Summary */}
          <div className={`p-4 rounded-lg border-2 ${config.borderColor} ${config.bgColor}`}>
            <h3 className="font-semibold text-lg mb-3">{t('mapping:typeChange.warning')}</h3>
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground min-w-[80px]">{t('mapping:typeChange.currentType')}</span>
                <code className="px-3 py-1 bg-background rounded font-mono font-bold">
                  {old_type}
                </code>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground min-w-[80px]">{t('mapping:typeChange.newType')}</span>
                <code className="px-3 py-1 bg-background rounded font-mono font-bold">
                  {new_type}
                </code>
              </div>
            </div>
          </div>

          {/* Message */}
          <div>
            <h3 className="font-semibold text-lg mb-2">{t('mapping:typeChange.riskDesc')}</h3>
            <p className={`text-sm ${config.textColor}`}>{message}</p>
          </div>

          {/* Affected Rows */}
          {affected_rows !== undefined && affected_rows > 0 && (
            <div className="p-4 bg-muted rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="w-4 h-4 text-orange-500" />
                <h3 className="font-semibold">{t('mapping:typeChange.affectedRows')}</h3>
              </div>
              <p className="text-sm text-muted-foreground">
                {t('mapping:typeChange.affectedRowsDesc', { count: affected_rows.toLocaleString() })}
              </p>
            </div>
          )}

          {/* Examples */}
          {examples && examples.length > 0 && (
            <div className="p-4 bg-muted rounded-lg">
              <h3 className="font-semibold mb-2">{t('mapping:typeChange.examples')}</h3>
              <div className="space-y-1">
                {examples.slice(0, 5).map((example, idx) => (
                  <div key={idx} className="text-sm font-mono bg-background p-2 rounded">
                    {example}
                  </div>
                ))}
                {examples.length > 5 && (
                  <p className="text-xs text-muted-foreground mt-2">
                    {t('mapping:typeChange.moreExamples', { count: examples.length - 5 })}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Recommendation */}
          <div className="p-4 bg-blue-50 dark:bg-blue-950 rounded-lg border border-blue-200 dark:border-blue-800">
            <div className="flex items-start gap-3">
              <Info className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="font-semibold text-blue-700 dark:text-blue-300 mb-1">
                  {t('mapping:typeChange.recommendation')}
                </h3>
                <p className="text-sm text-blue-600 dark:text-blue-400">{recommendation}</p>
              </div>
            </div>
          </div>

          {/* Backup Notice */}
          {validation.requires_backup && (
            <div className="p-4 bg-green-50 dark:bg-green-950 rounded-lg border border-green-200 dark:border-green-800">
              <div className="flex items-start gap-3">
                <Shield className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-green-700 dark:text-green-300 mb-1">
                    {t('mapping:typeChange.backup.title')}
                  </h3>
                  <p className="text-sm text-green-600 dark:text-green-400">
                    {t('mapping:typeChange.backup.desc')}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Warning about confirmation */}
          {risk_level === 'danger' && (
            <div className="p-4 bg-red-50 dark:bg-red-950 rounded-lg border-2 border-red-500">
              <p className="text-sm text-red-700 dark:text-red-300 font-semibold">
                {t('mapping:typeChange.danger.warning')}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t bg-muted/50">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-border hover:bg-muted transition-colors"
            disabled={isLoading}
          >
            {t('common:actions.cancel')}
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-6 py-2 rounded-lg text-white font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${config.buttonColor}`}
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                {t('mapping:typeChange.applying')}
              </span>
            ) : (
              <span>
                {risk_level === 'danger' ? t('mapping:typeChange.confirmDanger') : t('mapping:typeChange.confirmBackup')}
              </span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
