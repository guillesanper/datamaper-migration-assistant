import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { versionService, type RecentVersion } from "../../services/version_service";
import { Database } from "lucide-react";

interface RecentVersionsProps {
  limit?: number;
}

const CHANGE_TYPE_KEYS: Record<string, string> = {
  create: "created",
  update: "updated",
  delete: "deleted",
  rename: "renamed",
  add: "added",
  remove: "deleted",
};

function formatTime(isoString: string, t: TFunction<['dashboard', 'common']>): string {
  const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 60_000);
  if (diff < 1) return t("common:time.now");
  if (diff < 60) return t("common:time.minutes", { count: diff });
  const h = Math.floor(diff / 60);
  if (h < 24) return t("common:time.hours", { count: h });
  return t("common:time.days", { count: Math.floor(h / 24) });
}

export const RecentVersions: React.FC<RecentVersionsProps> = ({
  limit = 5,
}) => {
  const { t } = useTranslation(["dashboard", "common"]);
  const [versions, setVersions] = useState<RecentVersion[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    versionService
      .getRecentVersions(limit)
      .then(setVersions)
      .catch(() => setVersions([]))
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

  if (versions.length === 0) {
    return (
      <div className="dashboard-home__placeholder">
        <Database size={22} className="dashboard-home__placeholder-icon" />
        <p>{t("dashboard:versions.empty")}</p>
        <span>{t("dashboard:versions.emptyHint")}</span>
      </div>
    );
  }

  return (
    <ul className="dashboard-home__list">
      {versions.map((v) => (
        <li key={v.id} className="dashboard-home__list-item">
          <div className="dashboard-home__list-item-main">
            <span className="dashboard-home__list-item-name">
              {v.project_name}
            </span>
            <span className="dashboard-home__status-badge dashboard-home__status-badge--version">
              {t(`dashboard:versions.entity.${v.entity_type}`, { defaultValue: v.entity_type })}{" "}
              {t(`dashboard:versions.${CHANGE_TYPE_KEYS[v.change_type] ?? v.change_type}`, { defaultValue: v.change_type })}
            </span>
          </div>
          {v.message && (
            <span className="dashboard-home__list-item-sub">{v.message}</span>
          )}
          <span className="dashboard-home__list-item-meta">
            {formatTime(v.created_at, t)}
          </span>
        </li>
      ))}
    </ul>
  );
};
