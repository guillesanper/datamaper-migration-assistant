// src/components/version_control/PermissionGuard.tsx
import React from 'react';
import { type Role, type Permissions } from '../../types/version_control_types';
import { hasPermission, getPermissionsForRole } from '../../utils/version_control/permissionUtils';

interface PermissionGuardProps {
  children: React.ReactNode;
  userRole?: Role;
  requiredPermission?: string;
  requiredPermissions?: Permissions;
  fallback?: React.ReactNode;
  onUnauthorized?: () => void;
}

/**
 * PermissionGuard - Higher-Order Component for protecting UI elements
 *
 * Usage:
 * ```tsx
 * <PermissionGuard userRole={currentUser.role} requiredPermission="edit:mapping">
 *   <Button>Edit Mapping</Button>
 * </PermissionGuard>
 * ```
 */
export const PermissionGuard: React.FC<PermissionGuardProps> = ({
  children,
  userRole,
  requiredPermission,
  requiredPermissions,
  fallback = null,
  onUnauthorized
}) => {
  // If no role provided, deny access
  if (!userRole) {
    onUnauthorized?.();
    return <>{fallback}</>;
  }

  // Check single permission
  if (requiredPermission) {
    const hasAccess = hasPermission(userRole, requiredPermission);
    if (!hasAccess) {
      onUnauthorized?.();
      return <>{fallback}</>;
    }
  }

  // Check multiple permissions (must have ALL)
  if (requiredPermissions) {
    const userPermissions = getPermissionsForRole(userRole);

    // Check each required permission
    const hasAllPermissions = Object.entries(requiredPermissions).every(([key, required]) => {
      if (!required) return true; // Skip if not required
      return userPermissions[key as keyof Permissions] === true;
    });

    if (!hasAllPermissions) {
      onUnauthorized?.();
      return <>{fallback}</>;
    }
  }

  // If we made it here, user has permission
  return <>{children}</>;
};

/**
 * Hook-based alternative for conditional rendering
 */
// eslint-disable-next-line react-refresh/only-export-components
export const usePermissionGuard = (userRole?: Role) => {
  const checkPermission = React.useCallback(
    (permission: string): boolean => {
      if (!userRole) return false;
      return hasPermission(userRole, permission);
    },
    [userRole]
  );

  const checkPermissions = React.useCallback(
    (permissions: Permissions): boolean => {
      if (!userRole) return false;
      const userPermissions = getPermissionsForRole(userRole);

      return Object.entries(permissions).every(([key, required]) => {
        if (!required) return true;
        return userPermissions[key as keyof Permissions] === true;
      });
    },
    [userRole]
  );

  return {
    can: checkPermission,
    canAll: checkPermissions,
    permissions: userRole ? getPermissionsForRole(userRole) : null
  };
};
