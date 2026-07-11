// src/components/settings/SecurityTab.tsx
import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom';
import { useTranslation } from 'react-i18next';
import { type TFunction } from 'i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Monitor,
  Smartphone,
  Shield,
  ShieldCheck,
  Loader2,
  X,
  Trash2,
} from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { settingsService } from '../../services/settings_service';
import type { TwoFASetup } from '../../types/settings_types';
import { toast } from '../../utils/toast';
import { secureCleanupState } from '../../utils/secureMemory';

// ---- Helpers ----------------------------------------------------------------

const getDeviceType = (ua: string): 'mobile' | 'desktop' =>
  /mobile|android|iphone|ipad/i.test(ua) ? 'mobile' : 'desktop';

const formatRelative = (dateStr: string, t: TFunction<['settings', 'common']>): string => {
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 60000);
  if (diff < 1) return t('common:time.now');
  if (diff < 60) return t('common:time.minutes', { count: diff });
  const hours = Math.floor(diff / 60);
  if (hours < 24) return t('common:time.hours', { count: hours });
  return t('common:time.days', { count: Math.floor(hours / 24) });
};

const SEVERITY_COLORS: Record<string, string> = {
  info: 'bg-blue-100 text-blue-800',
  warning: 'bg-yellow-100 text-yellow-800',
  error: 'bg-red-100 text-red-800',
  critical: 'bg-red-200 text-red-900 font-semibold',
};

// ---- 2FA Modal --------------------------------------------------------------

interface TwoFASetupModalProps {
  twoFAData: TwoFASetup;
  onClose: () => void;
  onVerify: (code: string) => void;
  isPending: boolean;
}

const TwoFASetupModal: React.FC<TwoFASetupModalProps> = ({
  twoFAData,
  onClose,
  onVerify,
  isPending,
}) => {
  const { t } = useTranslation('settings');
  const [code, setCode] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (code.length === 6) onVerify(code);
  };

  return ReactDOM.createPortal(
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3 className="modal-title">{t('security.2fa.setup.title')}</h3>
          <button onClick={onClose} disabled={isPending} className="btn-icon">
            <X size={20} />
          </button>
        </div>
        <div className="p-6 space-y-5">
          <p className="text-sm text-muted-foreground">
            {t('security.2fa.setup.step1')}
          </p>
          <div className="flex justify-center">
            <img
              src={`data:image/png;base64,${twoFAData.qr_code_base64}`}
              alt="QR Code 2FA"
              className="w-48 h-48 border border-border rounded-lg"
            />
          </div>
          <p className="text-xs text-muted-foreground text-center break-all font-mono bg-muted rounded p-2">
            {twoFAData.secret}
          </p>
          <p className="text-sm text-muted-foreground">
            {t('security.2fa.setup.step2')}
          </p>
          <form onSubmit={handleSubmit} className="space-y-3">
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder={t('security.2fa.setup.placeholder')}
              maxLength={6}
              inputMode="numeric"
              pattern="[0-9]*"
              autoFocus
              className="text-center text-lg tracking-widest font-mono"
            />
            <div className="flex gap-2 justify-end">
              <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
                {t('security.2fa.setup.cancel')}
              </Button>
              <Button type="submit" disabled={code.length !== 6 || isPending} className="gap-2">
                {isPending && <Loader2 size={14} className="animate-spin" />}
                {t('security.2fa.setup.verify')}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>,
    document.body
  );
};

// ---- Disable 2FA Modal ------------------------------------------------------

interface Disable2FAModalProps {
  onClose: () => void;
  onDisable: (code: string, password: string) => void;
  isPending: boolean;
}

