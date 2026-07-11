// src/hooks/mapping/useTableCRUD.tsx
import { useState, useCallback } from 'react';
import type { Table, Column } from '../../types/mapping-types';

type ModalType =
  | 'create-table'
  | 'edit-table'
  | 'delete-table'
  | 'create-column'
  | 'edit-column'
  | 'delete-column'
  | null;

interface ModalState {
  type: ModalType;
  table?: Table;
  column?: Column;
  tableId?: string;
  tableName?: string;
  tableType?: 'origin' | 'destination';
}

export const useTableCRUD = () => {
  const [modalState, setModalState] = useState<ModalState>({ type: null });

  // Table operations
  const openCreateTableModal = useCallback(() => {
    setModalState({ type: 'create-table' });
  }, []);

  const openEditTableModal = useCallback((table: Table) => {
    setModalState({ type: 'edit-table', table });
  }, []);

  const openDeleteTableModal = useCallback((table: Table) => {
    setModalState({ type: 'delete-table', table });
  }, []);

  // Column operations
  const openCreateColumnModal = useCallback((
    tableId: string,
    tableName: string,
    tableType: 'origin' | 'destination'
  ) => {
    setModalState({
      type: 'create-column',
      tableId,
      tableName,
      tableType
    });
  }, []);

  const openEditColumnModal = useCallback((
    column: Column,
    tableName: string,
    tableType: 'origin' | 'destination'
  ) => {
    setModalState({
      type: 'edit-column',
      column,
      tableName,
      tableType
    });
  }, []);

  const openDeleteColumnModal = useCallback((
    column: Column,
    tableName: string
  ) => {
    setModalState({
      type: 'delete-column',
      column,
      tableName
    });
  }, []);

  const closeModal = useCallback(() => {
    setModalState({ type: null });
  }, []);

  return {
    modalState,
    openCreateTableModal,
    openEditTableModal,
    openDeleteTableModal,
    openCreateColumnModal,
    openEditColumnModal,
    openDeleteColumnModal,
    closeModal
  };
};
