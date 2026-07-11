/**
 * Primary Key Service
 * Handles all API operations related to Primary Keys (simple and composite)
 */
import type { PrimaryKeyConstraint, SetPrimaryKeyData, PrimaryKeyValidation } from '../types/mapping-types';

const API_BASE = '/api/projects';
const IS_DEV = import.meta.env.DEV;

export const pkService = {
  /**
   * Get Primary Key for a table
   */
  async getPrimaryKey(projectId: string, tableId: string): Promise<PrimaryKeyConstraint | null> {
    const url = `${API_BASE}/${projectId}/schemas/tables/${tableId}/primary-key`;

    if (IS_DEV) console.log('[pkService] Fetching PK from:', url);

    const response = await fetch(url, {
      credentials: 'include',
    });

    if (IS_DEV) {
      console.log('[pkService] Response status:', response.status);
    }

    if (!response.ok) {
      const contentType = response.headers.get('content-type');

      if (contentType && contentType.includes('application/json')) {
        const error = await response.json();
        if (IS_DEV) console.error('[pkService] JSON error:', error);
        throw new Error(error.detail || 'Error al obtener Primary Key');
      } else {
        if (IS_DEV) {
          const text = await response.text();
          console.error('[pkService] Non-JSON response:', text.substring(0, 500));
        }
        throw new Error(`Error del servidor: ${response.status} ${response.statusText}`);
      }
    }

    const data = await response.json();
    if (IS_DEV) console.log('[pkService] PK data received:', data);
    return data.primary_key;
  },

  /**
   * Set or update Primary Key for a table
   */
  async setPrimaryKey(projectId: string, data: SetPrimaryKeyData): Promise<PrimaryKeyConstraint> {
    const response = await fetch(`${API_BASE}/${projectId}/schemas/tables/${data.table_id}/primary-key`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({
        column_ids: data.column_ids,
        constraint_name: data.constraint_name || null,
      }),
    });

    if (!response.ok) {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        const error = await response.json();

        // Handle FastAPI 422 validation errors (array of error objects)
        if (response.status === 422 && Array.isArray(error.detail)) {
          const errorMessages = (error.detail as Array<{ msg?: string }>).map((e) => e.msg || JSON.stringify(e)).join(', ');
          throw new Error(errorMessages || 'Error de validación');
        }

        // Handle other error formats
        throw new Error(error.detail || 'Error al configurar Primary Key');
      } else {
        throw new Error(`Error del servidor: ${response.status} ${response.statusText}`);
      }
    }

    const result = await response.json();
    return result.primary_key;
  },

  /**
   * Remove Primary Key from a table
   */
  async removePrimaryKey(projectId: string, tableId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/${projectId}/schemas/tables/${tableId}/primary-key`, {
      method: 'DELETE',
      credentials: 'include',
    });

    if (!response.ok) {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        const error = await response.json();
        throw new Error(error.detail || 'Error al eliminar Primary Key');
      } else {
        throw new Error(`Error del servidor: ${response.status} ${response.statusText}`);
      }
    }
  },

  /**
   * Validate that all Primary Key columns are mapped
   */
  async validatePrimaryKeyMappings(projectId: string): Promise<PrimaryKeyValidation> {
    const response = await fetch(`${API_BASE}/${projectId}/schemas/primary-keys/validate`, {
      credentials: 'include',
    });

    if (!response.ok) {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        const error = await response.json();
        throw new Error(error.detail || 'Error al validar mappings');
      } else {
        throw new Error(`Error del servidor: ${response.status} ${response.statusText}`);
      }
    }

    const data = await response.json();
    return data.validation;
  },
};

// Re-export helper utilities for backward compatibility
export {
  isCompositePrimaryKey,
  getPrimaryKeyColumnNames,
  isColumnInPrimaryKey,
  validateConstraintName,
} from './pk_service.utils';
