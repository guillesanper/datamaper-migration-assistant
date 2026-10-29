// src/components/mapping/modals/DatabaseConnectionModal.tsx
import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X, Database, CheckCircle, AlertCircle, Loader2, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { dbConnectionService } from '../../../services/db_connection.service';
import { toast } from '../../../utils/toast';
import { confirmsHostname, isPlausibleCaPem, isValidHostFormat } from '../../../utils/tls';
import { TlsUnverifiedBadge } from '../TlsUnverifiedBadge';
import { TlsSkipConfirmModal } from './TlsSkipConfirmModal';
import type {
  DBConnectionConfig,
  DBDialect,
  DBConnectionTestResult,
  ValidationErrors,
} from '../../../types/db_connection_types';
import { DEFAULT_PORTS, DIALECT_NAMES } from '../../../types/db_connection_types';
import styles from '../../../styles/mapping/mapping-modals.module.css';

interface DatabaseConnectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  onSuccess: (
    sessionId: string,
    tableType: 'origin' | 'destination',
    tlsVerified: boolean
  ) => void;
  targetType?: 'origin' | 'destination';
}

// Prefijo del mensaje del backend cuando falla la verificación TLS (lo fija un test del backend)
const TLS_FAILURE_PREFIX = 'TLS verification failed';

