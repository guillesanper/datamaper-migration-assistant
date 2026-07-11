// src/components/dashboard/Topbar.tsx
import React, { useEffect, useState } from 'react';
import { Search, Bell, Settings, Sun, Moon, Laptop, Menu } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../../providers/ThemeProvider';
import { Button } from '../ui/button';
import { NotificationsPanel } from './NotificationsPanel';
import { notificationService } from '../../services/notification_service';

interface TopbarProps {
  onMenuClick?: () => void;
}

export const Topbar: React.FC<TopbarProps> = ({ onMenuClick }) => {
  const { theme, setTheme } = useTheme();
  const { t, i18n } = useTranslation('dashboard');
  const [panelOpen, setPanelOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const themeIcons = {
    light: Sun,
    dark: Moon,
    system: Laptop
  };

  const ThemeIcon = themeIcons[theme];

  const cycleTheme = () => {
    const themes: Array<'light' | 'dark' | 'system'> = ['light', 'dark', 'system'];
    const currentIndex = themes.indexOf(theme);
    const nextIndex = (currentIndex + 1) % themes.length;
    setTheme(themes[nextIndex]);
  };

  const toggleLanguage = () => {
    void i18n.changeLanguage(i18n.language === 'es' ? 'en' : 'es');
  };

  useEffect(() => {
    notificationService.getUnreadCount().then(setUnreadCount).catch(() => {});
  }, []);

  return (
    <header className="topbar">
      {onMenuClick && (
        <button
          onClick={onMenuClick}
          className="menu-button"
          aria-label={t('topbar.aria.openMenu')}
        >
          <Menu size={20} />
        </button>
      )}

      <div className="topbar-search">
        <Search size={20} className="text-muted-foreground" />
        <input
          type="text"
          placeholder={t('topbar.search.placeholder')}
          className="flex-1 bg-transparent outline-none text-sm"
        />
      </div>

      <div className="topbar-actions">
        <Button
          onClick={toggleLanguage}
          size="sm"
          variant="outline"
          aria-label={t('topbar.aria.toggleLanguage')}
          className="font-medium"
        >
          {i18n.language === 'es' ? 'EN' : 'ES'}
        </Button>

        <div className="relative">
          <Button
            size="icon"
            aria-label={t('topbar.aria.notifications')}
            variant="outline"
            className="relative"
            onClick={() => setPanelOpen((prev) => !prev)}
          >
            <Bell size={20} />
            {unreadCount > 0 && (
              <span className="notification-dot">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </Button>

          {panelOpen && (
            <NotificationsPanel
              onClose={() => setPanelOpen(false)}
              onUnreadCountChange={setUnreadCount}
            />
          )}
        </div>

        <Button onClick={cycleTheme} size="icon" variant="outline" aria-label={t('topbar.aria.theme')}>
          <ThemeIcon size={20} />
        </Button>

        <Button size="icon" variant="outline" className="hidden sm:flex" aria-label={t('topbar.aria.settings')}>
          <Settings size={20} />
        </Button>
      </div>
    </header>
  );
};
