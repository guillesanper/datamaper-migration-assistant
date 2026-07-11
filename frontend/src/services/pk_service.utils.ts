/**
 * Primary Key Service - Utilities
 * Helper functions without HTTP dependencies (lightweight, no fetch calls)
 */
import type { PrimaryKeyConstraint } from '../types/mapping-types';

/**
 * Helper: Check if a table has a composite PK
 */
export const isCompositePrimaryKey = (pk: PrimaryKeyConstraint | null): boolean => {
  return pk !== null && pk.column_ids.length > 1;
};

/**
 * Helper: Get PK column names as string
 */
export const getPrimaryKeyColumnNames = (pk: PrimaryKeyConstraint | null): string => {
  if (!pk || pk.columns.length === 0) return 'Sin PK';

  const columnNames = pk.columns.map(col => col.name).join(', ');
  return pk.is_composite ? `(${columnNames})` : columnNames;
};

/**
 * Helper: Check if column is part of PK
 */
export const isColumnInPrimaryKey = (columnId: string, pk: PrimaryKeyConstraint | null): boolean => {
  return pk !== null && pk.column_ids.includes(columnId);
};

/**
 * Helper: Validate constraint name format
 */
export const validateConstraintName = (value: string): string | null => {
  if (!value.trim()) return null; // Optional field

  if (!/^[A-Za-z][A-Za-z0-9_]{0,62}$/.test(value)) {
    return 'El nombre debe comenzar con letra y contener solo letras, números y _ (máx 63 caracteres)';
  }
  return null;
};
