// src/components/mapping/ImportModal.tsx
import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, Table, FileSpreadsheet, X, AlertCircle } from '../icons';
import { mappingService } from '../../services/mapping_service';
import { toast } from '../../utils/toast';
import styles from '../../styles/mapping/mapping.module.css';

interface ImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  onSuccess: () => void;
}

export const ImportModal: React.FC<ImportModalProps> = ({
  isOpen,
  onClose,
  projectId,
  onSuccess
}) => {
  const { t } = useTranslation(['mapping', 'common']);
  const [selectedFormat, setSelectedFormat] = useState<'json' | 'csv' | 'excel'>('json');
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [importType, setImportType] = useState<'origin' | 'destination' | 'both'>('both');
  const [duplicateStrategy, setDuplicateStrategy] = useState<'skip' | 'replace'>('skip');

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      const uploadedFile = acceptedFiles[0];

      const extension = uploadedFile.name.split('.').pop()?.toLowerCase();
      if (extension === 'json') setSelectedFormat('json');
      else if (extension === 'csv') setSelectedFormat('csv');
      else if (extension === 'xlsx' || extension === 'xls') setSelectedFormat('excel');

      setFile(uploadedFile);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/json': ['.json'],
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls']
    },
    maxFiles: 1,
    maxSize: 15 * 1024 * 1024
  });

  const handleImport = async () => {
    if (!file) {
      toast.error(t('import.error.noFile' as any));
      return;
    }

    setIsUploading(true);
    try {
      const response = await mappingService.importStructure(projectId, file, selectedFormat, duplicateStrategy);

      const totalSkipped = (response.tables_duplicates_skipped || 0) + (response.duplicates_skipped || 0);
      const parts: string[] = [];

      if (response.tables_added > 0)
        parts.push(t('import.result.tablesAdded', { count: response.tables_added } as any));
      if ((response.tables_replaced ?? 0) > 0)
        parts.push(t('import.result.tablesReplaced', { count: response.tables_replaced } as any));
      if (response.columns_added > 0)
        parts.push(t('import.result.columnsAdded', { count: response.columns_added } as any));

      if (parts.length === 0) {
        toast.success(t('import.nothingImported', { count: totalSkipped } as any));
      } else {
        if (totalSkipped > 0)
          parts.push(t('import.result.skipped', { count: totalSkipped } as any));
        toast.success(t('import.success', { details: parts.join(', ') } as any));
      }

      onSuccess();
      handleClose();
    } catch (error: unknown) {
      console.error('Import error:', error);
      toast.error(error instanceof Error ? error.message : t('common:errors.generic'));
    } finally {
      setIsUploading(false);
    }
  };

  const handleClose = () => {
    setFile(null);
    setSelectedFormat('json');
    setImportType('both');
    setDuplicateStrategy('skip');
    onClose();
  };

  if (!isOpen) return null;

  const formatExamples = {
    json: `{
  "tables": [
    {
      "name": "customers",
      "type": "origin",
      "columns": [...]
    }
  ]
}`,
    csv: `table_name,type,column_name,data_type
customers,origin,id,INTEGER
customers,origin,name,TEXT`,
    excel: t('import.example.excelHint' as any)
  };

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modalContent}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>{t('import.title' as any)}</h2>
          <button onClick={handleClose} className={styles.modalCloseButton}>
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className={styles.modalBody}>
          {/* Tipo de importación */}
          <div>
            <label className="text-sm font-medium mb-2 block">{t('import.type.label' as any)}</label>
            <div className="flex gap-3">
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  value="origin"
                  checked={importType === 'origin'}
                  onChange={(e) => setImportType(e.target.value as 'origin' | 'destination' | 'both')}
                  className="w-4 h-4"
                />
                <span>{t('import.type.originOnly' as any)}</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  value="destination"
                  checked={importType === 'destination'}
                  onChange={(e) => setImportType(e.target.value as 'origin' | 'destination' | 'both')}
                  className="w-4 h-4"
                />
                <span>{t('import.type.destOnly' as any)}</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  value="both"
                  checked={importType === 'both'}
                  onChange={(e) => setImportType(e.target.value as 'origin' | 'destination' | 'both')}
                  className="w-4 h-4"
                />
                <span>{t('import.type.both' as any)}</span>
              </label>
            </div>
          </div>

          {/* Manejo de Duplicados */}
          <div>
            <label className="text-sm font-medium mb-2 block">{t('import.duplicates.label' as any)}</label>
            <div className="flex gap-3">
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  value="skip"
                  checked={duplicateStrategy === 'skip'}
                  onChange={() => setDuplicateStrategy('skip')}
                  className="w-4 h-4"
                />
                <span>{t('import.duplicates.skip' as any)}</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  value="replace"
                  checked={duplicateStrategy === 'replace'}
                  onChange={() => setDuplicateStrategy('replace')}
                  className="w-4 h-4"
                />
                <span>{t('import.duplicates.replace' as any)}</span>
              </label>
            </div>
            <p className="text-xs text-muted-foreground mt-1.5">
              {duplicateStrategy === 'skip'
                ? t('import.duplicates.skipHint' as any)
                : t('import.duplicates.replaceHint' as any)}
            </p>
          </div>

          {/* Format selector */}
          <div>
            <label className="text-sm font-medium mb-2 block">{t('import.format.label' as any)}</label>
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
                <div className={styles.formatDescription}>{t('import.format.recommended' as any)}</div>
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
                <div className={styles.formatDescription}>{t('import.format.simple' as any)}</div>
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
                <div className={styles.formatDescription}>{t('import.format.compatible' as any)}</div>
              </button>
            </div>
          </div>

          {/* Dropzone */}
          <div>
            <label className="text-sm font-medium mb-2 block">{t('import.file.label' as any)}</label>
            <div
              {...getRootProps()}
              className={`${styles.dropzone} ${isDragActive ? styles.dropzoneActive : ''}`}
            >
              <input {...getInputProps()} />
              <Upload className={styles.dropzoneIcon} />
              {file ? (
                <div>
                  <p className={styles.dropzoneFileName}>{file.name}</p>
                  <p className={styles.dropzoneFileSize}>
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </div>
              ) : (
                <div>
                  <p className={styles.dropzoneTitle}>
                    {t('import.file.dropTitle' as any)}
                  </p>
                  <p className={styles.dropzoneDescription}>
                    {t('import.file.dropHint' as any)}
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Format example */}
          <div>
            <label className="text-sm font-medium mb-2 block">{t('import.example.label' as any)}</label>
            <pre className="bg-muted p-3 rounded-lg text-xs overflow-x-auto">
              {formatExamples[selectedFormat]}
            </pre>
          </div>

          {/* Info alert */}
          <div className={`${styles.alert} ${styles.alertInfo}`}>
            <div className={styles.alertContent}>
              <AlertCircle className={`${styles.alertIcon} ${styles.alertIconInfo}`} />
              <div className={styles.alertBody}>
                <p className={`${styles.alertTitle} ${styles.alertTitleInfo}`}>
                  {t('import.info.title' as any)}
                </p>
                <ul className={styles.alertList}>
                  <li className={styles.alertListItemInfo}>
                    {duplicateStrategy === 'skip'
                      ? t('import.info.duplicates' as any)
                      : t('import.info.duplicatesReplace' as any)}
                  </li>
                  <li className={styles.alertListItemInfo}>
                    {t('import.info.types' as any)}
                  </li>
                  <li className={styles.alertListItemInfo}>
                    {t('import.info.direction' as any)}
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className={styles.modalFooter}>
          <div className={styles.modalFooterLeft}>
            {file
              ? t('import.footer.ready', { filename: file.name } as any)
              : t('import.footer.empty' as any)}
          </div>
          <div className={styles.modalFooterRight}>
            <button
              onClick={handleClose}
              className={styles.toolbarButton}
              disabled={isUploading}
            >
              {t('common:actions.cancel')}
            </button>
            <button
              onClick={handleImport}
              disabled={!file || isUploading}
              className={styles.toolbarButtonPrimary}
            >
              {isUploading ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                  {t('import.importing' as any)}
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  {t('import.submit' as any)}
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
