// src/services/activity_service.ts
import { apiService } from "./api.service";

export interface Activity {
  id: string;
  project_id: string;
  user_id: string;
  user_email?: string;
  user_username?: string;
  activity_type: string;
  entity_type: string;
  entity_id: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface GroupedActivity {
  date: string;
  label: string;
  activities: Activity[];
}

export interface ActivityFilters {
  limit?: number;
  offset?: number;
  activity_type?: string;
  entity_id?: string;
  grouped?: boolean;
}

class ActivityService {
  private readonly BASE_PATH = "/api/activity";

  /**
   * Obtiene el feed de actividad de un proyecto
   */
  async getProjectActivity(
    projectId: string,
    filters?: ActivityFilters
  ): Promise<Activity[]> {
    const params = new URLSearchParams();

    if (filters?.limit) params.append('limit', filters.limit.toString());
    if (filters?.offset) params.append('offset', filters.offset.toString());
    if (filters?.activity_type) params.append('activity_type', filters.activity_type);
    if (filters?.entity_id) params.append('entity_id', filters.entity_id);
    if (filters?.grouped !== undefined) params.append('grouped', filters.grouped.toString());

    const queryString = params.toString();
    const endpoint = `${this.BASE_PATH}/projects/${projectId}${queryString ? '?' + queryString : ''}`;

    const response = await apiService.get<{ success: boolean; data: Activity[] }>(endpoint);

    if (!response.success || !response.data) {
      throw new Error("Error al obtener la actividad del proyecto");
    }

    return response.data;
  }

  /**
   * Obtiene actividad agrupada por fecha
   */
  async getGroupedActivity(
    projectId: string,
    filters?: Omit<ActivityFilters, 'grouped'>
  ): Promise<GroupedActivity[]> {
    const params = new URLSearchParams();
    params.append('grouped', 'true');

    if (filters?.limit) params.append('limit', filters.limit.toString());
    if (filters?.offset) params.append('offset', filters.offset.toString());
    if (filters?.activity_type) params.append('activity_type', filters.activity_type);
    if (filters?.entity_id) params.append('entity_id', filters.entity_id);

    const endpoint = `${this.BASE_PATH}/projects/${projectId}?${params.toString()}`;

    const response = await apiService.get<{ success: boolean; data: GroupedActivity[] }>(endpoint);

    if (!response.success || !response.data) {
      throw new Error("Error al obtener la actividad agrupada");
    }

    return response.data;
  }

  /**
   * Obtiene actividad de una entidad específica
   */
  async getEntityActivity(
    entityId: string,
    entityType: string,
    limit: number = 50
  ): Promise<Activity[]> {
    const params = new URLSearchParams({
      entity_type: entityType,
      limit: limit.toString()
    });

    const endpoint = `${this.BASE_PATH}/entity/${entityId}?${params.toString()}`;

    const response = await apiService.get<{ success: boolean; data: Activity[] }>(endpoint);

    if (!response.success || !response.data) {
      throw new Error("Error al obtener la actividad de la entidad");
    }

    return response.data;
  }

  async getGlobalActivity(filters?: ActivityFilters): Promise<Activity[]> {
    const params = new URLSearchParams();
    if (filters?.limit) params.append('limit', filters.limit.toString());
    if (filters?.offset) params.append('offset', filters.offset.toString());

    const queryString = params.toString();
    const endpoint = `${this.BASE_PATH}/global${queryString ? '?' + queryString : ''}`;

    const response = await apiService.get<{ success: boolean; data: Activity[] }>(endpoint);

    if (!response.success || !response.data) {
      throw new Error("Error al obtener la actividad global");
    }

    return response.data;
  }

  /**
   * Obtiene actividad de un usuario específico
   */
  async getUserActivity(
    userId: string,
    projectId?: string,
    limit: number = 50
  ): Promise<Activity[]> {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (projectId) params.append('project_id', projectId);

    const endpoint = `${this.BASE_PATH}/users/${userId}?${params.toString()}`;

    const response = await apiService.get<{ success: boolean; data: Activity[] }>(endpoint);

    if (!response.success || !response.data) {
      throw new Error("Error al obtener la actividad del usuario");
    }

    return response.data;
  }
}

export const activityService = new ActivityService();
export default ActivityService;
