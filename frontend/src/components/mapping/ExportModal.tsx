// src/components/mapping/ExportModal.tsx
import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, FileText, Table, FileSpreadsheet, X, AlertTriangle, CheckCircle } from '../icons';
import { mappingService } from '../../services/mapping_service';
import { type Mapping } from '../../types/mapping-types';
import { toast } from '../../utils/toast';
import styles from '../../styles/mapping/mapping.module.css';

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
}

export const ExportModal: React.FC<ExportModalProps> = ({
  isOpen,
  onClose,
  projectId,
}) => {
  const { t } = useTranslation(['mapping', 'common']);
  const [selectedFormat, setSelectedFormat] = useState<'json' | 'csv' | 'excel'>('json');
  const [isExporting, setIsExporting] = useState(false);
  const [validationResult, setValidationResult] = useState<{
    isValid: boolean;
    errors: string[];
  } | null>(null);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [isMappingsLoading, setIsMappingsLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      validateMappings();
      fetchMappings();
    } else {
      setMappings([]);
      setIsMappingsLoading(false);
      setValidationResult(null);
    }
  }, [isOpen]);

  const validateMappings = async () => {
    try {
      const result = await mappingService.validateMappings(projectId);
      setValidationResult(result);
    } catch (error) {
      console.error('Validation error:', error);
    }
  };

  const fetchMappings = async () => {
    setIsMappingsLoading(true);
    try {
      const result = await mappingService.getMappings(projectId);
      setMappings(result);
    } catch (error) {
      console.error('Error fetching mappings for export:', error);
    } finally {
      setIsMappingsLoading(false);
    }
  };


  const handleExport = async () => {
    setIsExporting(true);
    try {
      const blob = await mappingService.exportMappings(projectId, selectedFormat);

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `mappings_${projectId}_${new Date().toISOString().split('T')[0]}.${
        selectedFormat === 'excel' ? 'xlsx' : selectedFormat
      }`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast.success(t('export.success'));
      onClose();
    } catch (error: unknown) {
      console.error('Export error:', error);

      let errorMessage = t('export.error');

      const errObj = error as Record<string, unknown>;
      const responseData = errObj.response as Record<string, unknown> | undefined;
      const responseDataBody = responseData?.data as Record<string, unknown> | undefined;
      if (responseDataBody?.detail) {
        errorMessage = String(responseDataBody.detail);
      } else if (responseDataBody?.message) {
        errorMessage = String(responseDataBody.message);
      } else if (errObj.detail) {
        errorMessage = String(errObj.detail);
      } else if (error instanceof Error) {
        errorMessage = error.message;
      } else if (typeof error === 'string') {
        errorMessage = error;
      }

      if (errorMessage.length > 200) {
        errorMessage = errorMessage.substring(0, 200) + '...';
      }

      toast.error(errorMessage, {
        duration: 5000,
      });
    } finally {
      setIsExporting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modalContent}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>{t('export.title')}</h2>
          <button onClick={onClose} className={styles.modalCloseButton}>
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className={styles.modalBody}>
          {/* Statistics */}
          <div className={styles.statsGrid}>
            <div className={styles.statsCard}>
              <div className={styles.statsValue}>
                {isMappingsLoading
                  ? <div className="animate-spin rounded-full h-4 w-4 border-2 border-primary border-t-transparent mx-auto" />
                  : mappings.length}
              </div>
              <div className={styles.statsLabel}>{t('export.stats.total')}</div>
            </div>
            <div className={styles.statsCard}>
              <div className={styles.statsValue}>
                {isMappingsLoading
                  ? <div className="animate-spin rounded-full h-4 w-4 border-2 border-primary border-t-transparent mx-auto" />
                  : new Set(mappings.map(m => m.origin_table)).size}
              </div>
              <div className={styles.statsLabel}>{t('export.stats.originTables')}</div>
            </div>
            <div className={styles.statsCard}>
              <div className={styles.statsValue}>
                {isMappingsLoading
                  ? <div className="animate-spin rounded-full h-4 w-4 border-2 border-primary border-t-transparent mx-auto" />
                  : new Set(mappings.map(m => m.destination_table)).size}
              </div>
              <div className={styles.statsLabel}>{t('export.stats.destTables')}</div>
            </div>
          </div>

          {/* Validation Results */}
          {validationResult && (
            <div className={`${styles.alert} ${
              validationResult.isValid ? styles.alertSuccess : styles.alertWarning
            }`}>
              <div className={styles.alertContent}>
                {validationResult.isValid ? (
                  <CheckCircle className={`${styles.alertIcon} ${styles.alertIconSuccess}`} />
                ) : (
                  <AlertTriangle className={`${styles.alertIcon} ${styles.alertIconWarning}`} />
                )}
                <div className={styles.alertBody}>
                  <h4 className={`${styles.alertTitle} ${
                    validationResult.isValid
                      ? styles.alertTitleSuccess
                      : styles.alertTitleWarning
                  }`}>
                    {validationResult.isValid
                      ? t('export.validation.ok')
                      : t('export.validation.warnings', { count: validationResult.errors.length })
                    }
                  </h4>
                  {!validationResult.isValid && validationResult.errors.length > 0 && (
                    <ul className={styles.alertList}>
                      {validationResult.errors.map((error, index) => (
                        <li key={index} className={styles.alertListItemWarning}>
                          • {error}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Format selector */}
          <div>
            <label className="text-sm font-medium mb-3 block">{t('export.format.label')}</label>
            <div className={styles.formatGrid}>
              <button
                onClick={() => setSelectedFormat('json')}
                className={`${styles.formatButton} ${
                  selectedFormat === 'json'
                    ? styles.formatButtonActive
                    : styles.formatButtonInactive
                }`}
              >
                <FileText className={styles.formatIcon} />
                <div className={styles.formatName}>JSON</div>
                <div className={styles.formatDescription}>{t('export.format.jsonLabel')}</div>
              </button>

              <button
                onClick={() => setSelectedFormat('csv')}
                className={`${styles.formatButton} ${
                  selectedFormat === 'csv'
                    ? styles.formatButtonActive
                    : styles.formatButtonInactive
                }`}
              >
                <Table className={styles.formatIcon} />
                <div className={styles.formatName}>CSV</div>
                <div className={styles.formatDescription}>{t('export.format.csvLabel')}</div>
              </button>

              <button
                onClick={() => setSelectedFormat('excel')}
                className={`${styles.formatButton} ${
                  selectedFormat === 'excel'
                    ? styles.formatButtonActive
                    : styles.formatButtonInactive
                }`}
              >
                <FileSpreadsheet className={styles.formatIcon} />
                <div className={styles.formatName}>Excel</div>
                <div className={styles.formatDescription}>{t('export.format.excelLabel')}</div>
              </button>
            </div>

            <p className="text-sm text-muted-foreground mt-3">
              {{
                json: t('export.format.jsonDesc'),
                csv: t('export.format.csvDesc'),
                excel: t('export.format.excelDesc')
              }[selectedFormat]}
            </p>
          </div>

          {/* Export options */}
          <div className="space-y-3">
            <label className="flex items-center gap-3">
              <input type="checkbox" className="w-4 h-4" defaultChecked />
              <span className="text-sm">{t('export.options.metadata')}</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" className="w-4 h-4" defaultChecked />
              <span className="text-sm">{t('export.options.dataTypes')}</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" className="w-4 h-4" />
              <span className="text-sm">{t('export.options.sqlScript')}</span>
            </label>
          </div>
        </div>

        {/* Footer */}
        <div className={styles.modalFooter}>
          <div className={styles.modalFooterLeft}>
            {isMappingsLoading
              ? t('export.footer.loading')
              : mappings.length === 0
                ? t('export.footer.empty')
                : t('export.footer.ready', { count: mappings.length })
            }
          </div>
          <div className={styles.modalFooterRight}>
            <button
              onClick={onClose}
              className={styles.toolbarButton}
              disabled={isExporting}
            >
              {t('common:actions.cancel')}
            </button>
            <button
              onClick={handleExport}
              disabled={isExporting || isMappingsLoading || mappings.length === 0}
              className={styles.toolbarButtonPrimary}
            >
              {isExporting ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                  {t('export.exporting')}
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  {t('export.submit')}
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
