/**
 * Web Worker for calculating ReactFlow layouts
 *
 * OPTIMIZATION: Moves expensive layout calculations off the main thread
 * to avoid blocking the UI during rendering of large projects
 *
 * Estimated Impact: -200ms for projects with >50 tables
 */

import type { Node, Edge } from 'reactflow';

interface LayoutMessage {
  type: 'CALCULATE_LAYOUT';
  payload: {
    nodes: Node[];
    edges: Edge[];
  };
  requestId: number;
}

interface LayoutResponse {
  type: 'LAYOUT_CALCULATED';
  payload: {
    nodes: Node[];
    edges: Edge[];
  };
  requestId: number;
}

// Constants for layout calculation
const LEFT_X = 100;
const RIGHT_X = 900;
const MIN_NODE_HEIGHT = 120;
const COLUMN_ROW_HEIGHT = 36;
const SPACING_BETWEEN_TABLES = 80;

/**
 * Calculate the height of a table node based on its columns
 */
function calculateTableHeight(columns: unknown[], isExpanded: boolean = true): number {
  if (!isExpanded) return MIN_NODE_HEIGHT;

  const headerHeight = 50;
  const searchHeight = columns.length > 8 ? 50 : 0;
  const maxVisibleRows = Math.min(columns.length, 10);
  const columnsHeight = maxVisibleRows * COLUMN_ROW_HEIGHT;

  return headerHeight + searchHeight + columnsHeight + 20;
}

/**
 * Calculate horizontal layout for nodes (two-column layout)
 */
function calculateLayout(nodes: Node[], edges: Edge[]): { nodes: Node[]; edges: Edge[] } {
  const originNodes = nodes.filter(n => n.id.startsWith('origin-'));
  const destNodes = nodes.filter(n => n.id.startsWith('destination-'));

  // Layout origin nodes (left column)
  let currentYOrigin = 50;
  const layoutedOriginNodes = originNodes.map((node) => {
    const tableData = node.data;
    const height = calculateTableHeight(tableData.table.columns);

    const positioned = {
      ...node,
      position: {
        x: LEFT_X,
        y: currentYOrigin,
      },
    };

    currentYOrigin += height + SPACING_BETWEEN_TABLES;
    return positioned;
  });

  // Layout destination nodes (right column)
  let currentYDest = 50;
  const layoutedDestNodes = destNodes.map((node) => {
    const tableData = node.data;
    const height = calculateTableHeight(tableData.table.columns);

    const positioned = {
      ...node,
      position: {
        x: RIGHT_X,
        y: currentYDest,
      },
    };

    currentYDest += height + SPACING_BETWEEN_TABLES;
    return positioned;
  });

  return {
    nodes: [...layoutedOriginNodes, ...layoutedDestNodes],
    edges
  };
}

// Worker message handler
self.onmessage = (event: MessageEvent<LayoutMessage>) => {
  const { type, payload, requestId } = event.data;

  if (type === 'CALCULATE_LAYOUT') {
    const { nodes, edges } = payload;

    // Perform layout calculation
    const result = calculateLayout(nodes, edges);

    // Send result back to main thread
    const response: LayoutResponse = {
      type: 'LAYOUT_CALCULATED',
      payload: result,
      requestId,
    };

    self.postMessage(response);
  }
};

// Export empty object for TypeScript
export {};
