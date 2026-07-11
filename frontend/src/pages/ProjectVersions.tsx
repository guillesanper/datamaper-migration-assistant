// src/pages/ProjectVersions.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { History, X, ArrowLeft, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/button';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import {
  VersionHistory,
  VersionCompare,
  VersionFilters,
  VersionStats,
  HelpGuide
} from '../components/version_control';
import { versionControlService } from '../services/version_control';
import { projectService } from '../services/project_service';
import type {
  Version,
  VersionFilters as VersionFiltersType,
  Tag
} from '../types/version_control_types';
import type { Project } from '../types/project_types';
import { toast } from '../utils/toast';
import styles from '../styles/version_control/project-versions.module.css';

/**
 * ProjectVersions - Dedicated page for project version control
 *
 * Features:
 * - Complete version history of the project
 * - Advanced filtering
 * - Version comparison
 * - Tag management
 * - Statistics dashboard
 */
export const ProjectVersions: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<Project | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [filteredVersions, setFilteredVersions] = useState<Version[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [filters, setFilters] = useState<VersionFiltersType>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Comparison state
  const [compareData, setCompareData] = useState<{
    versionA: Version;
    versionB: Version;
  } | null>(null);

  /**
   * Load project data
   */
  const loadProject = useCallback(async () => {
    if (!projectId) return;

    try {
      const projectData = await projectService.getProjectById(projectId);
      setProject(projectData);
    } catch (error) {
      console.error('Error loading project:', error);
      toast.error('Error al cargar proyecto');
    }
  }, [projectId]);

  /**
   * Load versions and tags
   */
  const loadData = useCallback(async (showLoader = true) => {
    if (!projectId) return;

    try {
      if (showLoader) setLoading(true);
      else setRefreshing(true);

      const [versionsData, tagsData] = await Promise.all([
        versionControlService.getProjectVersions(projectId),
        versionControlService.getTags(projectId)
      ]);

      setVersions(versionsData);
      setFilteredVersions(versionsData);
      setTags(tagsData);
    } catch (error) {
      console.error('Error loading data:', error);
      toast.error('Error al cargar historial');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [projectId]);

  /**
   * Apply filters to versions
   */
  const applyFilters = useCallback(() => {
    let filtered = [...versions];

    // Search term
    if (filters.search_term) {
      const term = filters.search_term.toLowerCase();
      filtered = filtered.filter(v =>
        v.message?.toLowerCase().includes(term) ||
        v.username.toLowerCase().includes(term)
      );
    }

    // User filter
    if (filters.user_id) {
      filtered = filtered.filter(v => v.user_id === filters.user_id);
    }

    // Change type filter
    if (filters.change_type && filters.change_type.length > 0) {
      filtered = filtered.filter(v => filters.change_type!.includes(v.change_type));
    }

    // Entity type filter
    if (filters.entity_type) {
      filtered = filtered.filter(v => v.entity_type === filters.entity_type);
    }

    // Date range
    if (filters.date_from) {
      const fromDate = new Date(filters.date_from);
      filtered = filtered.filter(v => new Date(v.created_at) >= fromDate);
    }

    if (filters.date_to) {
      const toDate = new Date(filters.date_to);
      toDate.setHours(23, 59, 59, 999);
      filtered = filtered.filter(v => new Date(v.created_at) <= toDate);
    }

    // Tags filter
    if (filters.tags && filters.tags.length > 0) {
      filtered = filtered.filter(v =>
        v.tags?.some(t => filters.tags!.includes(t.id))
      );
    }

    setFilteredVersions(filtered);
  }, [versions, filters]);

  /**
   * Handle version comparison
   */
  const handleCompare = useCallback((versionA: Version, versionB: Version) => {
    setCompareData({ versionA, versionB });
  }, []);

  /**
   * Handle version restore
   */
  const handleRestore = useCallback(async (version: Version) => {
    try {
      await versionControlService.restoreVersion(version.id, true);
      toast.success(`Versión ${version.version_number} restaurada`);
      await loadData(false);
    } catch (error) {
      console.error('Error restoring version:', error);
      toast.error('Error al restaurar versión');
    }
  }, [loadData]);


  // Load data on mount
  useEffect(() => {
    loadProject();
    loadData();
  }, [loadProject, loadData]);

  // Apply filters when versions or filters change
  useEffect(() => {
    applyFilters();
  }, [versions, filters]); // eslint-disable-line react-hooks/exhaustive-deps

  // Get unique users for filter
  const availableUsers = Array.from(
    new Set(versions.map(v => ({ id: v.user_id, name: v.username })))
  ).map(u => ({ id: u.id, name: u.name }));

  if (loading) {
    return (
      <div className={styles.pageContainer}>
        <div className={styles.loadingState}>
          <LoadingSpinner size="lg" />
          <span>Cargando historial...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.pageContainer}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerTop}>
          <div className={styles.headerTitle}>
            <Button
              size="icon-sm"
              variant="ghost"
              onClick={() => navigate(`/projects/${projectId}/mapping`)}
            >
              <ArrowLeft size={20} />
            </Button>
            <History size={28} />
            <h1>Control de Versiones</h1>
            <span className={styles.headerSubtitle}>
              {project?.name || 'Proyecto'}
            </span>
          </div>

          <div className={styles.headerActions}>
            <HelpGuide />
            <Button
              size="sm"
              variant="outline"
              onClick={() => loadData(false)}
              disabled={refreshing}
            >
              <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
              Actualizar
            </Button>
          </div>
        </div>

      </div>

      {/* Content */}
      <div className={styles.content}>
        {/* Main Panel - Filters & Timeline */}
        <div className={styles.mainPanel}>
          {/* Filters */}
          <div className={styles.filtersSection}>
            <VersionFilters
              filters={filters}
              onFiltersChange={setFilters}
              availableUsers={availableUsers}
              availableTags={tags.map(t => ({ id: t.id, name: t.name }))}
              onReset={() => setFilters({})}
            />
          </div>

          {/* Timeline */}
          <div className={styles.timelineSection}>
            <div className={styles.timelineHeader}>
              <span className={styles.timelineTitle}>
                <History size={18} />
                Historial de versiones
              </span>
              <span className={styles.timelineCount}>
                {filteredVersions.length} versión{filteredVersions.length !== 1 ? 'es' : ''}
              </span>
            </div>

            <div className={styles.timelineContent}>
              {filteredVersions.length === 0 ? (
                <div className={styles.emptyState}>
                  <History size={48} />
                  <h3>No se encontraron versiones</h3>
                  <p>
                    {Object.keys(filters).length > 0
                      ? 'Intenta ajustar los filtros'
                      : 'Aún no hay versiones en este proyecto'}
                  </p>
                </div>
              ) : (
                <VersionHistory
                  versions={filteredVersions}
                  onCompare={handleCompare}
                  onRestore={handleRestore}
                  canRestore={true}
                  canDelete={false}
                />
              )}
            </div>
          </div>
        </div>

        {/* Side Panel - Stats */}
        <div className={styles.sidePanel}>
          <div className={styles.statsPanel}>
            <VersionStats versions={filteredVersions} tags={tags} projectId={projectId!} />
          </div>
        </div>
      </div>

      {/* Compare Modal */}
      {compareData && (
        <div
          className={styles.compareOverlay}
          onClick={() => setCompareData(null)}
        >
          <div
            className={styles.compareModal}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.compareModalHeader}>
              <h2 className={styles.compareModalTitle}>
                Comparar versiones {compareData.versionA.version_number} y{' '}
                {compareData.versionB.version_number}
              </h2>
              <Button
                size="icon-sm"
                variant="ghost"
                onClick={() => setCompareData(null)}
              >
                <X size={20} />
              </Button>
            </div>

            <div className={styles.compareModalContent}>
              <VersionCompare
                versionA={compareData.versionA}
                versionB={compareData.versionB}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjectVersions;
