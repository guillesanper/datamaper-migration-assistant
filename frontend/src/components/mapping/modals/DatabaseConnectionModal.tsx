// src/components/mapping/modals/DatabaseConnectionModal.tsx
import React, { useState, useEffect } from 'react';
import { X, Database, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { dbConnectionService } from '../../../services/db_connection.service';
import { toast } from '../../../utils/toast';
import type {
  DBConnectionConfig,
  DBDialect,
  DBSSLMode,
  DBConnectionTestResult,
  ValidationErrors,
} from '../../../types/db_connection_types';
import { DEFAULT_PORTS, DIALECT_NAMES } from '../../../types/db_connection_types';
import styles from '../../../styles/mapping/mapping-modals.module.css';

interface DatabaseConnectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  onSuccess: (sessionId: string, tableType: 'origin' | 'destination') => void;
  targetType?: 'origin' | 'destination';
}

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
    ssl_mode: 'verify',
  });
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [testResult, setTestResult] = useState<DBConnectionTestResult | null>(null);
  const [validationErrors, setValidationErrors] = useState<ValidationErrors>({});

  useEffect(() => {
    if (isOpen) {
      setSelectedDialect(null);
      setConfig({ timeout: 30, ssl_mode: 'verify' });
      setTestResult(null);
      setValidationErrors({});
      setActiveTab(targetType ?? 'origin');
    }
  }, [isOpen, targetType]);

  useEffect(() => {
    if (selectedDialect) {
      setConfig(prev => ({
        ...prev,
        dialect: selectedDialect,
        port: DEFAULT_PORTS[selectedDialect],
      }));
    }
  }, [selectedDialect]);

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
      const fullConfig: DBConnectionConfig = {
        dialect: selectedDialect,
        host: config.host!,
        port: config.port!,
        database: config.database!,
        user: config.user!,
        password: config.password!,
        timeout: config.timeout,
        ssl_mode: config.ssl_mode,
        service_name: config.service_name,
        sid: config.sid,
      };

      const result = await dbConnectionService.testConnection(fullConfig);
      setTestResult(result);

      if (result.success) {
        toast.success(t('db.toast.testSuccess'));
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
      const fullConfig: DBConnectionConfig = {
        dialect: selectedDialect,
        host: config.host!,
        port: config.port!,
        database: config.database!,
        user: config.user!,
        password: config.password!,
        timeout: config.timeout,
        ssl_mode: config.ssl_mode,
        service_name: config.service_name,
        sid: config.sid,
      };

      const session = await dbConnectionService.createSession(fullConfig, true, 3, projectId);

      toast.success(t('db.toast.connected', { name: DIALECT_NAMES[selectedDialect] }));

      onSuccess(session.session_id, activeTab);

      handleClose();
    } catch (error: unknown) {
      console.error('Error connecting:', error);
      const errObj = error as Record<string, unknown>;
      const responseDetail = (errObj.response as Record<string, unknown> | undefined)?.data as Record<string, unknown> | undefined;
      toast.error(
        String(responseDetail?.detail ?? '') ||
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
                    onChange={(e) => setConfig({ ...config, host: e.target.value })}
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

              {/* TLS */}
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium">{t('db.ssl.label')}</label>
                <select
                  value={config.ssl_mode || 'verify'}
                  onChange={(e) => setConfig({ ...config, ssl_mode: e.target.value as DBSSLMode })}
                  disabled={isTestingConnection || isConnecting}
                  className="px-3 py-2 border rounded-md bg-background border-border"
                >
                  <option value="verify">{t('db.ssl.verify')}</option>
                  <option value="require">{t('db.ssl.require')}</option>
                  <option value="disable">{t('db.ssl.disable')}</option>
                </select>
                {config.ssl_mode && config.ssl_mode !== 'verify' && (
                  <span className="text-xs text-amber-600">{t('db.ssl.warning')}</span>
                )}
              </div>

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
                        {testResult.error_message}
                      </p>
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
      </div>
    </div>
  );
};
