// src/services/version_control/versionControl.service.ts

import { apiService } from '../api.service';
import type {
  Version,
  VersionResponse,
  CreateVersionRequest,
  VersionFilters,
  VersionDiff,
  RestoreVersionRequest,
  Tag,
  CreateTagRequest
} from '@/types/versioning_types';
import { createSnapshot, generateVersionHash } from '@/utils/version_control/versionUtils';

/**
 * Servicio para gestión de versiones
 * REUTILIZA: apiService existente con interceptores
 */
class VersionControlService {
  private readonly BASE_PATH = '/api/versions';

  /**
   * Crea una nueva versión de una entidad
   */
  async createVersion(data: CreateVersionRequest): Promise<Version> {
    try {
      // Crear snapshot y hash
      const snapshot = createSnapshot(data.snapshot);
      const hash = generateVersionHash(data.snapshot);

      const response = await apiService.post<VersionResponse>(this.BASE_PATH, {
        entity_id: data.entity_id,
        entity_type: data.entity_type,
        change_type: data.change_type,
        message: data.message || '',
        snapshot,
        hash
      });

      if (!response.success || !response.data?.version) {
        throw new Error(response.message || 'Error al crear versión');
      }

      return response.data.version;
    } catch (error: unknown) {
      console.error('[VersionControlService] Error creating version:', error);
      throw error;
    }
  }

  /**
   * Obtiene el historial de versiones de una entidad
   */
  async getVersionHistory(entityId: string, filters?: VersionFilters): Promise<Version[]> {
    try {
      const params = new URLSearchParams();
      params.append('entity_id', entityId);

      if (filters?.user_id) params.append('user_id', filters.user_id);
      if (filters?.change_type?.length) params.append('change_type', filters.change_type.join(','));
      if (filters?.date_from) params.append('date_from', filters.date_from);
      if (filters?.date_to) params.append('date_to', filters.date_to);
      if (filters?.entity_type) params.append('entity_type', filters.entity_type);
      if (filters?.search_term) params.append('search', filters.search_term);
      if (filters?.tags?.length) params.append('tags', filters.tags.join(','));
      if (filters?.limit) params.append('limit', filters.limit.toString());
      if (filters?.offset) params.append('offset', filters.offset.toString());

      const response = await apiService.get<VersionResponse>(
        `${this.BASE_PATH}?${params.toString()}`
      );

      if (!response.success || !response.data?.versions) {
        throw new Error(response.message || 'Error al obtener historial');
      }

      return response.data.versions;
    } catch (error: unknown) {
      console.error('[VersionControlService] Error getting history:', error);
      throw error;
    }
  }

  /**
   * Obtiene una versión específica por ID
   */
  async getVersionById(versionId: string): Promise<Version> {
    try {
      const response = await apiService.get<VersionResponse>(
        `${this.BASE_PATH}/${versionId}`
      );

      if (!response.success || !response.data?.version) {
        throw new Error(response.message || 'Error al obtener versión');
      }

      return response.data.version;
    } catch (error: unknown) {
      console.error('[VersionControlService] Error getting version:', error);
      throw error;
    }
  }

  /**
   * Compara dos versiones
   */
  async compareVersions(versionAId: string, versionBId: string): Promise<VersionDiff> {
    try {
      const params = new URLSearchParams();
      params.append('version_a_id', versionAId);
      params.append('version_b_id', versionBId);

      const response = await apiService.get<VersionResponse>(
        `${this.BASE_PATH}/compare?${params.toString()}`
      );

      if (!response.success || !response.data?.diff) {
        throw new Error(response.message || 'Error al comparar versiones');
      }

      return response.data.diff;
    } catch (error: unknown) {
      console.error('[VersionControlService] Error comparing versions:', error);
      throw error;
    }
  }

  /**
   * Restaura una versión anterior
   */
  async restoreVersion(
    versionId: string,
    createBackup: boolean = true,
    message?: string
  ): Promise<Version> {
    try {
      const response = await apiService.post<VersionResponse>(
        `${this.BASE_PATH}/${versionId}/restore`,
        {
          create_backup: createBackup,
          message: message || 'Versión restaurada'
        } as RestoreVersionRequest
      );

      if (!response.success || !response.data?.version) {
        throw new Error(response.message || 'Error al restaurar versión');
      }

      return response.data.version;
    } catch (error: unknown) {
      console.error('[VersionControlService] Error restoring version:', error);
      throw error;
    }
  }

  /**
   * Crea un tag en una versión
   */
  async createTag(data: CreateTagRequest): Promise<Tag> {
    try {
      const response = await apiService.post<VersionResponse>(
        `${this.BASE_PATH}/tags`,
        data
      );

      if (!response.success || !response.data?.tag) {
        throw new Error(response.message || 'Error al crear tag');
      }

      return response.data.tag;
    } catch (error: unknown) {
      console.error('[VersionControlService] Error creating tag:', error);
      throw error;
    }
  }

  /**
   * Obtiene todos los tags de un proyecto
   */
  async getTags(projectId: string): Promise<Tag[]> {
    try {
      const response = await apiService.get<VersionResponse>(
        `${this.BASE_PATH}/projects/${projectId}/tags`
      );

      if (!response.success || !response.data?.tags) {
        throw new Error(response.message || 'Error al obtener tags');
      }

      return response.data.tags;
    } catch (error: unknown) {
      console.error('[VersionControlService] Error getting tags:', error);
      throw error;
    }
  }

  /**
   * Elimina un tag
   */
  async deleteTag(tagId: string): Promise<void> {
    try {
      const response = await apiService.delete<VersionResponse>(
        `${this.BASE_PATH}/tags/${tagId}`
      );

      if (!response.success) {
        throw new Error(response.message || 'Error al eliminar tag');
      }
    } catch (error: unknown) {
      console.error('[VersionControlService] Error deleting tag:', error);
      throw error;
    }
  }

  /**
   * Obtiene versiones de un proyecto completo
   */
  async getProjectVersions(projectId: string, filters?: VersionFilters): Promise<Version[]> {
    try {
      const params = new URLSearchParams();

      if (filters?.user_id) params.append('user_id', filters.user_id);
      if (filters?.change_type?.length) params.append('change_type', filters.change_type.join(','));
      if (filters?.date_from) params.append('date_from', filters.date_from);
      if (filters?.date_to) params.append('date_to', filters.date_to);
      if (filters?.entity_type) params.append('entity_type', filters.entity_type);
      if (filters?.limit) params.append('limit', filters.limit.toString());
      if (filters?.offset) params.append('offset', filters.offset.toString());

      const queryString = params.toString();
      const url = queryString
        ? `${this.BASE_PATH}/projects/${projectId}?${queryString}`
        : `${this.BASE_PATH}/projects/${projectId}`;

      const response = await apiService.get<VersionResponse>(url);

      if (!response.success || !response.data?.versions) {
        throw new Error(response.message || 'Error al obtener versiones del proyecto');
      }

      return response.data.versions;
    } catch (error: unknown) {
      console.error('[VersionControlService] Error getting project versions:', error);
      throw error;
    }
  }
}

// Exportar instancia singleton
export const versionControlService = new VersionControlService();
export default VersionControlService;
