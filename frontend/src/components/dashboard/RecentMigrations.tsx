import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { migrationService, type RecentMigration } from "../../services/migration_service";
import { Play } from "lucide-react";

interface RecentMigrationsProps {
  limit?: number;
}

function formatTime(isoString: string, t: TFunction<['dashboard', 'common']>): string {
  const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 60_000);
  if (diff < 1) return t("common:time.now");
  if (diff < 60) return t("common:time.minutes", { count: diff });
  const h = Math.floor(diff / 60);
  if (h < 24) return t("common:time.hours", { count: h });
  return t("common:time.days", { count: Math.floor(h / 24) });
}

export const RecentMigrations: React.FC<RecentMigrationsProps> = ({
  limit = 5,
}) => {
  const { t } = useTranslation(["dashboard", "common"]);
  const [migrations, setMigrations] = useState<RecentMigration[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    migrationService
      .getRecentMigrations(limit)
      .then(setMigrations)
      .catch(() => setMigrations([]))
      .finally(() => setLoading(false));
  }, [limit]);

  if (loading) {
    return (
      <div className="dashboard-home__skeleton-block">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="dashboard-home__skeleton"
            style={{ width: i === 1 ? "90%" : "65%" }}
          />
        ))}
      </div>
    );
  }

  if (migrations.length === 0) {
    return (
      <div className="dashboard-home__placeholder">
        <Play size={22} className="dashboard-home__placeholder-icon" />
        <p>{t("dashboard:migrations.empty")}</p>
        <span>{t("dashboard:migrations.emptyHint")}</span>
      </div>
    );
  }

  return (
    <ul className="dashboard-home__list">
      {migrations.map((m) => (
        <li key={m.execution_id} className="dashboard-home__list-item">
          <div className="dashboard-home__list-item-main">
            <span className="dashboard-home__list-item-name">
              {m.project_name}
            </span>
            <span
              className={`dashboard-home__status-badge dashboard-home__status-badge--migration-${m.status}`}
            >
              {t(`dashboard:migrations.${m.status}`)}
            </span>
          </div>
          <span className="dashboard-home__list-item-meta">
            {formatTime(m.started_at, t)}
          </span>
        </li>
      ))}
    </ul>
  );
};
