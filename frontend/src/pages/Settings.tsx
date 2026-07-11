// src/pages/Settings.tsx
import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { User, Bell, SlidersHorizontal, Shield, Key } from 'lucide-react';
import { ProfileTab } from '../components/settings/ProfileTab';
import { NotificationsTab } from '../components/settings/NotificationsTab';
import { PreferencesTab } from '../components/settings/PreferencesTab';
import { SecurityTab } from '../components/settings/SecurityTab';
import { ApiKeysTab } from '../components/settings/ApiKeysTab';

type SettingsTab = 'profile' | 'notifications' | 'preferences' | 'security' | 'api-keys';

const TAB_META: { id: SettingsTab; icon: React.ComponentType<{ size?: number }> }[] = [
  { id: 'profile', icon: User },
  { id: 'notifications', icon: Bell },
  { id: 'preferences', icon: SlidersHorizontal },
  { id: 'security', icon: Shield },
  { id: 'api-keys', icon: Key },
];

export const Settings: React.FC = () => {
  const { t } = useTranslation('settings');
  const [activeTab, setActiveTab] = useState<SettingsTab>('profile');

  const tabLabels: Record<SettingsTab, string> = {
    profile: t('tabs.profile'),
    notifications: t('tabs.notifications'),
    preferences: t('tabs.preferences'),
    security: t('tabs.security'),
    'api-keys': t('tabs.apiKeys'),
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-foreground">{t('page.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('page.subtitle')}</p>
      </div>

      {/* Tab bar */}
      <div className="border-b border-border">
        <nav className="flex -mb-px overflow-x-auto">
          {TAB_META.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              <tab.icon size={16} />
              {tabLabels[tab.id]}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div className=''>
        {activeTab === 'profile' && <ProfileTab />}
        {activeTab === 'notifications' && <NotificationsTab />}
        {activeTab === 'preferences' && <PreferencesTab />}
        {activeTab === 'security' && <SecurityTab />}
        {activeTab === 'api-keys' && <ApiKeysTab />}
      </div>
    </div>
  );
};
