// src/pages/Dashboard.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Plus, Play, Database, Activity, FolderOpen } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../providers/AuthProvider';
import { StatCard } from '../components/dashboard/StatCard';
import { CreateProjectModal } from '../components/dashboard/modals/CreateProjectModal';
import { ActivityFeed } from '../components/team/ActivityFeed';
import { ProjectsTable } from '../components/dashboard/ProjectsTable';
import { projectService } from '../services/project_service';
import { RecentMigrations } from '../components/dashboard/RecentMigrations';
import { RecentVersions } from '../components/dashboard/RecentVersions';
import type { Project, ProjectStats, FormattedStat, CreateProjectDTO } from '../types/project_types';

// ─── Custom Hook ───────────────────────────────────────────────────────────────

interface DashboardState {
  stats: ProjectStats | null;
  recentProjects: Project[];
  loadingStats: boolean;
  loadingProjects: boolean;
}

function useDashboardData(): DashboardState & { reload: () => void } {
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [recentProjects, setRecentProjects] = useState<Project[]>([]);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingProjects, setLoadingProjects] = useState(true);

  const load = useCallback(async () => {
    setLoadingStats(true);
    setLoadingProjects(true);

    const [statsResult, projectsResult] = await Promise.allSettled([
      projectService.getProjectStats(),
      projectService.getRecentProjects(5),
    ]);

    if (statsResult.status === 'fulfilled') {
      setStats(statsResult.value);
    } else {
      console.error('Error loading stats:', statsResult.reason);
    }
    setLoadingStats(false);

    if (projectsResult.status === 'fulfilled') {
      setRecentProjects(projectsResult.value);
    } else {
      console.error('Error loading recent projects:', projectsResult.reason);
    }
    setLoadingProjects(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { stats, recentProjects, loadingStats, loadingProjects, reload: load };
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

type TFn = (key: string, options?: Record<string, unknown>) => string;

function formatLastAccessed(dateStr: string | null | undefined, t: TFn, language: string): string {
  if (!dateStr) return t('recent.projects.neverAccessed');
  const date = new Date(dateStr);
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days = Math.floor(diff / 86_400_000);
  if (minutes < 1) return t('common:time.now');
  if (minutes < 60) return t('common:time.minutes', { count: minutes });
  if (hours < 24) return t('common:time.hours', { count: hours });
  if (days < 7) return t('common:time.days', { count: days });
  return date.toLocaleDateString(language === 'es' ? 'es-ES' : 'en-US', { day: 'numeric', month: 'short' });
}

function buildFormattedStats(stats: ProjectStats, t: TFn): FormattedStat[] {
  const fmtBudget = (n: number) =>
    n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M`
    : n >= 1_000   ? `$${(n / 1_000).toFixed(1)}K`
    : `$${n}`;

  return [
    {
      label: t('stats.totalProjects'),
      value: stats.total_projects.value,
      change: `${Math.abs(stats.total_projects.change)}%`,
      positive: stats.total_projects.positive,
    },
    {
      label: t('stats.activeProjects'),
      value: stats.active_projects.value,
      change: `${Math.abs(stats.active_projects.change)}%`,
      positive: stats.active_projects.positive,
    },
    {
      label: t('stats.totalBudget'),
      value: fmtBudget(stats.total_budget.value),
      change: `${Math.abs(stats.total_budget.change)}%`,
      positive: stats.total_budget.positive,
    },
    {
      label: t('stats.completed'),
      value: stats.completed_projects.value,
      change: `${Math.abs(stats.completed_projects.change)}%`,
      positive: stats.completed_projects.positive,
    },
  ];
}

// ─── Sub-components ────────────────────────────────────────────────────────────

const SkeletonLines: React.FC<{ count?: number }> = ({ count = 3 }) => (
  <div className="dashboard-home__skeleton-block">
    {Array.from({ length: count }).map((_, i) => (
      <div
        key={i}
        className="dashboard-home__skeleton"
        style={{ width: i === 0 ? '60%' : i === 1 ? '90%' : '45%' }}
      />
    ))}
  </div>
);

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const { t } = useTranslation('dashboard');
  const labels: Record<string, string> = {
    active: t('projectRow.status.active'),
    paused: t('projectRow.status.paused'),
    completed: t('projectRow.status.completed'),
  };
  return (
    <span className={`dashboard-home__status-badge dashboard-home__status-badge--${status}`}>
      {labels[status] ?? status}
    </span>
  );
};

// ─── Dashboard Home ────────────────────────────────────────────────────────────

const DashboardHome: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { stats, recentProjects, loadingStats, loadingProjects, reload } = useDashboardData();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const { t, i18n } = useTranslation(['dashboard', 'common']);

  const username = user?.username || user?.email?.split('@')[0] || 'usuario';

  const hour = new Date().getHours();
  const greeting = hour < 12
    ? t('greeting.morning', { name: username })
    : hour < 18
    ? t('greeting.afternoon', { name: username })
    : t('greeting.evening', { name: username });

  const locale = i18n.language === 'es' ? 'es-ES' : 'en-US';
  const today = new Date().toLocaleDateString(locale, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tFn = t as unknown as TFn;
  const formattedStats = stats ? buildFormattedStats(stats, tFn) : null;

  const handleCreateProject = async (data: CreateProjectDTO): Promise<{ id: string; name: string }> => {
    const project = await projectService.createProject(data);
    reload();
    return { id: project.id, name: project.name };
  };

  return (
    <div className="dashboard-home animate-fade-in">

      {/* ── OVERVIEW ──────────────────────────────────────────── */}
      <section className="dashboard-home__overview">
        <div className="dashboard-home__greeting">
          <h1 className="dashboard-home__greeting-title">{greeting}</h1>
          <p className="dashboard-home__greeting-date">{today}</p>
        </div>

        <div className="dashboard-home__stats-grid">
          {loadingStats
            ? Array.from({ length: 4 }).map((_, i) => <SkeletonLines key={i} count={3} />)
            : formattedStats?.map((stat) => <StatCard key={stat.label} {...stat} />)}
        </div>
      </section>

      {/* ── MAIN GRID (Left col | Activity) ──────────────────── */}
      <div className="dashboard-home__grid-main">

        {/* ── COLUMNA IZQUIERDA: Recientes + Quick Actions ────── */}
        <div className="dashboard-home__left-col">

          {/* ── RECENTS ─────────────────────────────────────────── */}
          <section className="dashboard-home__section">
            <h2 className="dashboard-home__section-title">
              <FolderOpen size={18} />
              {t('sections.recent')}
            </h2>

            <div className="dashboard-home__recents-grid">

              {/* Proyectos recientes */}
              <div className="dashboard-home__recent-card">
                <h3 className="dashboard-home__recent-card-title">{t('recent.projects.title')}</h3>
                {loadingProjects ? (
                  <SkeletonLines count={5} />
                ) : recentProjects.length === 0 ? (
                  <p className="dashboard-home__empty">{t('recent.projects.empty')}</p>
                ) : (
                  <ul className="dashboard-home__list">
                    {recentProjects.map((p) => (
                      <li
                        key={p.id}
                        className="dashboard-home__list-item"
                        onClick={() => navigate(`/projects/${p.id}/mapping`)}
                      >
                        <div className="dashboard-home__list-item-main">
                          <span className="dashboard-home__list-item-name">{p.name}</span>
                          <StatusBadge status={p.status} />
                        </div>
                        <span className="dashboard-home__list-item-meta">
                          {formatLastAccessed(p.last_accessed_at, tFn, i18n.language)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Migraciones recientes */}
              <div className="dashboard-home__recent-card">
                <h3 className="dashboard-home__recent-card-title">{t('recent.migrations.title')}</h3>
                <RecentMigrations limit={5} />
              </div>

              {/* Versiones recientes */}
              <div className="dashboard-home__recent-card">
                <h3 className="dashboard-home__recent-card-title">{t('recent.versions.title')}</h3>
                <RecentVersions limit={5} />
              </div>

            </div>
          </section>

          {/* ── QUICK ACTIONS ─────────────────────────────────── */}
          <section className="dashboard-home__quick-actions">
            <button
              className="dashboard-home__quick-action-btn"
              onClick={() => setIsModalOpen(true)}
            >
              <Plus size={28} />
              <span className="dashboard-home__quick-action-label">{t('quickActions.createProject')}</span>
              <span className="dashboard-home__quick-action-sub">{t('quickActions.createProjectSub')}</span>
            </button>

            <button
              className="dashboard-home__quick-action-btn"
              onClick={() => navigate('/projects?action=migrate')}
            >
              <Play size={28} />
              <span className="dashboard-home__quick-action-label">{t('quickActions.newMigration')}</span>
              <span className="dashboard-home__quick-action-sub">{t('quickActions.newMigrationSub')}</span>
            </button>

            <button
              className="dashboard-home__quick-action-btn"
              onClick={() => navigate('/settings')}
            >
              <Database size={28} />
              <span className="dashboard-home__quick-action-label">{t('quickActions.addDbConnection')}</span>
              <span className="dashboard-home__quick-action-sub">{t('quickActions.addDbConnectionSub')}</span>
            </button>
          </section>

        </div>

        {/* ── ACTIVITY & SOCIAL ───────────────────────────────── */}
        <section className="dashboard-home__section">
          <h2 className="dashboard-home__section-title">
            <Activity size={18} />
            {t('sections.activitySocial')}
          </h2>

          <ActivityFeed limit={8} />
        </section>

      </div>

      <CreateProjectModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => { /* handled by reload in handleCreateProject */ }}
        onSubmit={handleCreateProject}
      />
    </div>
  );
};

// ─── Export ────────────────────────────────────────────────────────────────────
// /projects sigue mostrando la tabla completa; /dashboard muestra el home.

export const Dashboard: React.FC = () => {
  const { pathname } = useLocation();
  if (pathname === '/projects') {
    return <ProjectsTable />;
  }
  return <DashboardHome />;
};
