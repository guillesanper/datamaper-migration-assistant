import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ChevronLeft, HelpCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { type TFunction } from 'i18next';
import {
  X,
  Play,
  ChevronRight,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Database,
} from '../icons';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import {
  migrationService,
  type GenerateScriptOptions,
  type GeneratedScript,
  type ExecutionStatus,
} from '../../services/migration_service';
import { toast } from '../../utils/toast';
import styles from '../../styles/mapping/mapping.module.css';
import { MigrationGuideModal } from './MigrationGuideModal';
import { TlsUnverifiedBadge } from './TlsUnverifiedBadge';

interface MigrationModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  destConnectionSessionId: string | null;
  /** true si la conexión de destino se creó sin verificar el certificado del servidor */
  destConnectionUnverified?: boolean;
  destinationDb?: string;
}

type Step = 'config' | 'preview' | 'running' | 'result';

function inferDialect(db?: string): GenerateScriptOptions['dialect'] | null {
  const lower = db?.toLowerCase() ?? '';
  if (lower.includes('postgres')) return 'postgresql';
  if (lower.includes('mysql') || lower.includes('mariadb')) return 'mysql';
  if (lower.includes('sql server') || lower.includes('sqlserver') || lower.includes('mssql')) return 'sqlserver';
  if (lower.includes('oracle')) return 'oracle';
  return null;
}

const TERMINAL_STATUSES = new Set([
  'success',
  'failed',
  'rolled_back',
  'dry_run_complete',
]);

function extractErrorMessage(err: unknown, t: TFunction<['mapping']>): string {
  const e = err as Record<string, unknown>;
  const data = (e.response as Record<string, unknown> | undefined)?.data as Record<string, unknown> | undefined;
  if (data?.detail) return String(data.detail);
  if (e.detail) return String(e.detail);
  if (err instanceof Error) return err.message;
  return t('migration.toast.unknownError');
}

