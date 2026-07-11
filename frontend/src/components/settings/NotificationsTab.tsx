// src/components/settings/NotificationsTab.tsx
import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { settingsService } from '../../services/settings_service';
import type { NotificationPrefs } from '../../types/settings_types';
import { toast } from '../../utils/toast';

type NotifKey = keyof NotificationPrefs['email_notifications'];

const NOTIF_KEYS: NotifKey[] = ['invitations', 'comments', 'version_updates', 'security_alerts'];

interface ToggleProps {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
}

const Toggle: React.FC<ToggleProps> = ({ checked, onChange, disabled }) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    onClick={onChange}
    disabled={disabled}
    className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
      checked ? 'bg-primary' : 'bg-muted'
    }`}
  >
    <span
      className={`inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform mt-0.5 ${
        checked ? 'translate-x-4' : 'translate-x-0.5'
      }`}
    />
  </button>
);

const DEFAULT_PREFS: NotificationPrefs = {
  email_notifications: {
    invitations: true,
    comments: true,
    version_updates: false,
    security_alerts: true,
  },
  in_app_notifications: {
    invitations: true,
    comments: true,
    version_updates: true,
    security_alerts: true,
  },
};

export const NotificationsTab: React.FC = () => {
  const { t } = useTranslation('settings');
  const queryClient = useQueryClient();
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);

  const notificationLabels: Record<NotifKey, string> = {
    invitations: t('notifications.projectInvitations'),
    comments: t('notifications.comments'),
    version_updates: t('notifications.versionUpdates'),
    security_alerts: t('notifications.securityAlerts'),
  };

  const sections: Array<{
    title: string;
    description: string;
    category: 'email_notifications' | 'in_app_notifications';
  }> = [
    {
      title: t('notifications.email.title'),
      description: t('notifications.email.description'),
      category: 'email_notifications',
    },
    {
      title: t('notifications.push.title'),
      description: t('notifications.push.description'),
      category: 'in_app_notifications',
    },
  ];

  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'notifications'],
    queryFn: () => settingsService.getNotificationPrefs(),
  });

  useEffect(() => {
    if (data) {
      // Merge with defaults to ensure all keys exist
      setPrefs({
        email_notifications: { ...DEFAULT_PREFS.email_notifications, ...data.email_notifications },
        in_app_notifications: { ...DEFAULT_PREFS.in_app_notifications, ...data.in_app_notifications },
      });
    }
  }, [data]);

  const mutation = useMutation({
    mutationFn: (updated: NotificationPrefs) => settingsService.updateNotificationPrefs(updated),
    onSuccess: (updated) => {
      queryClient.setQueryData(['settings', 'notifications'], updated);
      toast.success(t('notifications.save.success'));
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const handleToggle = (
    category: 'email_notifications' | 'in_app_notifications',
    key: NotifKey
  ) => {
    if (!prefs) return;
    const newPrefs: NotificationPrefs = {
      ...prefs,
      [category]: {
        ...prefs[category],
        [key]: !prefs[category][key],
      },
    };
    setPrefs(newPrefs);
    mutation.mutate(newPrefs);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={24} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  const currentPrefs = prefs ?? DEFAULT_PREFS;

  return (
    <div className="space-y-8 max-w-4xl">
      {sections.map(({ title, description, category }) => (
        <section key={category} className="rounded-lg border border-border bg-card p-6">
          <div className="mb-5">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              {title}
            </h2>
            <p className="text-xs text-muted-foreground mt-1">{description}</p>
          </div>
          <div className="space-y-4">
            {NOTIF_KEYS.map((key) => (
              <div key={key} className="flex items-center justify-between">
                <span className="text-sm text-foreground">{notificationLabels[key]}</span>
                <Toggle
                  checked={currentPrefs[category][key]}
                  onChange={() => handleToggle(category, key)}
                  disabled={mutation.isPending}
                />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
};
