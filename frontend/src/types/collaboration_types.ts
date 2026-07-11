// src/types/collaboration_types.ts

/**
 * Roles disponibles en el sistema de colaboración
 * - admin: Puede gestionar todo excepto transferir ownership
 * - editor: Puede editar contenido pero no gestionar miembros
 * - viewer: Solo puede ver y comentar
 */
export type Role = 'admin' | 'editor' | 'viewer';

/**
 * Colaborador de un proyecto
 */
export interface Collaborator {
  id: string;
  user_id: string;
  username: string;
  email: string;
  avatar?: string;
  role: Role;
  added_at: string;
  added_by: string;
  last_active?: string;
  is_online: boolean;
}

/**
 * Usuario online en tiempo real
 */
export interface OnlineUser {
  user_id: string;
  username: string;
  email: string;
  avatar?: string;
  status: 'online' | 'offline';
  last_seen?: string;
  current_page?: string;
  current_entity?: {
    entity_id: string;
    entity_type: string;
    action: 'viewing' | 'editing';
  };
  connected_at: string;
}

/**
 * Invitación a proyecto
 */
export interface Invitation {
  id: string;
  project_id: string;
  email: string;
  role: Role;
  token: string;
  invited_by: string;
  invited_by_name?: string;
  invited_at: string;
  expires_at: string;
  status: 'pending' | 'accepted' | 'expired' | 'rejected';
  message?: string;
}

/**
 * Permisos de un usuario en un proyecto
 */
export interface Permissions {
  can_view: boolean;
  can_edit: boolean;
  can_delete: boolean;
  can_create: boolean;
  can_invite: boolean;
  can_manage_roles: boolean;
  can_force_unlock: boolean;
  can_delete_others_comments: boolean;
  can_manage_versions: boolean;
  can_restore_versions: boolean;
}

/**
 * Request para invitar colaborador
 */
export interface InviteCollaboratorRequest {
  email: string;
  role: Role;
  message?: string;
}

/**
 * Request para actualizar rol
 */
export interface UpdateRoleRequest {
  role: Role;
}

/**
 * Response de operaciones de colaboración
 */
export interface CollaborationResponse {
  success: boolean;
  message?: string;
  data?: {
    collaborators?: Collaborator[];
    invitation?: Invitation;
    permissions?: Permissions;
  };
}

/**
 * Estadísticas de colaboración
 */
export interface CollaborationStats {
  total_collaborators: number;
  online_now: number;
  active_today: number;
  pending_invitations: number;
}
