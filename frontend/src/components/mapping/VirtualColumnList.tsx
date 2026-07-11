// src/components/mapping/VirtualColumnList.tsx
import React from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { Column } from '../../types/mapping-types';

interface VirtualColumnListProps {
  columns: Column[];
  renderColumn: (column: Column, index: number) => React.ReactNode;
  containerHeight?: number;
  estimateSize?: number;
}

/**
 * Virtualized column list for better performance with large datasets
 * Only renders visible columns in the viewport
 */
export const VirtualColumnList: React.FC<VirtualColumnListProps> = ({
  columns,
  renderColumn,
  containerHeight = 400,
  estimateSize = 40,
}) => {
  const parentRef = React.useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: columns.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimateSize,
    overscan: 5, // Render 5 items above and below viewport for smooth scrolling
  });

  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div
      ref={parentRef}
      style={{
        height: `${containerHeight}px`,
        overflow: 'auto',
      }}
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualItems.map((virtualRow) => {
          const column = columns[virtualRow.index];
          return (
            <div
              key={column.id}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              {renderColumn(column, virtualRow.index)}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default VirtualColumnList;
