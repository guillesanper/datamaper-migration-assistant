// src/components/mapping/TableNode.tsx
import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import {
  ChevronDown,
  ChevronRight,
  Database,
  Key,
  Lock,
  Search,
  Trash2,
  Edit,
  Plus,
} from '../icons';
import type { Mapping, TableWithColumns, Column } from '../../types/mapping-types';
import { useColumnLocks } from '../../hooks/mapping/useColumnLocks';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '../ui/context-menu';

export interface TableNodeData {
  table: TableWithColumns;
  type: 'origin' | 'destination';
  mappings: Mapping[];
  projectId: string;
  onDeleteMapping: (mapping: Mapping) => void;
  onSearchChange?: (tableName: string, searchTerm: string) => void;
  onEditTable?: (table: TableWithColumns) => void;
  onDeleteTable?: (table: TableWithColumns) => void;
  onAddColumn?: (tableId: string, tableName: string, tableType: 'origin' | 'destination') => void;
  onEditColumn?: (column: Column, tableName: string, tableType: 'origin' | 'destination') => void;
  onDeleteColumn?: (column: Column, tableName: string) => void;
  onDefinePrimaryKey?: (table: TableWithColumns) => void;
  onPreloadPrimaryKey?: () => void;
  onPreloadTableModal?: () => void;
  onPreloadColumnModal?: () => void;
  onPreloadDeleteTableModal?: () => void;
  onPreloadDeleteColumnModal?: () => void;
  onAttributeClick?: (tableName: string, columnName: string) => void;
  selectedAttribute?: { tableName: string; columnName: string } | null;
  primaryKeyInfo?: { columnIds: string[], isComposite: boolean } | null;
  isExpanded?: boolean;
  onToggleExpand?: (nodeId: string) => void;
}

