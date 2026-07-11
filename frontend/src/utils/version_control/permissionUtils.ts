// src/utils/version_control/permissionUtils.ts

import type { Role, Permissions } from '@/types/collaboration_types';

/**
 * Mapa de permisos por rol
 * admin: Todos los permisos excepto transferir ownership
 * editor: Puede crear/editar/eliminar contenido y comentar
 * viewer: Solo puede ver y comentar
 */
export const PERMISSIONS_MAP: Record<Role, string[]> = {
  'admin': [
    'read:*',
    'create:*',
    'edit:*',
    'delete:*',
    'manage:members',
    'manage:roles',
    'manage:versions',
    'force:unlock',
    'delete:any:comment'
  ],
  'editor': [
    'read:*',
    'create:mapping',
    'create:table',
    'create:column',
    'create:transformation',
    'edit:mapping',
    'edit:table',
    'edit:column',
    'edit:transformation',
    'delete:mapping',
    'delete:table',
    'delete:column',
    'delete:transformation',
    'create:comment',
    'edit:own:comment',
    'delete:own:comment',
    'create:version',
    'restore:version'
  ],
  'viewer': [
    'read:*',
    'create:comment',
    'edit:own:comment',
    'delete:own:comment'
  ]
};

/**
 * Verifica si un rol tiene un permiso específico
 */
export const hasPermission = (role: Role, permission: string): boolean => {
  const permissions = PERMISSIONS_MAP[role];

  // Wildcard: si tiene '*' o 'read:*' para read, etc.
  if (permissions.includes(permission)) {
    return true;
  }

  // Verificar wildcards específicos
  const [action] = permission.split(':');
  if (permissions.includes(`${action}:*`)) {
    return true;
  }

  return false;
};

/**
 * Verifica si se puede realizar una acción sobre un recurso
 */
export const canPerformAction = (
  role: Role,
  action: string,
  resource: string
): boolean => {
  return hasPermission(role, `${action}:${resource}`);
};

/**
 * Obtiene un objeto Permissions completo para un rol
 */
export const getPermissions = (role: Role, isOwner: boolean = false): Permissions => {
  // El owner tiene todos los permisos siempre
  if (isOwner) {
    return {
      can_view: true,
      can_edit: true,
      can_delete: true,
      can_create: true,
      can_invite: true,
      can_manage_roles: true,
      can_force_unlock: true,
      can_delete_others_comments: true,
      can_manage_versions: true,
      can_restore_versions: true
    };
  }

  return {
    can_view: hasPermission(role, 'read:*'),
    can_edit: canPerformAction(role, 'edit', 'mapping'),
    can_delete: canPerformAction(role, 'delete', 'mapping'),
    can_create: canPerformAction(role, 'create', 'mapping'),
    can_invite: hasPermission(role, 'manage:members'),
    can_manage_roles: hasPermission(role, 'manage:roles'),
    can_force_unlock: hasPermission(role, 'force:unlock'),
    can_delete_others_comments: hasPermission(role, 'delete:any:comment'),
    can_manage_versions: hasPermission(role, 'manage:versions'),
    can_restore_versions: hasPermission(role, 'restore:version')
  };
};

/**
 * Alias para getPermissions (para compatibilidad)
 */
export const getPermissionsForRole = getPermissions;

/**
 * Verifica si un rol puede editar un recurso específico
 */
export const canEdit = (role: Role, resourceType: string, isOwner: boolean = false): boolean => {
  if (isOwner) return true;
  return canPerformAction(role, 'edit', resourceType);
};

/**
 * Verifica si un rol puede eliminar un recurso específico
 */
export const canDelete = (role: Role, resourceType: string, isOwner: boolean = false): boolean => {
  if (isOwner) return true;
  return canPerformAction(role, 'delete', resourceType);
};

/**
 * Verifica si un rol puede crear un recurso específico
 */
export const canCreate = (role: Role, resourceType: string, isOwner: boolean = false): boolean => {
  if (isOwner) return true;
  return canPerformAction(role, 'create', resourceType);
};

/**
 * Verifica si un usuario puede editar un comentario específico
 */
export const canEditComment = (role: Role, commentUserId: string, currentUserId: string, isOwner: boolean = false): boolean => {
  if (isOwner) return true;

  // Siempre puede editar sus propios comentarios
  if (commentUserId === currentUserId) {
    return hasPermission(role, 'edit:own:comment');
  }

  // Solo admin puede editar comentarios de otros
  return role === 'admin';
};

/**
 * Verifica si un usuario puede eliminar un comentario específico
 */
export const canDeleteComment = (role: Role, commentUserId: string, currentUserId: string, isOwner: boolean = false): boolean => {
  if (isOwner) return true;

  // Puede eliminar sus propios comentarios
  if (commentUserId === currentUserId) {
    return hasPermission(role, 'delete:own:comment');
  }

  // Admin puede eliminar cualquier comentario
  return hasPermission(role, 'delete:any:comment');
};

/**
 * Obtiene el label de un rol para display
 */
export const getRoleLabel = (role: Role): string => {
  switch (role) {
    case 'admin':
      return 'Administrador';
    case 'editor':
      return 'Editor';
    case 'viewer':
      return 'Visualizador';
    default:
      return role;
  }
};

/**
 * Obtiene el color de un rol para UI
 */
export const getRoleColor = (role: Role): string => {
  switch (role) {
    case 'admin':
      return '#ef4444'; // red
    case 'editor':
      return '#3b82f6'; // blue
    case 'viewer':
      return '#6b7280'; // gray
    default:
      return '#6b7280';
  }
};

/**
 * Obtiene la descripción de un rol
 */
export const getRoleDescription = (role: Role): string => {
  switch (role) {
    case 'admin':
      return 'Puede gestionar miembros, roles y contenido del proyecto';
    case 'editor':
      return 'Puede crear, editar y eliminar contenido del proyecto';
    case 'viewer':
      return 'Puede ver el proyecto y comentar';
    default:
      return '';
  }
};

/**
 * Lista de todos los roles disponibles
 */
export const ALL_ROLES: Role[] = ['admin', 'editor', 'viewer'];

/**
 * Verifica si un rol puede invitar colaboradores
 */
export const canInviteCollaborators = (role: Role, isOwner: boolean = false): boolean => {
  if (isOwner) return true;
  return role === 'admin';
};

/**
 * Verifica si un rol puede cambiar roles de otros
 */
export const canManageRoles = (role: Role, isOwner: boolean = false): boolean => {
  if (isOwner) return true;
  return role === 'admin';
};

/**
 * Verifica si un rol puede forzar unlock
 */
export const canForceUnlock = (role: Role, isOwner: boolean = false): boolean => {
  if (isOwner) return true;
  return role === 'admin';
};
