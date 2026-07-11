// src/services/version_control/activity.service.ts

import { apiService } from '../api.service';
import type {
  Activity,
  ActivityResponse,
  ActivityFilters,
  GroupedActivity
} from '@/types/activity_types';

/**
 * Servicio para gestión del feed de actividad
 * REUTILIZA: apiService existente
 */
class ActivityService {
  private readonly BASE_PATH = '/api/activity';

  /**
   * Obtiene el feed de actividad de un proyecto
   */
  async getProjectActivity(projectId: string, filters?: ActivityFilters): Promise<Activity[]> {
    try {
      const params = new URLSearchParams();
      params.append('project_id', projectId);

      if (filters?.user_id) params.append('user_id', filters.user_id);
      if (filters?.activity_type?.length) {
        params.append('activity_type', filters.activity_type.join(','));
      }
      if (filters?.entity_id) params.append('entity_id', filters.entity_id);
      if (filters?.entity_type) params.append('entity_type', filters.entity_type);
      if (filters?.date_from) params.append('date_from', filters.date_from);
      if (filters?.date_to) params.append('date_to', filters.date_to);
      if (filters?.limit) params.append('limit', filters.limit.toString());
      if (filters?.offset) params.append('offset', filters.offset.toString());

      const response = await apiService.get<ActivityResponse>(
        `${this.BASE_PATH}?${params.toString()}`
      );

      if (!response.success || !response.data?.activities) {
        throw new Error(response.message || 'Error al obtener actividad');
      }

      return response.data.activities;
    } catch (error: unknown) {
      console.error('[ActivityService] Error getting activity:', error);
      throw error;
    }
  }

  /**
   * Obtiene actividad agrupada (para mostrar "Usuario hizo 5 cambios")
   */
  async getGroupedActivity(projectId: string, filters?: ActivityFilters): Promise<GroupedActivity[]> {
    try {
      const params = new URLSearchParams();
      params.append('project_id', projectId);
      params.append('grouped', 'true');

      if (filters?.user_id) params.append('user_id', filters.user_id);
      if (filters?.activity_type?.length) {
        params.append('activity_type', filters.activity_type.join(','));
      }
      if (filters?.date_from) params.append('date_from', filters.date_from);
      if (filters?.date_to) params.append('date_to', filters.date_to);

      const response = await apiService.get<ActivityResponse>(
        `${this.BASE_PATH}/grouped?${params.toString()}`
      );

      if (!response.success || !response.data?.grouped) {
        throw new Error(response.message || 'Error al obtener actividad agrupada');
      }

      return response.data.grouped;
    } catch (error: unknown) {
      console.error('[ActivityService] Error getting grouped activity:', error);
      throw error;
    }
  }

  /**
   * Obtiene actividad de una entidad específica
   */
  async getEntityActivity(entityId: string, entityType: string): Promise<Activity[]> {
    try {
      const response = await apiService.get<ActivityResponse>(
        `${this.BASE_PATH}/entity/${entityType}/${entityId}`
      );

      if (!response.success || !response.data?.activities) {
        throw new Error(response.message || 'Error al obtener actividad de entidad');
      }

      return response.data.activities;
    } catch (error: unknown) {
      console.error('[ActivityService] Error getting entity activity:', error);
      throw error;
    }
  }
}

// Exportar instancia singleton
export const activityService = new ActivityService();
export default ActivityService;
