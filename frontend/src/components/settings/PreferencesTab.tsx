// src/components/settings/PreferencesTab.tsx
import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '../ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { settingsService } from '../../services/settings_service';
import type { UserPreferences } from '../../types/settings_types';
import { toast } from '../../utils/toast';

const TIMEZONES = [
  'UTC',
  'America/Mexico_City',
  'America/Bogota',
  'America/Lima',
  'America/Argentina/Buenos_Aires',
  'America/Santiago',
  'Europe/Madrid',
  'Europe/London',
];

const DB_TYPES = ['postgresql', 'mysql', 'mariadb', 'sqlserver', 'oracle'];

const EXPORT_FORMATS = ['xlsx', 'csv', 'json'];

const DB_NONE = '__none__';

export const PreferencesTab: React.FC = () => {
  const { t } = useTranslation('settings');
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ['settings', 'preferences'],
    queryFn: () => settingsService.getPreferences(),
  });

  useEffect(() => {
    if (isError) {
      toast.error(t('preferences.error.load'));
    }
  }, [isError, t]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={24} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <p className="text-sm text-muted-foreground">{t('preferences.error.load')}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => queryClient.invalidateQueries({ queryKey: ['settings', 'preferences'] })}
        >
          {t('preferences.error.retry')}
        </Button>
      </div>
    );
  }

  return <PreferencesForm initialData={data} />;
};

interface PreferencesFormProps {
  initialData: UserPreferences;
}

const PreferencesForm: React.FC<PreferencesFormProps> = ({ initialData }) => {
  const { t } = useTranslation('settings');
  const queryClient = useQueryClient();

  const [form, setForm] = useState<UserPreferences>(() => ({
    language: initialData.language,
    timezone: initialData.timezone,
    default_db_type: initialData.default_db_type,
    default_export_format: initialData.default_export_format,
  }));

  const mutation = useMutation({
    mutationFn: (updated: Partial<UserPreferences>) => settingsService.updatePreferences(updated),
    onSuccess: (updated) => {
      queryClient.setQueryData(['settings', 'preferences'], updated);
      setForm(updated);
      toast.success(t('preferences.save.success'));
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate(form);
  };

  const setField = <K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  // Incluye el valor actual en la lista si el backend devuelve algo fuera de los
  // presets (ej: timezone guardada desde otra versión del front).
  const languageOptions = useMemo(() => {
    const langs = [
      { value: 'es', label: t('preferences.language.es') },
      { value: 'en', label: t('preferences.language.en') },
    ];
    return langs.some((o) => o.value === form.language)
      ? langs
      : [{ value: form.language, label: form.language }, ...langs];
  }, [form.language, t]);

  const timezoneOptions = useMemo(
    () => (TIMEZONES.includes(form.timezone) ? TIMEZONES : [form.timezone, ...TIMEZONES]),
    [form.timezone],
  );

  const dbTypeOptions = useMemo(() => {
    const current = form.default_db_type;
    if (!current || DB_TYPES.includes(current)) return DB_TYPES;
    return [current, ...DB_TYPES];
  }, [form.default_db_type]);

  const exportFormatOptions = useMemo(
    () =>
      EXPORT_FORMATS.includes(form.default_export_format)
        ? EXPORT_FORMATS
        : [form.default_export_format, ...EXPORT_FORMATS],
    [form.default_export_format],
  );

  const dbSelectValue = form.default_db_type ?? DB_NONE;

  return (
    <div className="max-w-2xl">
      <section className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-5">
          {t('preferences.section')}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Language */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">{t('preferences.language.label')}</label>
            <Select
              value={form.language}
              onValueChange={(v) => setField('language', v)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('preferences.language.placeholder')} />
              </SelectTrigger>
              <SelectContent>
                {languageOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Timezone */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">{t('preferences.timezone.label')}</label>
            <Select
              value={form.timezone}
              onValueChange={(v) => setField('timezone', v)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('preferences.timezone.placeholder')} />
              </SelectTrigger>
              <SelectContent>
                {timezoneOptions.map((tz) => (
                  <SelectItem key={tz} value={tz}>
                    {tz}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Default DB Type */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">{t('preferences.defaultDb.label')}</label>
            <Select
              value={dbSelectValue}
              onValueChange={(v) => setField('default_db_type', v === DB_NONE ? null : v)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('preferences.defaultDb.none')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DB_NONE}>{t('preferences.defaultDb.none')}</SelectItem>
                {dbTypeOptions.map((db) => (
                  <SelectItem key={db} value={db}>
                    {db}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Export format */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground">{t('preferences.defaultExport.label')}</label>
            <Select
              value={form.default_export_format}
              onValueChange={(v) => setField('default_export_format', v)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder={t('preferences.defaultExport.placeholder')} />
              </SelectTrigger>
              <SelectContent>
                {exportFormatOptions.map((fmt) => (
                  <SelectItem key={fmt} value={fmt}>
                    {fmt.toUpperCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button type="submit" disabled={mutation.isPending} className="gap-2">
            {mutation.isPending && <Loader2 size={14} className="animate-spin" />}
            {t('preferences.save.btn')}
          </Button>
        </form>
      </section>
    </div>
  );
};
