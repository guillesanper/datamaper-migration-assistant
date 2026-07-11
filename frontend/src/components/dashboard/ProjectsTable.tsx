// src/components/dashboard/ProjectsTable.tsx

import React, { useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Plus,
  Download,
  Upload,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Loader2,
  Play,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '../ui/button';
import { ProjectRow } from './ProjectRow';
import { CreateProjectModal } from './modals/CreateProjectModal';
import { projectService } from '../../services/project_service';
import type { Project, CreateProjectDTO } from '../../types/project_types';

type SortField = 'name' | 'status' | 'progress' | 'budget' | 'updated_at';
type SortOrder = 'asc' | 'desc' | null;

export const ProjectsTable: React.FC = () => {
  const { t } = useTranslation('dashboard');

  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string>('');

  // Estado del modal
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Estado de filtros y ordenamiento
  const [sortField, setSortField] = useState<SortField | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOrder>(null);
  const [filterStatus, setFilterStatus] = useState<string>('all');

  const [searchParams] = useSearchParams();
  const migrateMode = searchParams.get('action') === 'migrate';

  /**
   * Carga inicial de proyectos y estadísticas
   */
  useEffect(() => {
    loadData();
  }, []);

  /**
   * Obtiene proyectos y estadísticas del servidor
   */
  const loadData = async () => {
    try {
      setIsLoading(true);
      setError('');
      
      const projectsData = await projectService.getProjects();
      setProjects(projectsData);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t('table.error'));
      console.error('Error loading data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Maneja el cambio de ordenamiento
   */
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      if (sortOrder === 'asc') {
        setSortOrder('desc');
      } else if (sortOrder === 'desc') {
        setSortOrder(null);
        setSortField(null);
      }
    } else {
      setSortField(field);
      setSortOrder('asc');
    }
  };

  /**
   * Maneja la creación de un nuevo proyecto
   */
  const handleCreateProject = async (data: CreateProjectDTO): Promise<{ id: string; name: string }> => {
    const project = await projectService.createProject(data);
    await loadData(); // Recargar todo incluyendo estadísticas
    return { id: project.id, name: project.name };
  };

  /**
   * Proyectos filtrados y ordenados
   */
  const sortedAndFilteredProjects = useMemo(() => {
    let filtered = [...projects];

    if (filterStatus !== 'all') {
      filtered = filtered.filter((p) => p.status === filterStatus);
    }

    if (sortField && sortOrder) {
      filtered.sort((a, b) => {
        let aValue = a[sortField];
        let bValue = b[sortField];

        if (sortField === 'updated_at' || sortField === 'name') {
          aValue = String(aValue);
          bValue = String(bValue);
        }

        if (aValue < bValue) return sortOrder === 'asc' ? -1 : 1;
        if (aValue > bValue) return sortOrder === 'asc' ? 1 : -1;
        return 0;
      });
    }

    return filtered;
  }, [projects, sortField, sortOrder, filterStatus]);

  /**
   * Obtiene el ícono de ordenamiento para una columna
   */
  const getSortIcon = (field: SortField) => {
    if (sortField !== field)
      return <ArrowUpDown size={14} className="ml-1" />;
    if (sortOrder === 'asc') return <ArrowUp size={14} className="ml-1" />;
    if (sortOrder === 'desc') return <ArrowDown size={14} className="ml-1" />;
    return <ArrowUpDown size={14} className="ml-1" />;
  };

  // Renderizar estado de carga
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={48} className="animate-spin text-primary" />
      </div>
    );
  }

  // Renderizar error
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-red-500 mb-4">{error}</p>
        <Button onClick={loadData}>{t('table.retry')}</Button>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      {migrateMode && (
        <div className="flex items-center gap-3 mb-4 px-4 py-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg text-green-800 dark:text-green-300 text-sm">
          <Play size={16} className="shrink-0" />
          <span>{t('table.migrateHint')}</span>
        </div>
      )}
      <div className="projects-header">
        <h1 className="projects-title">{t('table.title')}</h1>
        <Button variant="outline" size="default" onClick={() => setIsModalOpen(true)}>
          <Plus size={20} />
          <span className="hidden sm:inline ml-2">{t('table.newProject')}</span>
        </Button>
      </div>

      <div className="table-container">
        <div className="table-header">
          <div className="table-filters">
            <select
              className="filter-select"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
            >
              <option value="all">{t('table.filter.all')}</option>
              <option value="active">{t('table.filter.active')}</option>
              <option value="paused">{t('table.filter.paused')}</option>
              <option value="completed">{t('table.filter.completed')}</option>
            </select>
          </div>

          <div className="flex gap-2">
            <button className="btn-ghost" title={t('table.importTitle')}>
              <Upload size={16} />
            </button>
            <button className="btn-ghost" title={t('table.exportTitle')}>
              <Download size={16} />
            </button>
          </div>
        </div>

        {sortedAndFilteredProjects.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground">{t('table.empty')}</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="custom-table">
              <thead>
                <tr>
                  <th>
                    <button className="sort-button" onClick={() => handleSort('name')}>
                      {t('table.header.project')}
                      {getSortIcon('name')}
                    </button>
                  </th>
                  <th>
                    <button className="sort-button" onClick={() => handleSort('status')}>
                      {t('table.header.status')}
                      {getSortIcon('status')}
                    </button>
                  </th>
                  <th>{t('table.header.databases')}</th>
                  <th>
                    <button className="sort-button" onClick={() => handleSort('progress')}>
                      {t('table.header.progress')}
                      {getSortIcon('progress')}
                    </button>
                  </th>
                  <th>
                    <button className="sort-button" onClick={() => handleSort('budget')}>
                      {t('table.header.budget')}
                      {getSortIcon('budget')}
                    </button>
                  </th>
                  <th>
                    <button className="sort-button" onClick={() => handleSort('updated_at')}>
                      {t('table.header.updatedAt')}
                      {getSortIcon('updated_at')}
                    </button>
                  </th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sortedAndFilteredProjects.map((project) => (
                  <ProjectRow
                    key={project.id}
                    project={project}
                    onUpdate={loadData}
                    migrateMode={migrateMode}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal de creación */}
      <CreateProjectModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => {
          console.log('Proyecto creado exitosamente');
        }}
        onSubmit={handleCreateProject}
      />
    </div>
  );
};