export const MigrationModal: React.FC<MigrationModalProps> = ({
  isOpen,
  onClose,
  projectId,
  destConnectionSessionId,
  destConnectionUnverified = false,
  destinationDb,
}) => {
  const { t } = useTranslation('mapping');
  const scriptOnly = !destConnectionSessionId;

  const [step, setStep] = useState<Step>('config');

  const [dialect, setDialect] = useState<GenerateScriptOptions['dialect']>(() => inferDialect(destinationDb) ?? 'postgresql');
  const [batchSize, setBatchSize] = useState(10000);
  const [includeConstraints, setIncludeConstraints] = useState(true);
  const [includeValidation, setIncludeValidation] = useState(true);
  const [dryRun, setDryRun] = useState(false);

  const [generatedScript, setGeneratedScript] = useState<GeneratedScript | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  const [executionStatus, setExecutionStatus] = useState<ExecutionStatus | null>(null);
  const [isStarting, setIsStarting] = useState(false);

  const [logExpanded, setLogExpanded] = useState(false);

  const [showGuideModal, setShowGuideModal] = useState(false);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const statusLabels: Record<string, string> = {
    success: t('migration.statusLabels.completed'),
    dry_run_complete: t('migration.statusLabels.dryRunOk'),
    failed: t('migration.statusLabels.failed'),
    rolled_back: t('migration.statusLabels.rolledBack'),
    running: t('migration.statusLabels.running'),
    pending: t('migration.statusLabels.pending'),
  };

  useEffect(() => {
    if (!isOpen) {
      resetState();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showGuideModal) {
          setShowGuideModal(false);
        } else {
          onClose();
        }
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, showGuideModal]);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  const resetState = () => {
    stopPolling();
    setStep('config');
    setDialect(inferDialect(destinationDb) ?? 'postgresql');
    setBatchSize(10000);
    setIncludeConstraints(true);
    setIncludeValidation(true);
    setDryRun(false);
    setGeneratedScript(null);
    setIsGenerating(false);
    setExecutionStatus(null);
    setIsStarting(false);
    setLogExpanded(false);
  };

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const script = await migrationService.generateScript(projectId, {
        dialect,
        batch_size: batchSize,
        include_constraints: includeConstraints,
        include_validation: includeValidation,
      });
      setGeneratedScript(script);
      setStep('preview');
    } catch (err: unknown) {
      const msg = extractErrorMessage(err, t);
      toast.error(t('migration.toast.scriptError', { error: msg }));
    } finally {
      setIsGenerating(false);
    }
  };

  const handleExecute = async () => {
    if (!generatedScript || !destConnectionSessionId) return;
    setIsStarting(true);
    try {
      const started = await migrationService.executeScript(projectId, {
        script_id: generatedScript.script_id,
        dry_run: dryRun,
        dest_connection_session_id: destConnectionSessionId,
      });
      setStep('running');
      startPolling(started.execution_id);
    } catch (err: unknown) {
      const msg = extractErrorMessage(err, t);
      toast.error(t('migration.toast.runError', { error: msg }));
    } finally {
      setIsStarting(false);
    }
  };

  const startPolling = (execId: string) => {
    stopPolling();
    pollingRef.current = setInterval(async () => {
      try {
        const status = await migrationService.getExecutionStatus(projectId, execId);
        setExecutionStatus(status);
        if (TERMINAL_STATUSES.has(status.status)) {
          stopPolling();
          setStep('result');
        }
      } catch {
        // silently ignore poll errors
      }
    }, 2000);
  };

  const formatDuration = (seconds: number | null) => {
    if (seconds === null) return '—';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  };

  if (!isOpen) return null;

  const steps: { key: Step; label: string }[] = scriptOnly
    ? [
        { key: 'config', label: t('migration.steps.config') },
        { key: 'preview', label: t('migration.steps.scriptGenerated') },
      ]
    : [
        { key: 'config', label: t('migration.steps.config') },
        { key: 'preview', label: t('migration.steps.preview') },
        { key: 'running', label: t('migration.steps.execution') },
        { key: 'result', label: t('migration.steps.result') },
      ];
  const currentIndex = steps.findIndex((s) => s.key === step);

  const chips = [
    { label: t('migration.chips.dialect', { dialect }) },
    { label: t('migration.chips.batch', { size: batchSize.toLocaleString() }) },
    ...(includeConstraints ? [{ label: t('migration.chips.constraints') }] : []),
    ...(includeValidation ? [{ label: t('migration.chips.validation') }] : []),
    ...(dryRun ? [{ label: t('migration.chips.dryRun'), highlight: true }] : []),
  ];

  const logCols = [
    t('migration.log.col.n'),
    t('migration.log.col.type'),
    t('migration.log.col.table'),
    t('migration.log.col.rows'),
    t('migration.log.col.duration'),
    t('migration.log.col.status'),
  ];

  return (
    <>
    <div className={styles.modalOverlay}>
      <div className={styles.modalContent} style={{ maxWidth: '72rem' }}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Database className="w-5 h-5" style={{ color: 'hsl(var(--primary))' }} />
            <h2 className={styles.modalTitle}>{t('migration.title')}</h2>
          </div>
          <button onClick={onClose} className={styles.modalCloseButton} aria-label={t('migration.aria.close')}>
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Step indicator */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '0.75rem 2rem',
            borderBottom: '1px solid var(--color-border)',
            gap: '0',
            background: 'hsl(var(--muted) / 0.2)',
          }}
        >
          {steps.map((s, idx) => (
            <React.Fragment key={s.key}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div
                  style={{
                    width: '1.5rem',
                    height: '1.5rem',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    background:
                      idx < currentIndex
                        ? 'hsl(var(--primary))'
                        : idx === currentIndex
                        ? 'hsl(var(--primary))'
                        : 'hsl(var(--muted))',
                    color:
                      idx <= currentIndex
                        ? 'hsl(var(--primary-foreground))'
                        : 'hsl(var(--muted-foreground))',
                    flexShrink: 0,
                  }}
                >
                  {idx < currentIndex ? '✓' : idx + 1}
                </div>
                <span
                  style={{
                    fontSize: '0.8125rem',
                    fontWeight: idx === currentIndex ? 600 : 400,
                    color:
                      idx === currentIndex
                        ? 'hsl(var(--foreground))'
                        : 'hsl(var(--muted-foreground))',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {s.label}
                </span>
              </div>
              {idx < steps.length - 1 && (
                <div
                  style={{
                    flex: 1,
                    height: '1px',
                    margin: '0 0.5rem',
                    background:
                      idx < currentIndex
                        ? 'hsl(var(--primary))'
                        : 'hsl(var(--border))',
                  }}
                />
              )}
            </React.Fragment>
          ))}
        </div>

        {/* Body */}
        <div className={styles.modalBody}>
          {/* ── STEP 1: CONFIG ─────────────────────────────────────────── */}
          {step === 'config' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {scriptOnly ? (
                <div className={`${styles.alert} ${styles.alertInfo}`} style={{ background: 'hsl(221 83% 96%)', borderColor: 'hsl(221 83% 82%)' }}>
                  <div className={styles.alertContent}>
                    <AlertTriangle className={`${styles.alertIcon}`} style={{ color: 'hsl(221 83% 53%)' }} />
                    <div className={styles.alertBody}>
                      <p style={{ fontSize: '0.875rem', fontWeight: 500, color: 'hsl(221 83% 30%)' }}>
                        {t('migration.alert.scriptOnly')}
                      </p>
                      <p style={{ fontSize: '0.8125rem', marginTop: '0.125rem', color: 'hsl(221 83% 40%)' }}>
                        {t('migration.alert.scriptOnlyDesc')}
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className={`${styles.alert} ${styles.alertInfo}`} style={{ background: 'hsl(var(--muted) / 0.4)', border: '1px solid hsl(var(--border))' }}>
                  <div className={styles.alertContent}>
                    <Database className={`${styles.alertIcon}`} style={{ color: 'hsl(var(--primary))' }} />
                    <div className={styles.alertBody}>
                      <p style={{ fontSize: '0.875rem', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                        {t('migration.alert.sessionActive')}
                        {destConnectionUnverified && <TlsUnverifiedBadge />}
                      </p>
                      <p style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', marginTop: '0.125rem', fontFamily: 'monospace' }}>
                        {destConnectionSessionId}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {destinationDb && !inferDialect(destinationDb) && (
                <div className={`${styles.alert} ${styles.alertWarning}`}>
                  <div className={styles.alertContent}>
                    <AlertTriangle className={`${styles.alertIcon} ${styles.alertIconWarning}`} />
                    <div className={styles.alertBody}>
                      <p className={`${styles.alertTitle} ${styles.alertTitleWarning}`}>
                        {t('migration.alert.dialectUnknown')}
                      </p>
                      <p style={{ fontSize: '0.8125rem', marginTop: '0.125rem' }}>
                        {t('migration.alert.dialectUnknownDesc', { name: destinationDb })}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <div>
                <label style={{ fontSize: '0.875rem', fontWeight: 500, display: 'block', marginBottom: '0.5rem' }}>
                  {t('migration.dialect.label')}
                </label>
                <Select
                  value={dialect}
                  onValueChange={(v) => setDialect(v as GenerateScriptOptions['dialect'])}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="postgresql">PostgreSQL</SelectItem>
                    <SelectItem value="mysql">MySQL</SelectItem>
                    <SelectItem value="sqlserver">SQL Server</SelectItem>
                    <SelectItem value="oracle">Oracle</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label style={{ fontSize: '0.875rem', fontWeight: 500, display: 'block', marginBottom: '0.5rem' }}>
                  {t('migration.batchSize.label')}
                </label>
                <input
                  type="number"
                  min={1}
                  max={1000000}
                  value={batchSize}
                  onChange={(e) => setBatchSize(Number(e.target.value))}
                  style={{
                    width: '100%',
                    padding: '0.5rem 0.75rem',
                    borderRadius: 'var(--mapping-border-radius, 0.5rem)',
                    border: '1px solid hsl(var(--border))',
                    background: 'hsl(var(--background))',
                    color: 'hsl(var(--foreground))',
                    fontSize: '0.875rem',
                  }}
                />
                <p style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', marginTop: '0.25rem' }}>
                  {t('migration.batchSize.hint')}
                </p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={includeConstraints}
                    onChange={(e) => setIncludeConstraints(e.target.checked)}
                    style={{ width: '1rem', height: '1rem', cursor: 'pointer' }}
                  />
                  <span style={{ fontSize: '0.875rem' }}>{t('migration.options.constraints')}</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={includeValidation}
                    onChange={(e) => setIncludeValidation(e.target.checked)}
                    style={{ width: '1rem', height: '1rem', cursor: 'pointer' }}
                  />
                  <span style={{ fontSize: '0.875rem' }}>{t('migration.options.validation')}</span>
                </label>
                {!scriptOnly && (
                  <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={dryRun}
                      onChange={(e) => setDryRun(e.target.checked)}
                      style={{ width: '1rem', height: '1rem', marginTop: '0.125rem', cursor: 'pointer' }}
                    />
                    <div>
                      <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>{t('migration.options.dryRun')}</span>
                      <p style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', marginTop: '0.125rem' }}>
                        {t('migration.options.dryRunHint')}
                      </p>
                    </div>
                  </label>
                )}
              </div>
            </div>
          )}

          {/* ── STEP 2: PREVIEW ────────────────────────────────────────── */}
          {step === 'preview' && generatedScript && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div className={styles.statsGrid}>
                <div className={styles.statsCard}>
                  <div className={styles.statsValue}>
                    {generatedScript.dependency_order.length || '—'}
                  </div>
                  <div className={styles.statsLabel}>{t('migration.stats.tablesLabel')}</div>
                </div>
                <div
                  className={styles.statsCard}
                  title={t('migration.script.rowsNote')}
                  style={{ cursor: 'help' }}
                >
                  <div className={styles.statsValue}>
                    {generatedScript.estimated_rows === 0 ? '—' : generatedScript.estimated_rows.toLocaleString()}
                  </div>
                  <div className={styles.statsLabel}>{t('migration.stats.estimatedRows')}</div>
                </div>
                <div className={styles.statsCard}>
                  <div className={styles.statsValue}>
                    {formatDuration(generatedScript.estimated_duration_seconds)}
                  </div>
                  <div className={styles.statsLabel}>{t('migration.stats.estimatedDuration')}</div>
                </div>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.375rem' }}>
                {chips.map((chip) => (
                  <span
                    key={chip.label}
                    style={{
                      fontSize: '0.75rem',
                      padding: '0.1875rem 0.625rem',
                      borderRadius: '9999px',
                      background: chip.highlight
                        ? 'hsl(38 92% 50% / 0.15)'
                        : 'hsl(var(--muted))',
                      color: chip.highlight
                        ? 'hsl(38 60% 35%)'
                        : 'hsl(var(--muted-foreground))',
                      fontFamily: 'monospace',
                      fontWeight: 500,
                    }}
                  >
                    {chip.label}
                  </span>
                ))}
              </div>

              {dryRun && (
                <div className={`${styles.alert} ${styles.alertWarning}`}>
                  <div className={styles.alertContent}>
                    <AlertTriangle className={`${styles.alertIcon} ${styles.alertIconWarning}`} />
                    <div className={styles.alertBody}>
                      <p className={`${styles.alertTitle} ${styles.alertTitleWarning}`}>
                        {t('migration.dryRunAlert')}
                      </p>
                      <p style={{ fontSize: '0.875rem', marginTop: '0.125rem' }}>
                        {t('migration.dryRunAlertDesc')}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                  <label style={{ fontSize: '0.875rem', fontWeight: 500 }}>
                    {t('migration.script.label')}
                  </label>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <button
                      onClick={() => setShowGuideModal(true)}
                      className={styles.toolbarButton}
                      style={{ fontSize: '0.8125rem', padding: '0.25rem 0.625rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}
                      title={t('migration.script.howTo')}
                    >
                      <HelpCircle style={{ width: '0.875rem', height: '0.875rem' }} />
                      {t('migration.script.howTo')}
                    </button>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(generatedScript.script);
                        toast.success(t('migration.toast.copied'));
                      }}
                      className={styles.toolbarButton}
                      style={{ fontSize: '0.8125rem', padding: '0.25rem 0.625rem' }}
                    >
                      {t('migration.script.copy')}
                    </button>
                    <button
                      onClick={() => {
                        const blob = new Blob([generatedScript.script], { type: 'text/plain' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `migration_${projectId}.sql`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                      className={styles.toolbarButton}
                      style={{ fontSize: '0.8125rem', padding: '0.25rem 0.625rem' }}
                    >
                      {t('migration.script.download')}
                    </button>
                  </div>
                </div>
                <textarea
                  readOnly
                  value={generatedScript.script}
                  style={{
                    width: '100%',
                    height: '28rem',
                    padding: '0.875rem 1rem',
                    borderRadius: 'var(--mapping-border-radius, 0.5rem)',
                    border: '1px solid hsl(var(--border))',
                    background: 'hsl(220 14% 11%)',
                    color: 'hsl(210 40% 88%)',
                    fontFamily: 'monospace',
                    fontSize: '0.875rem',
                    resize: 'vertical',
                    lineHeight: 1.6,
                    outline: 'none',
                    tabSize: 2,
                  }}
                />
                <p style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', marginTop: '0.375rem' }}>
                  {t('migration.script.rowsNote')}
                </p>
              </div>
            </div>
          )}

          {/* ── STEP 3: RUNNING ────────────────────────────────────────── */}
          {step === 'running' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', padding: '0.5rem 0' }}>
              <div style={{ textAlign: 'center' }}>
                <div
                  style={{
                    width: '3.5rem',
                    height: '3.5rem',
                    borderRadius: '50%',
                    border: '3px solid hsl(var(--primary) / 0.2)',
                    borderTopColor: 'hsl(var(--primary))',
                    animation: 'spin 0.8s linear infinite',
                    margin: '0 auto 1rem',
                  }}
                />
                <p style={{ fontWeight: 600, fontSize: '1rem' }}>
                  {executionStatus
                    ? (statusLabels[executionStatus.status] ?? t('migration.status.completing'))
                    : t('migration.running.starting')}
                </p>
                {executionStatus?.current_step && (
                  <p style={{ fontSize: '0.875rem', color: 'hsl(var(--muted-foreground))', marginTop: '0.25rem' }}>
                    {executionStatus.current_step}
                  </p>
                )}
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.375rem' }}>
                  <span style={{ fontSize: '0.8125rem', color: 'hsl(var(--muted-foreground))' }}>{t('migration.running.progress')}</span>
                  <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>
                    {executionStatus?.progress_percent ?? 0}%
                  </span>
                </div>
                <div
                  style={{
                    width: '100%',
                    height: '0.75rem',
                    borderRadius: '9999px',
                    background: 'hsl(var(--muted))',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${executionStatus?.progress_percent ?? 0}%`,
                      background: 'hsl(var(--primary))',
                      borderRadius: '9999px',
                      transition: 'width 0.4s ease',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: '1rem' }}>
                <div className={styles.statsCard} style={{ flex: 1, textAlign: 'center' }}>
                  <div className={styles.statsValue}>
                    {(executionStatus?.rows_migrated ?? 0).toLocaleString()}
                  </div>
                  <div className={styles.statsLabel}>{t('migration.running.rowsMigrated')}</div>
                </div>
                <div className={styles.statsCard} style={{ flex: 1, textAlign: 'center' }}>
                  <div className={styles.statsValue}>
                    {executionStatus?.estimated_remaining_seconds !== null && executionStatus?.estimated_remaining_seconds !== undefined
                      ? formatDuration(executionStatus.estimated_remaining_seconds)
                      : '—'}
                  </div>
                  <div className={styles.statsLabel}>{t('migration.running.timeLeft')}</div>
                </div>
              </div>
            </div>
          )}

          {/* ── STEP 4: RESULT ─────────────────────────────────────────── */}
          {step === 'result' && executionStatus && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {executionStatus.status === 'success' && (
                <div className={`${styles.alert} ${styles.alertSuccess}`}>
                  <div className={styles.alertContent}>
                    <CheckCircle2 className={`${styles.alertIcon} ${styles.alertIconSuccess}`} />
                    <div className={styles.alertBody}>
                      <p className={`${styles.alertTitle} ${styles.alertTitleSuccess}`}>
                        {t('migration.result.success')}
                      </p>
                      <p style={{ fontSize: '0.875rem', marginTop: '0.125rem' }}>
                        {t('migration.result.migratedCount', { count: executionStatus.rows_migrated.toLocaleString() })}
                      </p>
                    </div>
                  </div>
                </div>
              )}
              {executionStatus.status === 'dry_run_complete' && (
                <div className={`${styles.alert} ${styles.alertInfo}`} style={{ background: 'hsl(221 83% 96%)', borderColor: 'hsl(221 83% 82%)' }}>
                  <div className={styles.alertContent}>
                    <CheckCircle2 className={`${styles.alertIcon}`} style={{ color: 'hsl(221 83% 53%)' }} />
                    <div className={styles.alertBody}>
                      <p style={{ fontWeight: 500, color: 'hsl(221 83% 30%)' }}>
                        {t('migration.result.dryRunOk')}
                      </p>
                      <p style={{ fontSize: '0.875rem', marginTop: '0.125rem', color: 'hsl(221 83% 40%)' }}>
                        {t('migration.result.dryRunDesc')}
                      </p>
                    </div>
                  </div>
                </div>
              )}
              {(executionStatus.status === 'failed' || executionStatus.status === 'rolled_back') && (
                <div className={`${styles.alert} ${styles.alertError}`}>
                  <div className={styles.alertContent}>
                    <AlertCircle className={`${styles.alertIcon} ${styles.alertIconError}`} />
                    <div className={styles.alertBody}>
                      <p className={`${styles.alertTitle} ${styles.alertTitleError}`}>
                        {executionStatus.status === 'failed' ? t('migration.result.failed') : t('migration.result.rolledBack')}
                      </p>
                      {executionStatus.errors && (
                        <p style={{ fontSize: '0.875rem', marginTop: '0.25rem', fontFamily: 'monospace' }}>
                          {executionStatus.errors}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className={styles.statsGrid}>
                <div className={styles.statsCard}>
                  <div className={styles.statsValue}>
                    {executionStatus.rows_migrated.toLocaleString()}
                  </div>
                  <div className={styles.statsLabel}>{t('migration.result.statRows')}</div>
                </div>
                <div className={styles.statsCard}>
                  <div className={styles.statsValue}>
                    {executionStatus.execution_log.length}
                  </div>
                  <div className={styles.statsLabel}>{t('migration.result.statSteps')}</div>
                </div>
                <div className={styles.statsCard}>
                  <div className={styles.statsValue}>
                    {dryRun ? t('migration.result.dryRunYes') : t('migration.result.dryRunNo')}
                  </div>
                  <div className={styles.statsLabel}>{t('migration.result.statDryRun')}</div>
                </div>
              </div>

              {executionStatus.execution_log.length > 0 && (
                <div>
                  <button
                    onClick={() => setLogExpanded((v) => !v)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      fontSize: '0.875rem',
                      fontWeight: 500,
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: 'hsl(var(--foreground))',
                      padding: '0.5rem 0',
                      width: '100%',
                    }}
                  >
                    {logExpanded ? (
                      <ChevronRight
                        className="w-4 h-4"
                        style={{ transform: 'rotate(90deg)', transition: 'transform 0.2s' }}
                      />
                    ) : (
                      <ChevronRight className="w-4 h-4" style={{ transition: 'transform 0.2s' }} />
                    )}
                    {t('migration.log.title', { count: executionStatus.execution_log.length })}
                  </button>

                  {logExpanded && (
                    <div
                      style={{
                        overflowX: 'auto',
                        borderRadius: 'var(--mapping-border-radius, 0.5rem)',
                        border: '1px solid hsl(var(--border))',
                        marginTop: '0.5rem',
                      }}
                    >
                      <table style={{ width: '100%', fontSize: '0.8125rem', borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ background: 'hsl(var(--muted) / 0.5)' }}>
                            {logCols.map((h) => (
                              <th
                                key={h}
                                style={{
                                  padding: '0.5rem 0.75rem',
                                  textAlign: 'left',
                                  fontWeight: 600,
                                  borderBottom: '1px solid hsl(var(--border))',
                                  color: 'hsl(var(--muted-foreground))',
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {executionStatus.execution_log.map((entry, idx) => (
                            <tr
                              key={idx}
                              style={{
                                borderBottom: '1px solid hsl(var(--border) / 0.5)',
                                background: idx % 2 === 0 ? 'transparent' : 'hsl(var(--muted) / 0.2)',
                              }}
                            >
                              <td style={{ padding: '0.5rem 0.75rem' }}>{entry.step}</td>
                              <td style={{ padding: '0.5rem 0.75rem' }}>{entry.type ?? '—'}</td>
                              <td style={{ padding: '0.5rem 0.75rem', fontFamily: 'monospace' }}>{entry.table ?? '—'}</td>
                              <td style={{ padding: '0.5rem 0.75rem' }}>{entry.rows?.toLocaleString() ?? '—'}</td>
                              <td style={{ padding: '0.5rem 0.75rem' }}>{entry.duration !== undefined ? `${entry.duration}s` : '—'}</td>
                              <td style={{ padding: '0.5rem 0.75rem' }}>
                                <span
                                  style={{
                                    padding: '0.125rem 0.5rem',
                                    borderRadius: '9999px',
                                    fontSize: '0.75rem',
                                    fontWeight: 500,
                                    background:
                                      entry.status === 'success'
                                        ? '#dcfce7'
                                        : entry.status === 'failed'
                                        ? '#fee2e2'
                                        : 'hsl(var(--muted))',
                                    color:
                                      entry.status === 'success'
                                        ? '#166534'
                                        : entry.status === 'failed'
                                        ? '#991b1b'
                                        : 'hsl(var(--muted-foreground))',
                                  }}
                                >
                                  {entry.status ?? '—'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={styles.modalFooter}>
          <div className={styles.modalFooterLeft}>
            {step === 'config' && scriptOnly && t('migration.footer.scriptMode')}
            {step === 'config' && !scriptOnly && t('migration.footer.configure')}
            {step === 'preview' && generatedScript && t('migration.footer.scriptId', { id: generatedScript.script_id.slice(0, 8) })}
            {step === 'running' && t('migration.footer.inProgress')}
            {step === 'result' && executionStatus && statusLabels[executionStatus.status]}
          </div>
          <div className={styles.modalFooterRight}>
            {step === 'config' && (
              <>
                <button onClick={onClose} className={styles.toolbarButton}>
                  {t('migration.cancelBtn')}
                </button>
                <button
                  onClick={handleGenerate}
                  disabled={isGenerating}
                  className={styles.toolbarButtonPrimary}
                >
                  {isGenerating ? (
                    <>
                      <div
                        style={{
                          width: '1rem',
                          height: '1rem',
                          borderRadius: '50%',
                          border: '2px solid transparent',
                          borderTopColor: 'white',
                          animation: 'spin 0.8s linear infinite',
                        }}
                      />
                      {t('migration.generating')}
                    </>
                  ) : (
                    <>
                      <ChevronRight className="w-4 h-4" />
                      {t('migration.generateBtn')}
                    </>
                  )}
                </button>
              </>
            )}

            {step === 'preview' && (
              <>
                <button
                  onClick={() => setStep('config')}
                  className={styles.toolbarButton}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}
                >
                  <ChevronLeft className="w-4 h-4" />
                  {t('migration.backBtn')}
                </button>
                {scriptOnly ? (
                  <button onClick={onClose} className={styles.toolbarButtonPrimary}>
                    {t('migration.closeBtn')}
                  </button>
                ) : (
                  <button
                    onClick={handleExecute}
                    disabled={isStarting}
                    className={styles.toolbarButtonPrimary}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}
                  >
                    {isStarting ? (
                      <>
                        <div
                          style={{
                            width: '1rem',
                            height: '1rem',
                            borderRadius: '50%',
                            border: '2px solid transparent',
                            borderTopColor: 'white',
                            animation: 'spin 0.8s linear infinite',
                          }}
                        />
                        {t('migration.starting')}
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4" />
                        {t('migration.runBtn')}
                      </>
                    )}
                  </button>
                )}
              </>
            )}

            {step === 'running' && (
              <button onClick={onClose} className={styles.toolbarButton} disabled>
                {t('migration.cancelBtn')}
              </button>
            )}

            {step === 'result' && (
              <button onClick={onClose} className={styles.toolbarButtonPrimary}>
                {t('migration.closeBtn')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>

    <MigrationGuideModal isOpen={showGuideModal} onClose={() => setShowGuideModal(false)} dialect={dialect} />
    </>
  );
};
