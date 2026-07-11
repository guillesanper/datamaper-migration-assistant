// src/types/activity_types.ts

/**
 * Tipos de actividad
 */
export type ActivityType =
  | 'version_created'
  | 'comment_added'
  | 'member_added'
  | 'member_removed'
  | 'member_role_changed'
  | 'lock_acquired'
  | 'lock_released'
  | 'tag_created'
  | 'project_updated'
  | 'mapping_created'
  | 'mapping_updated'
  | 'mapping_deleted'
  | 'table_imported'
  | 'version_restored';

/**
 * Actividad del proyecto
 */
export interface Activity {
  id: string;
  project_id: string;
  user_id?: string;
  username?: string;
  user_email?: string;
  user_avatar?: string;
  activity_type: ActivityType;
  entity_id?: string;
  entity_type?: string;
  description: string;
  metadata?: ActivityMetadata;
  created_at: string;
}

/**
 * Metadata de actividad (flexible)
 */
export interface ActivityMetadata {
  [key: string]: unknown;
  version_id?: string;
  version_number?: number;
  comment_id?: string;
  old_role?: string;
  new_role?: string;
  tag_name?: string;
  lock_id?: string;
}

/**
 * Actividad agrupada (para mostrar "Usuario hizo 5 cambios")
 */
export interface GroupedActivity {
  activity_type: ActivityType;
  user_id: string;
  username: string;
  count: number;
  first_activity: Activity;
  last_activity: Activity;
  activities: Activity[];
  date: string;
}

/**
 * Filtros para actividad
 */
export interface ActivityFilters {
  user_id?: string;
  activity_type?: ActivityType[];
  entity_id?: string;
  entity_type?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

/**
 * Response de actividad
 */
export interface ActivityResponse {
  success: boolean;
  message?: string;
  data?: {
    activities?: Activity[];
    grouped?: GroupedActivity[];
    total?: number;
  };
}

/**
 * Estadísticas de actividad
 */
export interface ActivityStats {
  total_activities: number;
  activities_today: number;
  most_active_user?: {
    user_id: string;
    username: string;
    activity_count: number;
  };
  most_common_activity: ActivityType;
}