const Disable2FAModal: React.FC<Disable2FAModalProps> = ({ onClose, onDisable, isPending }) => {
  const { t } = useTranslation('settings');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');

  useEffect(() => {
    return () => {
      secureCleanupState(setPassword);
    };
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onDisable(code, password);
  };

  return ReactDOM.createPortal(
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: 440 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3 className="modal-title">{t('security.2fa.deactivate.title')}</h3>
          <button onClick={onClose} disabled={isPending} className="btn-icon">
            <X size={20} />
          </button>
        </div>
        <div className="p-6 space-y-4">
          <p className="text-sm text-muted-foreground">
            {t('security.2fa.deactivate.desc')}
          </p>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                {t('security.2fa.deactivate.currentPassword')}
              </label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                {t('security.2fa.deactivate.totpCode')}
              </label>
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder={t('security.2fa.setup.placeholder')}
                maxLength={6}
                inputMode="numeric"
                pattern="[0-9]*"
                className="text-center tracking-widest font-mono"
              />
            </div>
            <div className="flex gap-2 justify-end pt-1">
              <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
                {t('security.2fa.setup.cancel')}
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={code.length !== 6 || !password || isPending}
                className="gap-2"
              >
                {isPending && <Loader2 size={14} className="animate-spin" />}
                {t('security.2fa.disable')}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>,
    document.body
  );
};

// ---- Main component ---------------------------------------------------------

export const SecurityTab: React.FC = () => {
  const { t, i18n } = useTranslation(['settings', 'common']);
  const queryClient = useQueryClient();

  const [show2FASetup, setShow2FASetup] = useState(false);
  const [twoFAData, setTwoFAData] = useState<TwoFASetup | null>(null);
  const [showDisable2FA, setShowDisable2FA] = useState(false);

  // Queries
  const { data: sessions, isLoading: sessionsLoading } = useQuery({
    queryKey: ['settings', 'sessions'],
    queryFn: () => settingsService.getSessions(),
  });

  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['settings', 'access-history'],
    queryFn: () => settingsService.getAccessHistory(20, 0),
  });

  const { data: profile } = useQuery({
    queryKey: ['settings', 'profile'],
    queryFn: () => settingsService.getProfile(),
    staleTime: Infinity,
  });

  // Mutations
  const revokeSessionMutation = useMutation({
    mutationFn: (id: string) => settingsService.revokeSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'sessions'] });
      toast.success(t('security.sessions.revoked'));
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const setup2FAMutation = useMutation({
    mutationFn: () => settingsService.setup2FA(),
    onSuccess: (data) => {
      setTwoFAData(data);
      setShow2FASetup(true);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const verify2FAMutation = useMutation({
    mutationFn: (code: string) => settingsService.verify2FA(code),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'profile'] });
      setShow2FASetup(false);
      setTwoFAData(null);
      toast.success(t('security.2fa.success.enabled'));
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const disable2FAMutation = useMutation({
    mutationFn: ({ code, password }: { code: string; password: string }) =>
      settingsService.disable2FA(code, password),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'profile'] });
      setShowDisable2FA(false);
      toast.success(t('security.2fa.success.disabled'));
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const totpEnabled = profile?.totp_enabled ?? false;

  return (
    <div className="space-y-8 max-w-4xl">
      {/* Sessions */}
      <section className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-5">
          {t('security.sessions.title')}
        </h2>
        {sessionsLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={20} className="animate-spin text-muted-foreground" />
          </div>
        ) : !sessions?.length ? (
          <p className="text-sm text-muted-foreground text-center py-6">{t('security.sessions.empty')}</p>
        ) : (
          <div className="space-y-3">
            {sessions.map((session) => {
              const device = getDeviceType(session.user_agent);
              const DeviceIcon = device === 'mobile' ? Smartphone : Monitor;
              return (
                <div
                  key={session.id}
                  className="flex items-center gap-4 p-3 rounded-lg border border-border hover:bg-muted/30 transition-colors"
                >
                  <DeviceIcon size={20} className="text-muted-foreground flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-foreground">
                        {session.ip_address || t('security.sessions.unknownIp')}
                      </span>
                      {session.is_current && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-800 font-medium">
                          {t('security.sessions.current')}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">
                      {formatRelative(session.last_activity, t)}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    disabled={session.is_current || revokeSessionMutation.isPending}
                    onClick={() => revokeSessionMutation.mutate(session.id)}
                    title={session.is_current ? t('security.sessions.cantRevoke') : t('security.sessions.revoke')}
                    className="text-destructive hover:text-destructive flex-shrink-0"
                  >
                    <Trash2 size={16} />
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* 2FA */}
      <section className="rounded-lg border border-border bg-card p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              {t('security.2fa.title')}
            </h2>
            <p className="text-sm text-muted-foreground">
              {t('security.2fa.description')}
            </p>
          </div>
          {totpEnabled ? (
            <span className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-green-100 text-green-800 font-medium flex-shrink-0">
              <ShieldCheck size={14} />
              {t('security.2fa.enabled')}
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-muted text-muted-foreground font-medium flex-shrink-0">
              <Shield size={14} />
              {t('security.2fa.disabled')}
            </span>
          )}
        </div>
        <div className="mt-4">
          {totpEnabled ? (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setShowDisable2FA(true)}
            >
              {t('security.2fa.disable')}
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setup2FAMutation.mutate()}
              disabled={setup2FAMutation.isPending}
              className="gap-2"
            >
              {setup2FAMutation.isPending && <Loader2 size={14} className="animate-spin" />}
              {t('security.2fa.enable')}
            </Button>
          )}
        </div>
      </section>

      {/* Access history */}
      <section className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-5">
          {t('security.accessLog.title')}
        </h2>
        {historyLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={20} className="animate-spin text-muted-foreground" />
          </div>
        ) : !history?.length ? (
          <p className="text-sm text-muted-foreground text-center py-6">{t('security.accessLog.empty')}</p>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    {t('security.accessLog.cols.event')}
                  </th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    {t('security.accessLog.cols.ip')}
                  </th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    {t('security.accessLog.cols.severity')}
                  </th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground">
                    {t('security.accessLog.cols.date')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {history.map((entry, idx) => (
                  <tr key={idx} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-2 font-mono text-xs text-foreground">{entry.event_type}</td>
                    <td className="px-4 py-2 text-muted-foreground text-xs font-mono">
                      {entry.ip_address || '—'}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs ${
                          SEVERITY_COLORS[entry.severity] ?? 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {entry.severity}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-muted-foreground text-xs">
                      {new Date(entry.created_at).toLocaleString(
                        i18n.language === 'es' ? 'es-ES' : 'en-US'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 2FA Setup Modal */}
      {show2FASetup && twoFAData && (
        <TwoFASetupModal
          twoFAData={twoFAData}
          onClose={() => {
            setShow2FASetup(false);
            setTwoFAData(null);
          }}
          onVerify={(code) => verify2FAMutation.mutate(code)}
          isPending={verify2FAMutation.isPending}
        />
      )}

      {/* Disable 2FA Modal */}
      {showDisable2FA && (
        <Disable2FAModal
          onClose={() => setShowDisable2FA(false)}
          onDisable={(code, password) => disable2FAMutation.mutate({ code, password })}
          isPending={disable2FAMutation.isPending}
        />
      )}
    </div>
  );
};
