// src/hooks/version_control/useVersionControl.ts

import { useState, useCallback, useEffect } from 'react';
import { versionControlService } from '@/services/version_control';
import type {
  Version,
  CreateVersionRequest,
  VersionFilters,
  Tag,
  CreateTagRequest,
  EntityType
} from '@/types/versioning_types';

/**
 * Hook para gestión de versiones de una entidad
 * REUTILIZA: Patrón de hooks del proyecto (similar a useAuth)
 */
export const useVersionControl = (entityId: string, entityType?: EntityType) => {
  const [versions, setVersions] = useState<Version[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Carga el historial de versiones
   */
  const loadVersions = useCallback(async (filters?: VersionFilters) => {
    setLoading(true);
    setError(null);

    try {
      const data = await versionControlService.getVersionHistory(entityId, filters);
      setVersions(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al cargar versiones');
      console.error('[useVersionControl] Load error:', err);
    } finally {
      setLoading(false);
    }
  }, [entityId]);

  /**
   * Crea una nueva versión
   */
  const createVersion = useCallback(async (
    snapshot: object,
    changeType: 'create' | 'update' | 'delete',
    message?: string
  ): Promise<Version | null> => {
    if (!entityType) {
      setError('Entity type is required to create version');
      return null;
    }

    setLoading(true);
    setError(null);

    try {
      const request: CreateVersionRequest = {
        entity_id: entityId,
        entity_type: entityType,
        change_type: changeType,
        message,
        snapshot
      };

      const newVersion = await versionControlService.createVersion(request);

      // Agregar a la lista local (optimistic update)
      setVersions(prev => [newVersion, ...prev]);

      return newVersion;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al crear versión');
      console.error('[useVersionControl] Create error:', err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [entityId, entityType]);

  /**
   * Restaura una versión anterior
   */
  const restoreVersion = useCallback(async (
    versionId: string,
    createBackup: boolean = true,
    message?: string
  ): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      await versionControlService.restoreVersion(versionId, createBackup, message);
      // Recargar versiones después de restaurar
      await loadVersions();
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al restaurar versión');
      console.error('[useVersionControl] Restore error:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [loadVersions]);

  /**
   * Compara dos versiones
   */
  const compareVersions = useCallback(async (versionAId: string, versionBId: string) => {
    setLoading(true);
    setError(null);

    try {
      const diff = await versionControlService.compareVersions(versionAId, versionBId);
      return diff;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al comparar versiones');
      console.error('[useVersionControl] Compare error:', err);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Crea un tag
   */
  const createTag = useCallback(async (data: CreateTagRequest): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      const newTag = await versionControlService.createTag(data);
      setTags(prev => [...prev, newTag]);
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al crear tag');
      console.error('[useVersionControl] Create tag error:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Elimina un tag
   */
  const deleteTag = useCallback(async (tagId: string): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      await versionControlService.deleteTag(tagId);
      setTags(prev => prev.filter(t => t.id !== tagId));
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error al eliminar tag');
      console.error('[useVersionControl] Delete tag error:', err);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Limpia el error
   */
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Cargar versiones al montar
  useEffect(() => {
    if (entityId) {
      loadVersions();
    }
  }, [entityId, loadVersions]);

  return {
    versions,
    tags,
    loading,
    error,
    loadVersions,
    createVersion,
    restoreVersion,
    compareVersions,
    createTag,
    deleteTag,
    clearError
  };
};

export default useVersionControl;
