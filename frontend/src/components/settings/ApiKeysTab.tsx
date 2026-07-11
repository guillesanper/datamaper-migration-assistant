// src/components/settings/ApiKeysTab.tsx
import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Copy, Check, Trash2, Loader2, Key } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { settingsService } from '../../services/settings_service';
import type { NewApiKey } from '../../types/settings_types';
import { toast } from '../../utils/toast';
import { secureCleanupState } from '../../utils/secureMemory';

export const ApiKeysTab: React.FC = () => {
  const { t, i18n } = useTranslation(['settings', 'common']);
  const queryClient = useQueryClient();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createExpiry, setCreateExpiry] = useState('');
  const [newKeyResult, setNewKeyResult] = useState<NewApiKey | null>(null);
  const [rawKey, setRawKey] = useState('');
  const [copiedKey, setCopiedKey] = useState(false);
  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null);

  const expiryOptions = [
    { label: t('settings:apiKeys.expiry.none'), value: '' },
    { label: t('settings:apiKeys.expiry.30d'), value: '30' },
    { label: t('settings:apiKeys.expiry.90d'), value: '90' },
    { label: t('settings:apiKeys.expiry.1y'), value: '365' },
  ];

  // Secure cleanup on unmount
  useEffect(() => {
    return () => {
      secureCleanupState(setRawKey);
    };
  }, []);

  const { data: apiKeys, isLoading } = useQuery({
    queryKey: ['settings', 'api-keys'],
    queryFn: () => settingsService.getApiKeys(),
  });

  const createMutation = useMutation({
    mutationFn: ({ name, expiresInDays }: { name: string; expiresInDays?: number }) =>
      settingsService.createApiKey(name, expiresInDays),
    onSuccess: (newKey) => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'api-keys'] });
      setNewKeyResult(newKey);
      setRawKey(newKey.raw_key);
      setShowCreateForm(false);
      setCreateName('');
      setCreateExpiry('');
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => settingsService.revokeApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'api-keys'] });
      setConfirmRevokeId(null);
      toast.success(t('settings:apiKeys.revokedSuccess'));
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!createName.trim()) return;
    const expiresInDays = createExpiry ? parseInt(createExpiry, 10) : undefined;
    createMutation.mutate({ name: createName.trim(), expiresInDays });
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(rawKey).then(() => {
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    });
  };

  const handleCloseResult = () => {
    secureCleanupState(setRawKey);
    setNewKeyResult(null);
  };

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleDateString(
      i18n.language === 'es' ? 'es-ES' : 'en-US',
      { day: '2-digit', month: '2-digit', year: 'numeric' }
    );
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            {t('settings:apiKeys.description')}{' '}
            <code className="text-xs bg-muted px-1 py-0.5 rounded font-mono">
              Authorization: Bearer rlk_...
            </code>
          </p>
        </div>
        {!showCreateForm && !newKeyResult && (
          <Button
            size="sm"
            onClick={() => setShowCreateForm(true)}
            className="gap-2 flex-shrink-0"
          >
            <Plus size={14} />
            {t('settings:apiKeys.create')}
          </Button>
        )}
      </div>

      {/* Create form */}
      {showCreateForm && (
        <section className="rounded-lg border border-border bg-card p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4">
            {t('settings:apiKeys.createFormTitle')}
          </h2>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                {t('settings:apiKeys.name.label')} <span className="text-destructive">*</span>
              </label>
              <Input
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder={t('settings:apiKeys.name.placeholder')}
                maxLength={100}
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                {t('settings:apiKeys.expiry.label')}
              </label>
              <Select value={createExpiry} onValueChange={setCreateExpiry}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t('settings:apiKeys.expiry.none')} />
                </SelectTrigger>
                <SelectContent>
                  {expiryOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 pt-1">
              <Button
                type="submit"
                disabled={!createName.trim() || createMutation.isPending}
                className="gap-2"
              >
                {createMutation.isPending && <Loader2 size={14} className="animate-spin" />}
                {t('common:actions.create')}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setShowCreateForm(false);
                  setCreateName('');
                  setCreateExpiry('');
                }}
                disabled={createMutation.isPending}
              >
                {t('common:actions.cancel')}
              </Button>
            </div>
          </form>
        </section>
      )}

      {/* New key result */}
      {newKeyResult && (
        <section className="rounded-lg border border-yellow-300 bg-yellow-50 p-6 space-y-4">
          <div className="flex items-start gap-3">
            <Key size={18} className="text-yellow-700 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-yellow-900">
                {t('settings:apiKeys.new.title')}: <span className="font-normal">{newKeyResult.name}</span>
              </p>
              <p className="text-xs text-yellow-700 mt-1">
                ⚠️ {t('settings:apiKeys.new.warning')}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 bg-white rounded-lg border border-yellow-200 p-3">
            <code className="flex-1 text-xs font-mono text-foreground break-all">{rawKey}</code>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              onClick={handleCopy}
              title={t('common:actions.copy')}
              className="flex-shrink-0"
            >
              {copiedKey ? <Check size={14} className="text-green-600" /> : <Copy size={14} />}
            </Button>
          </div>
          <Button variant="outline" size="sm" onClick={handleCloseResult}>
            {t('settings:apiKeys.new.acknowledge')}
          </Button>
        </section>
      )}

      {/* Keys list */}
      <section className="rounded-lg border border-border bg-card overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={20} className="animate-spin text-muted-foreground" />
          </div>
        ) : !apiKeys?.length ? (
          <div className="text-center py-12 text-sm text-muted-foreground">
            {t('settings:apiKeys.empty')}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">
                  {t('settings:apiKeys.table.name')}
                </th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">
                  {t('settings:apiKeys.table.prefix')}
                </th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">
                  {t('settings:apiKeys.table.created')}
                </th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">
                  {t('settings:apiKeys.table.lastUsed')}
                </th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">
                  {t('settings:apiKeys.table.expires')}
                </th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground">
                  {t('settings:apiKeys.table.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {apiKeys.map((key) => (
                <React.Fragment key={key.id}>
                  <tr className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-medium text-foreground">
                      {key.name}
                      {!key.is_active && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({t('settings:apiKeys.status.revoked')})
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground font-mono text-xs hidden sm:table-cell">
                      rlk_{key.key_prefix}...
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs hidden md:table-cell">
                      {formatDate(key.created_at)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs hidden md:table-cell">
                      {formatDate(key.last_used_at)}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground text-xs hidden lg:table-cell">
                      {key.expires_at ? formatDate(key.expires_at) : t('settings:apiKeys.neverUsed')}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {key.is_active && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setConfirmRevokeId(key.id)}
                          className="text-destructive hover:text-destructive gap-1.5"
                          disabled={revokeMutation.isPending && confirmRevokeId === key.id}
                        >
                          <Trash2 size={14} />
                          <span className="hidden sm:inline">{t('settings:apiKeys.revoke')}</span>
                        </Button>
                      )}
                    </td>
                  </tr>
                  {/* Inline confirm row */}
                  {confirmRevokeId === key.id && (
                    <tr>
                      <td colSpan={6} className="px-4 py-3 bg-destructive/5 border-t border-destructive/20">
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="text-sm text-foreground">
                            {t('settings:apiKeys.revokeConfirm', { name: key.name })}
                          </span>
                          <div className="flex gap-2">
                            <Button
                              variant="destructive"
                              size="sm"
                              onClick={() => revokeMutation.mutate(key.id)}
                              disabled={revokeMutation.isPending}
                              className="gap-2"
                            >
                              {revokeMutation.isPending && <Loader2 size={12} className="animate-spin" />}
                              {t('common:actions.confirm')}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setConfirmRevokeId(null)}
                              disabled={revokeMutation.isPending}
                            >
                              {t('common:actions.cancel')}
                            </Button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
};
