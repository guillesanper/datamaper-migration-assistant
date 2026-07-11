// src/services/project_service.ts
import { apiService } from "./api.service";
import type {
  Project,
  CreateProjectDTO,
  UpdateProjectDTO,
  ProjectListResponse,
  ProjectResponse,
  ProjectMembersResponse,
  ProjectMember,
  ProjectFilters,
  ProjectStats,
  ProjectStatsResponse,
  MetricDataPoint,
  MetricsHistoryResponse,
  ProjectRole,
} from "../types/project_types";

class ProjectService {
  private readonly BASE_PATH = "/api/projects";

  async getProjects(filters?: ProjectFilters): Promise<Project[]> {
    const params = new URLSearchParams();

    if (filters?.status && filters.status !== 'all') {
      params.append('status', filters.status);
    }
    if (filters?.sort_by) {
      params.append('sort_by', filters.sort_by);
    }
    if (filters?.sort_order) {
      params.append('sort_order', filters.sort_order);
    }
    if (filters?.search) {
      params.append('search', filters.search);
    }

    const queryString = params.toString();
    const endpoint = queryString ? `${this.BASE_PATH}?${queryString}` : this.BASE_PATH;

    const response = await apiService.get<ProjectListResponse>(endpoint);

    if (!response.success || !response.data?.projects) {
      throw new Error(response.message || "Error al obtener proyectos");
    }

    return response.data.projects;
  }

  async getProjectById(projectId: string): Promise<Project> {
    const response = await apiService.get<ProjectResponse>(
      `${this.BASE_PATH}/${projectId}`
    );

    if (!response.success || !response.data?.project) {
      throw new Error(response.message || "Error al obtener el proyecto");
    }

    return response.data.project;
  }

  async createProject(data: CreateProjectDTO): Promise<Project> {
    const response = await apiService.post<ProjectResponse>(
      this.BASE_PATH,
      data
    );

    if (!response.success || !response.data?.project) {
      throw new Error(response.message || "Error al crear el proyecto");
    }

    return response.data.project;
  }

  async updateProject(
    projectId: string,
    data: UpdateProjectDTO
  ): Promise<Project> {
    const response = await apiService.put<ProjectResponse>(
      `${this.BASE_PATH}/${projectId}`,
      data
    );

    if (!response.success || !response.data?.project) {
      throw new Error(response.message || "Error al actualizar el proyecto");
    }

    return response.data.project;
  }

  async deleteProject(projectId: string): Promise<void> {
    const response = await apiService.delete<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/${projectId}`
    );

    if (!response.success) {
      throw new Error(response.message || "Error al eliminar el proyecto");
    }
  }

  async getProjectMembers(projectId: string): Promise<ProjectMember[]> {
    const response = await apiService.get<ProjectMembersResponse>(
      `${this.BASE_PATH}/${projectId}/members`
    );

    if (!response.success || !response.data?.members) {
      throw new Error(response.message || "Error al obtener los miembros");
    }

    return response.data.members;
  }

  /**
   * Añade un miembro al proyecto
   * @param projectId - ID del proyecto
   * @param identifier - Email o username del usuario
   * @param role - Rol del miembro (viewer o editor)
   */
  async addMember(
    projectId: string,
    identifier: string,
    role: ProjectRole
  ): Promise<void> {
    const response = await apiService.post<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/${projectId}/members`,
      { identifier, role }
    );

    if (!response.success) {
      throw new Error(response.message || "Error al añadir el miembro");
    }
  }

  /**
   * Actualiza el rol de un miembro
   * @param projectId - ID del proyecto
   * @param userId - ID del usuario miembro
   * @param role - Nuevo rol
   */
  async updateMemberRole(
    projectId: string,
    userId: string,
    role: ProjectRole
  ): Promise<void> {
    const response = await apiService.put<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/${projectId}/members/${userId}`,
      { role }
    );

    if (!response.success) {
      throw new Error(response.message || "Error al actualizar el rol");
    }
  }

  async removeMember(projectId: string, userId: string): Promise<void> {
    const response = await apiService.delete<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/${projectId}/members/${userId}`
    );

    if (!response.success) {
      throw new Error(response.message || "Error al eliminar el miembro");
    }
  }

  async leaveProject(projectId: string): Promise<void> {
    const response = await apiService.post<{ success: boolean; message?: string }>(
      `${this.BASE_PATH}/${projectId}/leave`
    );

    if (!response.success) {
      throw new Error(response.message || "Error al salir del proyecto");
    }
  }

  async getProjectStats(comparisonDays: number = 30): Promise<ProjectStats> {
    const response = await apiService.get<ProjectStatsResponse>(
      `${this.BASE_PATH}/stats?comparison_days=${comparisonDays}`
    );

    if (!response.success || !response.data) {
      throw new Error(response.message || "Error al obtener estadísticas");
    }

    return response.data;
  }

  async getRecentProjects(limit = 5): Promise<Project[]> {
    const response = await apiService.get<ProjectListResponse>(
      `${this.BASE_PATH}/recent?limit=${limit}`
    );

    if (!response.success || !response.data?.projects) {
      throw new Error(response.message || "Error al obtener proyectos recientes");
    }

    return response.data.projects;
  }

  async getMetricsHistory(days: number = 30): Promise<MetricDataPoint[]> {
    const response = await apiService.get<MetricsHistoryResponse>(
      `${this.BASE_PATH}/metrics/history?days=${days}`
    );

    if (!response.success || !response.data) {
      throw new Error(response.message || "Error al obtener historial de métricas");
    }

    return response.data.metrics;
  }
}

export const projectService = new ProjectService();
export default ProjectService;