// CRÍTICO: Componente interno memoizado
const TableNodeInner: React.FC<NodeProps<TableNodeData>> = ({ data, id }) => {
  const isExpanded = data.isExpanded ?? true;
  const [searchTerm, setSearchTerm] = React.useState("");
  const {
    table,
    type,
    mappings,
    projectId,
    onSearchChange,
    onEditTable,
    onDeleteTable,
    onAddColumn,
    onEditColumn,
    onDeleteColumn,
    onDefinePrimaryKey,
    onPreloadPrimaryKey,
    onPreloadTableModal,
    onPreloadColumnModal,
    onPreloadDeleteTableModal,
    onPreloadDeleteColumnModal,
    onAttributeClick,
    selectedAttribute,
    primaryKeyInfo
  } = data;
  const isOrigin = type === 'origin';

  // Get Primary Key columns
  const pkColumns = primaryKeyInfo
    ? table.columns.filter(col => primaryKeyInfo.columnIds.includes(col.id))
    : table.columns.filter(col => col.is_primary);

  const hasPrimaryKey = pkColumns.length > 0;
  const isCompositePK = pkColumns.length > 1;

  // Hook para gestionar locks de columnas
  const { getColumnLockInfo } = useColumnLocks(projectId);

  const handleSearchChange = React.useCallback((value: string) => {
    setSearchTerm(value);
    onSearchChange?.(table.name, value);
  }, [table.name, onSearchChange]);

  // Memoize filtered columns to avoid recalculating on every render
  const filteredColumns = React.useMemo(() => {
    if (!searchTerm) return table.columns;
    const lowerSearch = searchTerm.toLowerCase();
    return table.columns.filter(col => col.name.toLowerCase().includes(lowerSearch));
  }, [table.columns, searchTerm]);

  // Memoize column mapping lookup
  const getColumnMapping = React.useCallback((columnName: string) => {
    return mappings.find((m) =>
      isOrigin
        ? m.origin_table === table.name && m.origin_column === columnName
        : m.destination_table === table.name && m.destination_column === columnName
    );
  }, [mappings, isOrigin, table.name]);

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <div
          className={`
            bg-card rounded-lg border-2 shadow-lg
            border-border
            ${isOrigin ? 'border-l-4 border-l-blue-500' : 'border-r-4 border-r-green-500'}
          `}
          style={{
            minWidth: '320px',
            maxWidth: '380px',
          }}
        >
          {/* Header */}
          <div
            className="px-3 py-2 bg-muted/50 border-b cursor-pointer flex items-center gap-2"
            onClick={() => data.onToggleExpand?.(id)}
          >
            {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            <Database className={`w-4 h-4 ${isOrigin ? 'text-blue-500' : 'text-green-500'}`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-sm truncate block" title={table.name}>
                  {table.name}
                </span>
                {table.is_connector && (
                  <span className="flex-shrink-0 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border border-orange-200 dark:border-orange-700">
                    <Database className="w-2.5 h-2.5" />
                    Connector
                  </span>
                )}
              </div>
              {hasPrimaryKey && (
                <div className="flex items-center gap-1 mt-0.5">
                  <Key className="w-3 h-3 text-yellow-500" />
                  <span
                    className="text-xs text-muted-foreground truncate"
                    title={`Primary Key: ${pkColumns.map(c => c.name).join(', ')}`}
                  >
                    PK: {pkColumns.map(c => c.name).join(', ')}
                    {isCompositePK && ' (Compuesta)'}
                  </span>
                </div>
              )}
            </div>
            <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded flex-shrink-0">
              {table.columns.length}
            </span>
          </div>

      {/* Search */}
      {isExpanded && table.columns.length > 8 && (
        <div className="px-3 py-2 border-b">
          <div className="relative flex items-center gap-2">
            <Search className="w-4 h-4 text-muted-foreground flex-shrink-0" />
            <input
              type="text"
              placeholder="Buscar..."
              value={searchTerm}
              onChange={(e) => handleSearchChange(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              className="flex-1 px-2 py-1 text-xs border rounded bg-background nodrag"
            />
          </div>
        </div>
      )}

      {/* Columns - with virtualization for large tables */}
      {isExpanded && (
        <div style={{ maxHeight: filteredColumns.length > 20 ? '400px' : 'auto', overflow: filteredColumns.length > 20 ? 'auto' : 'visible' }}>
          {filteredColumns.map((column) => {
            const mapping = getColumnMapping(column.name);
            const isMapped = !!mapping;
            const handleId = `${table.name}::${column.name}`;

            // Obtener información del lock para esta columna
            const lockInfo = getColumnLockInfo(table.name, column.name);
            const isLocked = lockInfo.isLocked && !lockInfo.isLockedByMe;

            // Verificar si este atributo está seleccionado
            const isSelected = selectedAttribute?.tableName === table.name && selectedAttribute?.columnName === column.name;

            // Check if this column is part of PK (including composite)
            const isPartOfPK = primaryKeyInfo
              ? primaryKeyInfo.columnIds.includes(column.id)
              : column.is_primary;

            return (
              <ContextMenu key={column.id}>
                <ContextMenuTrigger asChild>
                  <label
                    htmlFor={handleId}
                    onClick={(e) => {
                      // Solo activar la selección con click, no al arrastrar para crear conexiones
                      if (e.detail === 1) {
                        e.stopPropagation();
                        onAttributeClick?.(table.name, column.name);
                      }
                    }}
                    className={`
                      py-2.5 hover:bg-muted/50 transition-colors relative cursor-pointer
                      ${isMapped ? (isOrigin ? 'bg-blue-50 dark:bg-blue-950/20' : 'bg-green-50 dark:bg-green-950/20') : ''}
                      ${isLocked ? 'opacity-60' : ''}
                      ${isSelected ? (isOrigin ? 'ring-2 ring-blue-500 bg-blue-100 dark:bg-blue-900/40' : 'ring-2 ring-green-500 bg-green-100 dark:bg-green-900/40') : ''}
                      group flex items-center justify-between gap-2
                    `}
                    style={{
                      paddingLeft: isOrigin ? '12px' : '24px',
                      paddingRight: isOrigin ? '24px' : '12px',
                    }}
                  >
                <Handle
                  type={isOrigin ? "source" : "target"}
                  position={isOrigin ? Position.Right : Position.Left}
                  id={handleId}
                  isConnectable={!isLocked}
                  className={`
                    !w-4 !h-4 !border-2 !border-white
                    ${isOrigin ? '!bg-blue-500 hover:!bg-blue-600' : '!bg-green-500 hover:!bg-green-600'}
                    ${isLocked ? '!bg-gray-400 !cursor-not-allowed' : ''}
                    transition-all duration-200
                    ${!isLocked ? 'group-hover:!scale-125 group-hover:!shadow-lg' : ''}
                  `}
                  style={{
                    top: '50%',
                    [isOrigin ? 'right' : 'left']: 4,
                    zIndex: 10,
                  }}
                />

                <div className="flex items-center gap-2 flex-1 min-w-0">
                  {isPartOfPK && (
                    <div title={isCompositePK ? 'Parte de PK compuesta' : 'Primary Key'}>
                      <Key
                        className={`w-3 h-3 flex-shrink-0 ${
                          isCompositePK ? 'text-yellow-600' : 'text-yellow-500'
                        }`}
                      />
                    </div>
                  )}
                  <span className="text-xs font-medium truncate" title={column.name}>
                    {column.name}
                  </span>
                  {lockInfo.isLocked && lockInfo.lockedBy && (
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Lock className="w-3 h-3 text-orange-500" />
                      <span className="text-xs text-orange-600 dark:text-orange-400" title={`Bloqueado por ${lockInfo.lockedBy.username}`}>
                        {lockInfo.lockedBy.username}
                      </span>
                    </div>
                  )}
                  {isMapped && (
                    <div
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        isOrigin ? 'bg-blue-500' : 'bg-green-500'
                      }`}
                    />
                  )}
                </div>

                <div className="flex items-center gap-1 flex-shrink-0">
                  {!isOrigin && isMapped && mapping && (
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        if (window.confirm('¿Eliminar mapeo?')) {
                          data.onDeleteMapping(mapping);
                        }
                      }}
                      className="p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded nodrag"
                    >
                      <Trash2 className="w-3 h-3 text-red-500" />
                    </button>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {column.data_type?.slice(0, 3) || '---'}
                  </span>
                  {!column.is_nullable && (
                    <span className="text-xs text-red-500">!</span>
                  )}
                </div>
              </label>
            </ContextMenuTrigger>
            <ContextMenuContent>
              <ContextMenuItem
                onClick={(e) => {
                  e.stopPropagation();
                  onEditColumn?.(column, table.name, type);
                }}
                onMouseEnter={() => onPreloadColumnModal?.()}
              >
                <Edit className="w-4 h-4 mr-2" />
                Editar Columna
              </ContextMenuItem>
              <ContextMenuSeparator />
              <ContextMenuItem
                variant="destructive"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteColumn?.(column, table.name);
                }}
                onMouseEnter={() => onPreloadDeleteColumnModal?.()}
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Eliminar Columna
              </ContextMenuItem>
            </ContextMenuContent>
          </ContextMenu>
            );
          })}
        </div>
      )}
    </div>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onEditTable?.(table);
          }}
          onMouseEnter={() => onPreloadTableModal?.()}
        >
          <Edit className="w-4 h-4 mr-2" />
          Editar Tabla
        </ContextMenuItem>
        <ContextMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onAddColumn?.(table.id, table.name, type);
          }}
          onMouseEnter={() => onPreloadColumnModal?.()}
        >
          <Plus className="w-4 h-4 mr-2" />
          Añadir Columna
        </ContextMenuItem>
        <ContextMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onDefinePrimaryKey?.(table);
          }}
          onMouseEnter={() => onPreloadPrimaryKey?.()}
        >
          <Key className="w-4 h-4 mr-2 text-yellow-500" />
          {hasPrimaryKey ? 'Editar Primary Key' : 'Definir Primary Key'}
        </ContextMenuItem>
        <ContextMenuSeparator />
        <ContextMenuItem
          variant="destructive"
          onClick={(e) => {
            e.stopPropagation();
            onDeleteTable?.(table);
          }}
          onMouseEnter={() => onPreloadDeleteTableModal?.()}
        >
          <Trash2 className="w-4 h-4 mr-2" />
          Eliminar Tabla
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
};

// CRÍTICO: Exportar con React.memo para evitar re-renders innecesarios
export const TableNode = memo(TableNodeInner, (prevProps, nextProps) => {
  return (
    prevProps.data.table.id === nextProps.data.table.id &&
    prevProps.data.mappings.length === nextProps.data.mappings.length &&
    prevProps.data.type === nextProps.data.type &&
    prevProps.data.isExpanded === nextProps.data.isExpanded
  );
});

TableNode.displayName = 'TableNode';