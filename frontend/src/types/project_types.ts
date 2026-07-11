// src/types/project_types.ts

/**
 * Estado del proyecto
 */
export type ProjectStatus = 'active' | 'paused' | 'completed';

/**
 * Rol de un miembro en el proyecto
 */
export type ProjectRole = 'viewer' | 'editor';

/**
 * Interfaz principal del proyecto
 */
export interface Project {
  id: string;
  name: string;
  description: string;
  origin_db: string;
  destination_db: string;
  owner_id: string;
  status: ProjectStatus;
  progress: number;
  budget: number;
  created_at: string;
  updated_at: string;
  is_deleted: boolean;
  is_owner?: boolean;
  // Encryption fields
  encryption_enabled?: boolean;
  has_encryption_config?: boolean;
  // Tracking
  last_accessed_at?: string | null;
}

/**
 * DTO para crear un proyecto
 */
export interface CreateProjectDTO {
  name: string;
  description?: string;
  origin_db: string;
  destination_db: string;
  status?: ProjectStatus;
  progress?: number;
  budget?: number;
}

/**
 * DTO para actualizar un proyecto
 */
export interface UpdateProjectDTO {
  name?: string;
  description?: string;
  origin_db?: string;
  destination_db?: string;
  status?: ProjectStatus;
  progress?: number;
  budget?: number;
}

/**
 * Miembro de un proyecto
 */
export interface ProjectMember {
  user_id: string;
  email: string;
  username?: string; // Añadido
  role: ProjectRole;
}

/**
 * Respuesta de listado de proyectos
 */
export interface ProjectListResponse {
  success: boolean;
  data: {
    projects: Project[];
    total: number;
  };
  message?: string;
}

/**
 * Respuesta de un proyecto individual
 */
export interface ProjectResponse {
  success: boolean;
  data: {
    project: Project;
  };
  message?: string;
}

/**
 * Respuesta de miembros del proyecto
 */
export interface ProjectMembersResponse {
  success: boolean;
  data: {
    members: ProjectMember[];
  };
  message?: string;
}

/**
 * Parámetros de filtrado y ordenamiento
 */
export interface ProjectFilters {
  status?: ProjectStatus | 'all';
  sort_by?: 'name' | 'status' | 'progress' | 'budget' | 'updated_at';
  sort_order?: 'asc' | 'desc';
  search?: string;
}

// ============================================================================
// TIPOS PARA MÉTRICAS Y ESTADÍSTICAS
// ============================================================================

/**
 * Estadística individual con cambio porcentual
 */
export interface ProjectStat {
  value: number;
  change: number;
  positive: boolean;
}

/**
 * Conjunto completo de estadísticas del usuario
 */
export interface ProjectStats {
  total_projects: ProjectStat;
  active_projects: ProjectStat;
  completed_projects: ProjectStat;
  total_budget: ProjectStat;
  avg_progress?: ProjectStat;
}

/**
 * Respuesta del endpoint de estadísticas
 */
export interface ProjectStatsResponse {
  success: boolean;
  data: ProjectStats;
  message?: string;
}

/**
 * Punto de datos en el historial de métricas
 */
export interface MetricDataPoint {
  date: string;
  total_projects: number;
  active_projects: number;
  paused_projects: number;
  completed_projects: number;
  total_budget: number;
  avg_progress: number;
}

/**
 * Respuesta del endpoint de historial de métricas
 */
export interface MetricsHistoryResponse {
  success: boolean;
  data: {
    metrics: MetricDataPoint[];
    period_days: number;
  };
  message?: string;
}

/**
 * Datos formateados para tarjetas de estadísticas
 */
export interface FormattedStat {
  label: string;
  value: string | number;
  change: string;
  positive: boolean;
}

/**
 * DTO para añadir un miembro
 */
export interface AddMemberDTO {
  identifier: string; // email o username
  role: ProjectRole;
}

/**
 * DTO para actualizar el rol de un miembro
 */
export interface UpdateMemberRoleDTO {
  role: ProjectRole;
}