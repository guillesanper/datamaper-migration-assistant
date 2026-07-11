import React, { memo, useMemo } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  type EdgeProps,
  getBezierPath,
} from 'reactflow';
import { Trash2 } from '../icons';
import type { Mapping } from '../../types/mapping-types';

interface CustomEdgeData {
  mapping: Mapping;
  onDelete?: (mapping: Mapping) => void;
  isConnecting?: boolean;
  selectedAttribute?: { tableName: string; columnName: string } | null;
}

// Componente interno
const CustomMappingEdgeInner: React.FC<EdgeProps<CustomEdgeData>> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  data,
  selected,
}) => {

  // Memoize edge color calculation
  const edgeColor = useMemo(() => {
    if (!data?.mapping) return '#22c55e';

    // Ensure values are strings to prevent .split() errors with encrypted data
    const originTable = String(data.mapping.origin_table || '');
    const destinationTable = String(data.mapping.destination_table || '');

    const hash = (originTable + destinationTable)
      .split('')
      .reduce((acc, char) => char.charCodeAt(0) + ((acc << 5) - acc), 0);

    const colors = [
      '#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b',
      '#10b981', '#06b6d4', '#f97316', '#6366f1',
    ];

    return colors[Math.abs(hash) % colors.length];
  }, [data?.mapping?.origin_table, data?.mapping?.destination_table]);

  // Memoize bezier path calculation
  const [edgePath, labelX, labelY] = useMemo(() =>
    getBezierPath({
      sourceX,
      sourceY,
      sourcePosition,
      targetX,
      targetY,
      targetPosition,
      curvature: 0.25,
    }), [sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition]
  );

  // Verificar si esta conexión está relacionada con el atributo seleccionado
  const isRelatedToSelection = data?.selectedAttribute && data?.mapping && (
    (data.selectedAttribute.tableName === data.mapping.origin_table &&
     data.selectedAttribute.columnName === data.mapping.origin_column) ||
    (data.selectedAttribute.tableName === data.mapping.destination_table &&
     data.selectedAttribute.columnName === data.mapping.destination_column)
  );

  // Mostrar badge si el edge está seleccionado O si está relacionado con la selección de atributo
  const shouldShowBadge = (selected || isRelatedToSelection) && !data?.isConnecting;

  return (
    <>
      <g className="react-flow__edge-interaction">
        {/* Área invisible de click más grande para facilitar la selección */}
        <BaseEdge
          id={`${id}-hitarea`}
          path={edgePath}
          style={{
            stroke: 'transparent',
            strokeWidth: 30,
            cursor: 'pointer',
          }}
        />
        {/* Edge visual con colores y animaciones */}
        <BaseEdge
          id={id}
          path={edgePath}
          markerEnd={undefined}
          style={{
            ...style,
            stroke: edgeColor,
            strokeWidth: shouldShowBadge || selected ? 4 : 2.5,
            strokeOpacity: shouldShowBadge || selected ? 1 : 0.8,
            transition: 'stroke-width 0.2s ease, stroke-opacity 0.2s ease',
            cursor: 'pointer',
          }}
        />
      </g>

      {shouldShowBadge && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all',
              zIndex: 1000,
            }}
            className="nodrag nopan"
          >
            <div
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium
                         bg-white dark:bg-gray-800 border-2 shadow-xl
                         transition-all duration-200"
              style={{
                borderColor: edgeColor,
                color: edgeColor,
              }}
            >
              {data?.mapping && (
                <>
                  <span className="truncate max-w-[120px] font-semibold" title={data.mapping.origin_column}>
                    {data.mapping.origin_column}
                  </span>
                  <span className="text-gray-400 text-[10px] font-bold">→</span>
                  <span className="truncate max-w-[120px] font-semibold" title={data.mapping.destination_column}>
                    {data.mapping.destination_column}
                  </span>
                </>
              )}

              {data?.onDelete && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm('¿Eliminar este mapeo?')) {
                      data?.onDelete?.(data.mapping);
                    }
                  }}
                  className="p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded transition-colors ml-1.5 flex-shrink-0"
                  title="Eliminar mapeo"
                >
                  <Trash2 className="w-3.5 h-3.5 text-red-500" />
                </button>
              )}
            </div>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
};

// CRÍTICO: Exportar con React.memo
export const CustomMappingEdge = memo(CustomMappingEdgeInner, (prevProps, nextProps) => {
  return (
    prevProps.id === nextProps.id &&
    prevProps.selected === nextProps.selected &&
    prevProps.sourceX === nextProps.sourceX &&
    prevProps.sourceY === nextProps.sourceY &&
    prevProps.targetX === nextProps.targetX &&
    prevProps.targetY === nextProps.targetY &&
    prevProps.data?.mapping.origin_column === nextProps.data?.mapping.origin_column &&
    prevProps.data?.mapping.destination_column === nextProps.data?.mapping.destination_column &&
    prevProps.data?.selectedAttribute?.tableName === nextProps.data?.selectedAttribute?.tableName &&
    prevProps.data?.selectedAttribute?.columnName === nextProps.data?.selectedAttribute?.columnName
  );
});

CustomMappingEdge.displayName = 'CustomMappingEdge';
