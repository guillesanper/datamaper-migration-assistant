import React, { useCallback, useEffect, useRef, useState } from "react";
import { Bell, Check, CheckCheck, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { notificationService, type Notification } from "../../services/notification_service";
import { Button } from "../ui/button";

interface NotificationsPanelProps {
  onClose: () => void;
  onUnreadCountChange: (count: number) => void;
}

function timeAgo(isoString: string, t: TFunction<['dashboard', 'common']>): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return t("dashboard:notifications.now");
  if (minutes < 60) return t("dashboard:notifications.minutesAgo", { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t("dashboard:notifications.hoursAgo", { count: hours });
  const days = Math.floor(hours / 24);
  return t("dashboard:notifications.daysAgo", { count: days });
}

export const NotificationsPanel: React.FC<NotificationsPanelProps> = ({
  onClose,
  onUnreadCountChange,
}) => {
  const { t } = useTranslation(["dashboard", "common"]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const panelRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await notificationService.getNotifications({ limit: 20 });
      setNotifications(data);
      const unread = data.filter((n) => !n.read_at).length;
      onUnreadCountChange(unread);
    } finally {
      setLoading(false);
    }
  }, [onUnreadCountChange]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  const handleMarkRead = async (id: string) => {
    await notificationService.markAsRead(id);
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n))
    );
    onUnreadCountChange(
      notifications.filter((n) => !n.read_at && n.id !== id).length
    );
  };

  const handleMarkAll = async () => {
    await notificationService.markAllAsRead();
    const now = new Date().toISOString();
    setNotifications((prev) => prev.map((n) => ({ ...n, read_at: n.read_at ?? now })));
    onUnreadCountChange(0);
  };

  const unreadCount = notifications.filter((n) => !n.read_at).length;

  return (
    <div
      ref={panelRef}
      className="notifications-panel"
      role="dialog"
      aria-label={t("dashboard:notifications.title")}
    >
      <div className="notifications-panel-header">
        <div className="flex items-center gap-2">
          <Bell size={16} />
          <span className="font-semibold text-sm">{t("dashboard:notifications.title")}</span>
          {unreadCount > 0 && (
            <span className="notifications-badge">{unreadCount}</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {unreadCount > 0 && (
            <Button
              size="icon"
              variant="ghost"
              onClick={handleMarkAll}
              title={t("dashboard:notifications.markAllRead")}
              className="h-7 w-7"
            >
              <CheckCheck size={14} />
            </Button>
          )}
          <Button
            size="icon"
            variant="ghost"
            onClick={onClose}
            aria-label={t("common:actions.close")}
            className="h-7 w-7"
          >
            <X size={14} />
          </Button>
        </div>
      </div>

      <div className="notifications-panel-body">
        {loading ? (
          <div className="notifications-skeleton-list">
            {[1, 2, 3].map((i) => (
              <div key={i} className="notifications-skeleton-item">
                <div className="skeleton skeleton-title" />
                <div className="skeleton skeleton-body" />
              </div>
            ))}
          </div>
        ) : notifications.length === 0 ? (
          <div className="notifications-empty">
            <Bell size={32} className="text-muted-foreground opacity-40" />
            <p className="text-sm text-muted-foreground mt-2">{t("dashboard:notifications.empty")}</p>
          </div>
        ) : (
          <ul className="notifications-list">
            {notifications.map((notif) => (
              <li
                key={notif.id}
                className={`notification-item${notif.read_at ? " read" : " unread"}`}
              >
                <div className="notification-content">
                  <p className="notification-title">{notif.title}</p>
                  <p className="notification-body">{notif.body}</p>
                  <span className="notification-time">{timeAgo(notif.created_at, t)}</span>
                </div>
                {!notif.read_at && (
                  <button
                    onClick={() => handleMarkRead(notif.id)}
                    className="notification-mark-read"
                    title={t("dashboard:notifications.markRead")}
                    aria-label={t("dashboard:notifications.markRead")}
                  >
                    <Check size={12} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};
