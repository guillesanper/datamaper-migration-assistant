// src/types/versioning_types.ts

/**
 * Tipos de cambio en una versión
 */
export type ChangeType = 'create' | 'update' | 'delete';

/**
 * Tipos de entidad versionable
 */
export type EntityType = 'mapping' | 'table' | 'column' | 'transformation' | 'project';

/**
 * Versión de una entidad
 */
export interface Version {
  id: string;
  hash: string;
  project_id: string;
  entity_id: string;
  entity_type: EntityType;
  user_id: string;
  username: string;
  user_email?: string;
  version_number: number;
  change_type: ChangeType;
  message?: string;
  snapshot: string; // JSON stringified
  diff?: VersionDiff;
  parent_version_id?: string;
  created_at: string;
  tags?: Tag[];
}

/**
 * Diferencias entre versiones
 */
export interface VersionDiff {
  added: DiffEntry[];
  removed: DiffEntry[];
  modified: DiffEntry[];
}

/**
 * Entrada de diferencia
 */
export interface DiffEntry {
  path: string;
  value?: unknown;
  old_value?: unknown;
  new_value?: unknown;
}

/**
 * Tag/etiqueta de versión
 */
export interface Tag {
  id: string;
  version_id: string;
  project_id: string;
  name: string;
  description?: string;
  color?: string;
  created_by: string;
  created_by_name?: string;
  created_at: string;
}

/**
 * Filtros para historial de versiones
 */
export interface VersionFilters {
  user_id?: string;
  change_type?: ChangeType[];
  date_from?: string;
  date_to?: string;
  entity_type?: EntityType;
  search_term?: string;
  tags?: string[];
  limit?: number;
  offset?: number;
}

/**
 * Request para crear versión
 */
export interface CreateVersionRequest {
  entity_id: string;
  entity_type: EntityType;
  change_type: ChangeType;
  message?: string;
  snapshot: object; // Será stringificado
}

/**
 * Request para crear tag
 */
export interface CreateTagRequest {
  version_id: string;
  name: string;
  description?: string;
  color?: string;
}

/**
 * Request para comparar versiones
 */
export interface CompareVersionsRequest {
  version_a_id: string;
  version_b_id: string;
}

/**
 * Request para restaurar versión
 */
export interface RestoreVersionRequest {
  version_id: string;
  create_backup?: boolean; // Crear backup antes de restaurar
  message?: string;
}

/**
 * Response de versiones
 */
export interface VersionResponse {
  success: boolean;
  message?: string;
  data?: {
    version?: Version;
    versions?: Version[];
    total?: number;
    diff?: VersionDiff;
    tag?: Tag;
    tags?: Tag[];
  };
}

/**
 * Snapshot parseado de una entidad
 */
export interface EntitySnapshot {
  [key: string]: unknown;
}

/**
 * Estadísticas de versionado
 */
export interface VersioningStats {
  total_versions: number;
  versions_today: number;
  total_tags: number;
  unique_contributors: number;
  last_version_at?: string;
}
