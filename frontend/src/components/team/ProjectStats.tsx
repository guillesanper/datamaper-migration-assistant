// src/components/team/ProjectStats.tsx
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Database, GitBranch, TrendingUp, Calendar } from 'lucide-react';
import type { Project } from '../../types/project_types';

interface ProjectStatsProps {
  project: Project;
}

export const ProjectStats: React.FC<ProjectStatsProps> = ({ project }) => {
  const { t, i18n } = useTranslation(['team', 'common']);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString(i18n.language === 'es' ? 'es-ES' : 'en-US', {
      day: 'numeric',
      month: 'long',
      year: 'numeric'
    });
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      active: 'bg-green-500/10 text-green-700 dark:text-green-400',
      paused: 'bg-yellow-500/10 text-yellow-700 dark:text-yellow-400',
      completed: 'bg-blue-500/10 text-blue-700 dark:text-blue-400'
    };
    return colors[status] || 'bg-gray-500/10 text-gray-700';
  };

  const statusLabels: Record<string, string> = {
    active: t('common:status.active'),
    paused: t('common:status.paused'),
    completed: t('common:status.completed'),
  };

  return (
    <div className="bg-card border rounded-lg p-6 space-y-4">
      {/* Título y descripción */}
      <div>
        <h2 className="text-xl font-semibold mb-1">{project.name}</h2>
        {project.description && (
          <p className="text-sm text-muted-foreground">{project.description}</p>
        )}
      </div>

      {/* Grid de estadísticas */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Base de datos origen */}
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Database className="w-4 h-4" />
            <span className="text-xs font-medium">{t('team:projectInfo.origin')}</span>
          </div>
          <p className="font-medium text-sm truncate" title={project.origin_db}>
            {project.origin_db}
          </p>
        </div>

        {/* Base de datos destino */}
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-muted-foreground">
            <GitBranch className="w-4 h-4" />
            <span className="text-xs font-medium">{t('team:projectInfo.destination')}</span>
          </div>
          <p className="font-medium text-sm truncate" title={project.destination_db}>
            {project.destination_db}
          </p>
        </div>

        {/* Progreso */}
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-muted-foreground">
            <TrendingUp className="w-4 h-4" />
            <span className="text-xs font-medium">{t('team:projectInfo.progress')}</span>
          </div>
          <div className="space-y-1">
            <p className="font-medium text-sm">{project.progress}%</p>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${project.progress}%` }}
              />
            </div>
          </div>
        </div>

        {/* Estado */}
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Calendar className="w-4 h-4" />
            <span className="text-xs font-medium">{t('team:projectInfo.status')}</span>
          </div>
          <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(project.status)}`}>
            {statusLabels[project.status] ?? project.status}
          </span>
        </div>
      </div>

      {/* Fechas */}
      <div className="pt-4 border-t grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-muted-foreground">{t('team:projectInfo.createdAt')}</span>{' '}
          <span className="font-medium">{formatDate(project.created_at)}</span>
        </div>
        <div>
          <span className="text-muted-foreground">{t('team:projectInfo.updatedAt')}</span>{' '}
          <span className="font-medium">{formatDate(project.updated_at)}</span>
        </div>
      </div>
    </div>
  );
};