export const DatabaseConnectionModal: React.FC<DatabaseConnectionModalProps> = ({
  isOpen,
  onClose,
  projectId,
  onSuccess,
  targetType,
}) => {
  const { t } = useTranslation('mapping');

  const [activeTab, setActiveTab] = useState<'origin' | 'destination'>('origin');
  const [selectedDialect, setSelectedDialect] = useState<DBDialect | null>(null);
  const [config, setConfig] = useState<Partial<DBConnectionConfig>>({
    timeout: 30,
  });
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [testResult, setTestResult] = useState<DBConnectionTestResult | null>(null);
  const [validationErrors, setValidationErrors] = useState<ValidationErrors>({});
  const [isSkipConfirmOpen, setIsSkipConfirmOpen] = useState(false);
  const [caFileName, setCaFileName] = useState<string | null>(null);
  const caFileInput = useRef<HTMLInputElement>(null);

  const skipVerification = config.tls_verify === false;

  const clearCa = () => {
    setConfig(prev => ({ ...prev, tls_ca_pem: undefined }));
    setCaFileName(null);
    if (caFileInput.current) caFileInput.current.value = '';
    setValidationErrors(prev => ({ ...prev, tls_ca_pem: undefined }));
  };

  useEffect(() => {
    if (isOpen) {
      setSelectedDialect(null);
      setConfig({ timeout: 30 });
      setTestResult(null);
      setValidationErrors({});
      setActiveTab(targetType ?? 'origin');
      setIsSkipConfirmOpen(false);
      setCaFileName(null);
    }
  }, [isOpen, targetType]);

  useEffect(() => {
    if (selectedDialect) {
      setConfig(prev => ({
        ...prev,
        dialect: selectedDialect,
        port: DEFAULT_PORTS[selectedDialect],
        // SQL Server no admite una CA propia por conexión (usa el almacén del sistema)
        tls_ca_pem: selectedDialect === 'sqlserver' ? undefined : prev.tls_ca_pem,
      }));
      if (selectedDialect === 'sqlserver') setCaFileName(null);
    }
  }, [selectedDialect]);

  // Cambiar el host invalida la confirmación: se confirmó el host anterior
  const handleHostChange = (host: string) => {
    setConfig(prev => {
      const stillConfirmed =
        prev.tls_verify === false && confirmsHostname(prev.confirm_hostname ?? '', host);
      return prev.tls_verify === false && !stillConfirmed
        ? { ...prev, host, tls_verify: undefined, confirm_hostname: undefined }
        : { ...prev, host };
    });
  };

  const handleCaFile = async (file: File | undefined) => {
    if (!file) return;
    const text = await file.text();
    if (!isPlausibleCaPem(text)) {
      clearCa();
      setValidationErrors(prev => ({ ...prev, tls_ca_pem: t('db.tls.caInvalid') }));
      return;
    }
    setConfig(prev => ({ ...prev, tls_ca_pem: text }));
    setCaFileName(file.name);
    setValidationErrors(prev => ({ ...prev, tls_ca_pem: undefined }));
  };

  const requestSkipVerification = () => {
    if (!config.host?.trim()) {
      setValidationErrors(prev => ({ ...prev, host: t('db.validation.hostRequired') }));
      return;
    }
    setIsSkipConfirmOpen(true);
  };

  const confirmSkipVerification = (typedHostname: string) => {
    // Una CA propia no tiene sentido sin verificar: el backend las rechaza juntas
    setConfig(prev => ({
      ...prev,
      tls_verify: false,
      confirm_hostname: typedHostname,
      tls_ca_pem: undefined,
    }));
    setCaFileName(null);
    setIsSkipConfirmOpen(false);
  };

  const restoreVerification = () => {
    setConfig(prev => ({ ...prev, tls_verify: undefined, confirm_hostname: undefined }));
  };

  // Config que se envía al backend. El cifrado TLS es siempre obligatorio: aquí solo se decide
  // si se verifica el certificado, y desactivarlo va con la confirmación del hostname.
  const buildConfig = (dialect: DBDialect): DBConnectionConfig => ({
    dialect,
    host: config.host!.trim(),
    port: config.port!,
    database: config.database!,
    user: config.user!,
    password: config.password!,
    timeout: config.timeout,
    service_name: config.service_name,
    sid: config.sid,
    tls_verify: !skipVerification,
    ...(skipVerification
      ? { confirm_hostname: config.confirm_hostname }
      : config.tls_ca_pem && dialect !== 'sqlserver'
        ? { tls_ca_pem: config.tls_ca_pem }
        : {}),
  });

  const handleClose = () => {
    if (!isTestingConnection && !isConnecting) {
      onClose();
    }
  };

  const validateForm = (): boolean => {
    const errors: ValidationErrors = {};

    if (!config.host?.trim()) {
      errors.host = t('db.validation.hostRequired');
    } else if (config.host.length > 255) {
      errors.host = t('db.validation.hostMax');
    } else if (!isValidHostFormat(config.host)) {
      errors.host = t('db.validation.hostFormat');
    }

    if (!config.port) {
      errors.port = t('db.validation.portRequired');
    } else if (config.port < 1 || config.port > 65535) {
      errors.port = t('db.validation.portRange');
    }

    if (!config.database?.trim()) {
      errors.database = t('db.validation.dbRequired');
    } else if (config.database.length > 128) {
      errors.database = t('db.validation.dbMax');
    }

    if (!config.user?.trim()) {
      errors.user = t('db.validation.userRequired');
    } else if (config.user.length > 128) {
      errors.user = t('db.validation.userMax');
    }

    if (!config.password) {
      errors.password = t('db.validation.passRequired');
    }

    if (selectedDialect === 'oracle') {
      if (!config.service_name?.trim() && !config.sid?.trim()) {
        errors.service_name = t('db.validation.oracleRequired');
        errors.sid = t('db.validation.oracleRequired');
      }
    }

    if (config.timeout !== undefined) {
      if (config.timeout < 5 || config.timeout > 600) {
        errors.timeout = t('db.validation.timeoutRange');
      }
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleTestConnection = async () => {
    if (!selectedDialect) {
      toast.error(t('db.validation.noDialect'));
      return;
    }

    if (!validateForm()) {
      toast.error(t('db.validation.formErrors'));
      return;
    }

    setIsTestingConnection(true);
    setTestResult(null);

    try {
      const fullConfig = buildConfig(selectedDialect);

      const result = await dbConnectionService.testConnection(fullConfig);
      setTestResult(result);

      if (result.success) {
        toast.success(t('db.toast.testSuccess'));
      } else if (result.error_type === 'tls') {
        toast.error(t('db.tls.verificationFailed'));
      } else {
        toast.error(result.error_message || t('db.toast.testError'));
      }
    } catch (error: unknown) {
      console.error('Error testing connection:', error);
      setTestResult({
        success: false,
        dialect: selectedDialect,
        host: config.host!,
        database: config.database!,
        error_message: error instanceof Error ? error.message : t('db.toast.unknownError'),
        error_type: 'unknown_error',
        tls_verified: !skipVerification,
      });
      toast.error(t('db.toast.testError'));
    } finally {
      setIsTestingConnection(false);
    }
  };

  const handleConnect = async () => {
    if (!selectedDialect) {
      toast.error(t('db.validation.noDialect'));
      return;
    }

    if (!validateForm()) {
      toast.error(t('db.validation.formErrors'));
      return;
    }

    setIsConnecting(true);

    try {
      const fullConfig = buildConfig(selectedDialect);

      const session = await dbConnectionService.createSession(fullConfig, true, 3, projectId);

      toast.success(t('db.toast.connected', { name: DIALECT_NAMES[selectedDialect] }));

      onSuccess(session.session_id, activeTab, session.tls_verified);

      handleClose();
    } catch (error: unknown) {
      console.error('Error connecting:', error);
      const errObj = error as Record<string, unknown>;
      const responseDetail = (errObj.response as Record<string, unknown> | undefined)?.data as Record<string, unknown> | undefined;
      // apiService lanza { message } (el detail del backend); sin él no se distingue el fallo TLS
      const apiMessage = String((errObj as { message?: unknown }).message ?? '');
      toast.error(
        apiMessage.includes(TLS_FAILURE_PREFIX)
          ? t('db.tls.verificationFailed')
          : String(responseDetail?.detail ?? '') ||
            (error instanceof Error ? error.message : '') ||
            t('db.toast.connectError')
      );
    } finally {
      setIsConnecting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className={styles.modalOverlay} onClick={(e) => {
      if (e.target === e.currentTarget) handleClose();
    }}>
      <div className={styles.modalContent} style={{ maxWidth: '56rem' }}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>{t('db.title')}</h2>
          <button
            onClick={handleClose}
            className={styles.modalCloseButton}
            disabled={isTestingConnection || isConnecting}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs o badge de tipo bloqueado */}
        {targetType ? (
          <div className="border-b border-border px-6 py-3 flex items-center gap-2">
            <span className="text-sm text-muted-foreground">{t('db.typeLabel')}</span>
            <span
              className={`px-3 py-1 rounded-full text-xs font-semibold ${
                targetType === 'origin'
                  ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border border-blue-500/30'
                  : 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
              }`}
            >
              {targetType === 'origin' ? t('db.tabOrigin') : t('db.tabDest')}
            </span>
          </div>
        ) : (
          <div className="border-b border-border px-6">
            <div className="flex gap-2">
              <button
                onClick={() => setActiveTab('origin')}
                className={`px-4 py-3 font-medium transition-colors ${
                  activeTab === 'origin'
                    ? 'border-b-2 border-primary text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                disabled={isTestingConnection || isConnecting}
              >
                {t('db.tabOrigin')}
              </button>
              <button
                onClick={() => setActiveTab('destination')}
                className={`px-4 py-3 font-medium transition-colors ${
                  activeTab === 'destination'
                    ? 'border-b-2 border-primary text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
                disabled={isTestingConnection || isConnecting}
              >
                {t('db.tabDest')}
              </button>
            </div>
          </div>
        )}

        {/* Body */}
        <div className={styles.modalBody}>
          {/* Selector de Dialecto */}
          <div className="flex flex-col gap-2">
            <label className="text-sm font-semibold">{t('db.dialectLabel')}</label>
            <div className="grid grid-cols-2 gap-3">
              {(['postgresql', 'mysql', 'sqlserver', 'oracle'] as DBDialect[]).map(dialect => (
                <button
                  key={dialect}
                  onClick={() => setSelectedDialect(dialect)}
                  disabled={isTestingConnection || isConnecting}
                  className={`flex items-center gap-3 px-4 py-3 border-2 rounded-lg transition-all ${
                    selectedDialect === dialect
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border hover:border-primary/50 hover:bg-muted'
                  } ${(isTestingConnection || isConnecting) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  <Database className="w-5 h-5" />
                  <span className="font-medium">{DIALECT_NAMES[dialect]}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Formulario de Credenciales */}
          {selectedDialect && (
            <>
              <div className="grid grid-cols-2 gap-4">
                {/* Host */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium">{t('db.host.label')} *</label>
                  <input
                    type="text"
                    value={config.host || ''}
                    onChange={(e) => handleHostChange(e.target.value)}
                    placeholder={t('db.host.placeholder')}
                    disabled={isTestingConnection || isConnecting}
                    className={`px-3 py-2 border rounded-md bg-background ${
                      validationErrors.host ? 'border-red-500' : 'border-border'
                    }`}
                  />
                  {validationErrors.host && (
                    <span className="text-xs text-red-500">{validationErrors.host}</span>
                  )}
                </div>

                {/* Port */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium">{t('db.port.label')} *</label>
                  <input
                    type="number"
                    value={config.port || ''}
                    onChange={(e) => setConfig({ ...config, port: parseInt(e.target.value) || undefined })}
                    placeholder={DEFAULT_PORTS[selectedDialect].toString()}
                    disabled={isTestingConnection || isConnecting}
                    className={`px-3 py-2 border rounded-md bg-background ${
                      validationErrors.port ? 'border-red-500' : 'border-border'
                    }`}
                  />
                  {validationErrors.port && (
                    <span className="text-xs text-red-500">{validationErrors.port}</span>
                  )}
                </div>
              </div>

              {/* Database */}
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium">{t('db.db.label')} *</label>
                <input
                  type="text"
                  value={config.database || ''}
                  onChange={(e) => setConfig({ ...config, database: e.target.value })}
                  placeholder={t('db.db.placeholder')}
                  disabled={isTestingConnection || isConnecting}
                  className={`px-3 py-2 border rounded-md bg-background ${
                    validationErrors.database ? 'border-red-500' : 'border-border'
                  }`}
                />
                {validationErrors.database && (
                  <span className="text-xs text-red-500">{validationErrors.database}</span>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                {/* User */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium">{t('db.user.label')} *</label>
                  <input
                    type="text"
                    value={config.user || ''}
                    onChange={(e) => setConfig({ ...config, user: e.target.value })}
                    placeholder={t('db.user.placeholder')}
                    disabled={isTestingConnection || isConnecting}
                    className={`px-3 py-2 border rounded-md bg-background ${
                      validationErrors.user ? 'border-red-500' : 'border-border'
                    }`}
                  />
                  {validationErrors.user && (
                    <span className="text-xs text-red-500">{validationErrors.user}</span>
                  )}
                </div>

                {/* Password */}
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium">{t('db.pass.label')} *</label>
                  <input
                    type="password"
                    value={config.password || ''}
                    onChange={(e) => setConfig({ ...config, password: e.target.value })}
                    placeholder="••••••••"
                    disabled={isTestingConnection || isConnecting}
                    className={`px-3 py-2 border rounded-md bg-background ${
                      validationErrors.password ? 'border-red-500' : 'border-border'
                    }`}
                  />
                  {validationErrors.password && (
                    <span className="text-xs text-red-500">{validationErrors.password}</span>
                  )}
                </div>
              </div>

              {/* Oracle específico */}
              {selectedDialect === 'oracle' && (
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-sm font-medium">{t('db.oracle.serviceName')}</label>
                    <input
                      type="text"
                      value={config.service_name || ''}
                      onChange={(e) => setConfig({ ...config, service_name: e.target.value })}
                      placeholder="ORCL"
                      disabled={isTestingConnection || isConnecting}
                      className={`px-3 py-2 border rounded-md bg-background ${
                        validationErrors.service_name ? 'border-red-500' : 'border-border'
                      }`}
                    />
                    {validationErrors.service_name && (
                      <span className="text-xs text-red-500">{validationErrors.service_name}</span>
                    )}
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-sm font-medium">{t('db.oracle.sid')}</label>
                    <input
                      type="text"
                      value={config.sid || ''}
                      onChange={(e) => setConfig({ ...config, sid: e.target.value })}
                      placeholder="ORCL"
                      disabled={isTestingConnection || isConnecting}
                      className={`px-3 py-2 border rounded-md bg-background ${
                        validationErrors.sid ? 'border-red-500' : 'border-border'
                      }`}
                    />
                    {validationErrors.sid && (
                      <span className="text-xs text-red-500">{validationErrors.sid}</span>
                    )}
                  </div>
                </div>
              )}

              {/* Timeout */}
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium">{t('db.timeout.label')}</label>
                <input
                  type="number"
                  value={config.timeout || 30}
                  onChange={(e) => setConfig({ ...config, timeout: parseInt(e.target.value) || 30 })}
                  placeholder="30"
                  disabled={isTestingConnection || isConnecting}
                  className={`px-3 py-2 border rounded-md bg-background ${
                    validationErrors.timeout ? 'border-red-500' : 'border-border'
                  }`}
                />
                {validationErrors.timeout && (
                  <span className="text-xs text-red-500">{validationErrors.timeout}</span>
                )}
              </div>

              {/* Seguridad TLS: el cifrado es obligatorio; aquí solo se elige cómo verificar */}
              <fieldset
                className="flex flex-col gap-3 p-4 border border-border rounded-lg"
                disabled={isTestingConnection || isConnecting}
              >
                <legend className="px-2 text-sm font-semibold flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4" aria-hidden="true" />
                  {t('db.tls.sectionTitle')}
                </legend>
                <p className="text-xs text-muted-foreground">{t('db.tls.encryptedNote')}</p>

                {selectedDialect === 'sqlserver' ? (
                  <p className="text-xs text-muted-foreground">{t('db.tls.caSqlServer')}</p>
                ) : (
                  <div className="flex flex-col gap-1.5">
                    <label className="text-sm font-medium">{t('db.tls.caFileLabel')}</label>
                    <div className="flex items-center gap-2">
                      <input
                        ref={caFileInput}
                        type="file"
                        accept=".pem,.crt,.cer"
                        onChange={(e) => handleCaFile(e.target.files?.[0])}
                        disabled={skipVerification}
                        className="text-sm file:mr-3 file:px-3 file:py-1.5 file:border file:border-border file:rounded-md file:bg-background file:text-sm disabled:opacity-50"
                      />
                      {caFileName && (
                        <>
                          <span className="text-xs text-muted-foreground">
                            {t('db.tls.caLoaded', { name: caFileName })}
                          </span>
                          <button
                            type="button"
                            onClick={clearCa}
                            className="text-xs underline text-muted-foreground hover:text-foreground"
                          >
                            {t('db.tls.caClear')}
                          </button>
                        </>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground">{t('db.tls.caHelp')}</span>
                    {validationErrors.tls_ca_pem && (
                      <span className="text-xs text-red-500">{validationErrors.tls_ca_pem}</span>
                    )}
                  </div>
                )}

                {selectedDialect === 'oracle' && !skipVerification && (
                  <p className="text-xs text-muted-foreground">{t('db.tls.oracleHostHint')}</p>
                )}

                {skipVerification ? (
                  <div className="flex items-center justify-between gap-3 p-3 rounded-md bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-800">
                    <div className="flex items-center gap-2 flex-wrap">
                      <TlsUnverifiedBadge />
                      <span className="text-xs text-amber-900 dark:text-amber-200">
                        {t('db.tls.skipActive', { host: config.host })}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={restoreVerification}
                      className="text-xs underline text-amber-900 dark:text-amber-200 hover:no-underline"
                    >
                      {t('db.tls.skipUndo')}
                    </button>
                  </div>
                ) : (
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={false}
                      onChange={requestSkipVerification}
                      className="h-4 w-4"
                    />
                    <span>{t('db.tls.skipLabel')}</span>
                  </label>
                )}
              </fieldset>

              {/* Resultado de Test */}
              {testResult && (
                <div
                  className={`flex items-start gap-3 p-4 rounded-lg border ${
                    testResult.success
                      ? 'bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800'
                      : 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800'
                  }`}
                >
                  {testResult.success ? (
                    <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1">
                    <p
                      className={`text-sm font-medium ${
                        testResult.success ? 'text-green-800 dark:text-green-200' : 'text-red-800 dark:text-red-200'
                      }`}
                    >
                      {testResult.success ? t('db.test.success') : t('db.test.error')}
                    </p>
                    {testResult.error_message && (
                      <p className="text-sm text-red-700 dark:text-red-300 mt-1">
                        {testResult.error_type === 'tls'
                          ? t('db.tls.verificationFailed')
                          : testResult.error_message}
                      </p>
                    )}
                    {testResult.success && !testResult.tls_verified && (
                      <div className="mt-2">
                        <TlsUnverifiedBadge />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className={styles.modalFooter}>
          <div className={styles.modalFooterLeft}>
            {selectedDialect && (
              <span className="text-xs text-muted-foreground">
                {t('db.footer.connecting', {
                  dialect: DIALECT_NAMES[selectedDialect],
                  type: activeTab === 'origin' ? t('db.tabOrigin') : t('db.tabDest'),
                })}
              </span>
            )}
          </div>
          <div className={styles.modalFooterRight}>
            <button
              onClick={handleClose}
              disabled={isTestingConnection || isConnecting}
              className="px-4 py-2 border border-border rounded-md hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('db.actions.cancel')}
            </button>
            <button
              onClick={handleTestConnection}
              disabled={!selectedDialect || isTestingConnection || isConnecting}
              className="px-4 py-2 border border-border rounded-md hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isTestingConnection && <Loader2 className="w-4 h-4 animate-spin" />}
              {t('db.actions.test')}
            </button>
            <button
              onClick={handleConnect}
              disabled={!selectedDialect || isTestingConnection || isConnecting}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isConnecting && <Loader2 className="w-4 h-4 animate-spin" />}
              {t('db.actions.connect')}
            </button>
          </div>
        </div>

        {/* Portal: queda por encima y sus clics no cierran este modal */}
        {createPortal(
          <TlsSkipConfirmModal
            isOpen={isSkipConfirmOpen}
            host={config.host ?? ''}
            onConfirm={confirmSkipVerification}
            onCancel={() => setIsSkipConfirmOpen(false)}
          />,
          document.body
        )}
      </div>
    </div>
  );
};
