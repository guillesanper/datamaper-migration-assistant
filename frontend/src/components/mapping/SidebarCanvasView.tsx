// src/components/mapping/SidebarCanvasView.tsx
import React, { useState, useCallback, useEffect, useMemo } from "react";
import ReactFlow, {
  type Node,
  type Edge,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Connection,
  addEdge,
  MarkerType,
  Panel,
  ReactFlowProvider,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Search,
  Upload,
  Download,
  RefreshCw,
  Database,
  ChevronRight,
  Eye,
  EyeOff,
} from "lucide-react";
import { TableNode } from "./TableNode";
import { mappingService } from "../../services/mapping_service";
import type { Mapping, TableWithColumns } from "../../types/mapping-types";
import type { Project } from "../../types/project_types";
import type { ConnectorTable } from "../../types/db_connection_types";
import { connectorTablesToTableWithColumns } from "../../utils/connectorUtils";
import { useTranslation } from 'react-i18next';
import { toast } from "../../utils/toast";
import { getApiError } from "../../utils/apiError";
import { ImportModal } from "./ImportModal";
import { ExportModal } from "./ExportModal";
import styles from "../../styles/mapping/mapping.module.css";

const nodeTypes = {
  tableNode: TableNode,
};

interface SidebarCanvasViewProps {
  projectId: string;
  project: Project | null;
  tables: TableWithColumns[];
  mappings: Mapping[];
  onRefresh: () => void;
  connectorTables?: ConnectorTable[];
}

const SidebarCanvasViewInner: React.FC<SidebarCanvasViewProps> = ({
  projectId,
  tables: importedTables,
  mappings: initialMappings,
  onRefresh,
  connectorTables = [],
}) => {
  const { t } = useTranslation('common');
  const tables: TableWithColumns[] = useMemo(
    () => [...importedTables, ...connectorTablesToTableWithColumns(connectorTables)],
    [importedTables, connectorTables]
  );
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [visibleTables, setVisibleTables] = useState<Set<string>>(new Set());
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);

  const generateFlowNodes = useCallback((tables: TableWithColumns[]) => {
    const originTables = tables.filter((t) => t.type === "origin");
    const destTables = tables.filter((t) => t.type === "destination");

    const nodes: Node[] = [];
    const SPACING_X = 400;
    const SPACING_Y = 250;
    const MAX_COLUMNS = 3;

    // Nodos de origen
    originTables.forEach((table, index) => {
      const row = Math.floor(index / MAX_COLUMNS);
      const col = index % MAX_COLUMNS;

      nodes.push({
        id: `origin_${table.id}`,
        type: "tableNode",
        position: { x: col * SPACING_X, y: row * SPACING_Y },
        data: {
          table,
          type: "origin" as const,
          mappings: initialMappings,
          projectId,
          onDeleteMapping: () => {},
        },
      });
    });

    // Nodos de destino
    destTables.forEach((table, index) => {
      const row = Math.floor(index / MAX_COLUMNS);
      const col = index % MAX_COLUMNS;

      nodes.push({
        id: `dest_${table.id}`,
        type: "tableNode",
        position: { x: (MAX_COLUMNS + 1 + col) * SPACING_X, y: row * SPACING_Y },
        data: {
          table,
          type: "destination" as const,
          mappings: initialMappings,
          projectId,
          onDeleteMapping: () => {},
        },
      });
    });

    setNodes(nodes);
    setVisibleTables(new Set(tables.map((t) => t.id)));
  }, [projectId, initialMappings]);

  const generateFlowEdges = useCallback((mappings: Mapping[], tables: TableWithColumns[]) => {
    const edges = mappings
      .map((mapping, index) => {
        const sourceTable = tables.find(
          (t) => t.name === mapping.origin_table && t.type === "origin"
        );
        const targetTable = tables.find(
          (t) => t.name === mapping.destination_table && t.type === "destination"
        );

        if (!sourceTable || !targetTable) return null;

        const sourceColumn = sourceTable.columns.find((c) => c.name === mapping.origin_column);
        const targetColumn = targetTable.columns.find((c) => c.name === mapping.destination_column);

        if (!sourceColumn || !targetColumn) return null;

        return {
          id: `mapping_${index}`,
          source: `origin_${sourceTable.id}`,
          target: `dest_${targetTable.id}`,
          sourceHandle: `${sourceColumn.id}_out`,
          targetHandle: `${targetColumn.id}_in`,
          type: "smoothstep",
          animated: true,
          style: { stroke: "#3b82f6", strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#3b82f6" },
          data: mapping,
        };
      })
      .filter(Boolean) as Edge[];

    setEdges(edges);
  }, []);

  useEffect(() => {
    if (tables.length > 0) {
      generateFlowNodes(tables);
      generateFlowEdges(initialMappings, tables);
    }
  }, [tables, initialMappings, generateFlowNodes, generateFlowEdges]);

  const onConnect = useCallback(
    async (params: Connection) => {
      if (!params.source || !params.target) return;

      try {
        const sourceNode = nodes.find((n) => n.id === params.source);
        const targetNode = nodes.find((n) => n.id === params.target);

        if (!sourceNode?.data?.table || !targetNode?.data?.table) return;

        const sourceTable = sourceNode.data.table as TableWithColumns;
        const targetTable = targetNode.data.table as TableWithColumns;

        const sourceColumn = sourceTable.columns.find((c) => `${c.id}_out` === params.sourceHandle);
        const targetColumn = targetTable.columns.find((c) => `${c.id}_in` === params.targetHandle);

        if (!sourceColumn || !targetColumn) return;

        const newMapping: Mapping = {
          project_id: projectId,
          origin_table: sourceTable.name,
          origin_column: sourceColumn.name,
          destination_table: targetTable.name,
          destination_column: targetColumn.name,
        };

        await mappingService.createMapping(newMapping);

        setEdges((eds) =>
          addEdge(
            {
              ...params,
              type: "smoothstep",
              animated: true,
              style: { stroke: "#3b82f6", strokeWidth: 2 },
              markerEnd: { type: MarkerType.ArrowClosed, color: "#3b82f6" },
              data: newMapping,
            },
            eds
          )
        );

        toast.success("Mapeo creado exitosamente");
        onRefresh();
      } catch (error) {
        console.error("Error creating mapping:", error);
        toast.error(getApiError(error, t));
      }
    },
    [nodes, projectId, onRefresh, t]
  );

  const onEdgeDoubleClick = useCallback(
    async (_: React.MouseEvent, edge: Edge) => {
      try {
        if (edge.data) {
          await mappingService.deleteMapping(edge.data as Mapping);
          toast.success("Mapeo eliminado");
          onRefresh();
        }
      } catch (error) {
        console.error("Error deleting mapping:", error);
        toast.error(getApiError(error, t));
      }
    },
    [onRefresh, t]
  );

  const toggleTableVisibility = (tableId: string) => {
    setVisibleTables((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(tableId)) { newSet.delete(tableId); } else { newSet.add(tableId); }
      return newSet;
    });

    setNodes((nds) =>
      nds.map((node) => {
        if (node.data.table.id === tableId) {
          return { ...node, hidden: visibleTables.has(tableId) };
        }
        return node;
      })
    );
  };

  const filteredTables = tables.filter((t) =>
    t.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const originTables = filteredTables.filter((t) => t.type === "origin");
  const destTables = filteredTables.filter((t) => t.type === "destination");

  return (
    <div className={styles.sidebarCanvasLayout}>
      {/* Sidebar */}
      {sidebarOpen && (
        <div className={styles.sidebar}>
          <div className={styles.sidebarHeader}>
            <h3 className={styles.sidebarTitle}>Tablas Disponibles</h3>
            <div className={styles.sidebarSearch}>
              <Search className={styles.columnPanelSearchIcon} />
              <input
                type="text"
                placeholder="Buscar tablas..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className={styles.columnPanelSearchInput}
              />
            </div>
          </div>

          <div className={styles.sidebarContent}>
            <div className={styles.sidebarSection}>
              <div className={styles.sidebarSectionTitle}>
                <div className={`${styles.statDot} ${styles.statDotOrigin}`}></div>
                ORIGEN ({originTables.length})
              </div>
              {originTables.map((table) => (
                <div key={table.id} className={styles.sidebarTableItem}>
                  <div className={styles.sidebarTableItemLeft}>
                    <Database className={`${styles.tableCardIcon} ${styles.tableCardIconOrigin}`} />
                    <span className={styles.sidebarTableItemName}>{table.name}</span>
                    <span className={styles.sidebarTableItemCount}>({table.columns.length})</span>
                  </div>
                  <button
                    onClick={() => toggleTableVisibility(table.id)}
                    className={styles.sidebarTableItemButton}
                  >
                    {visibleTables.has(table.id) ? (
                      <Eye className="w-4 h-4" />
                    ) : (
                      <EyeOff className="w-4 h-4" />
                    )}
                  </button>
                </div>
              ))}
            </div>

            <div className={styles.sidebarSection}>
              <div className={styles.sidebarSectionTitle}>
                <div className={`${styles.statDot} ${styles.statDotDestination}`}></div>
                DESTINO ({destTables.length})
              </div>
              {destTables.map((table) => (
                <div key={table.id} className={styles.sidebarTableItem}>
                  <div className={styles.sidebarTableItemLeft}>
                    <Database className={`${styles.tableCardIcon} ${styles.tableCardIconDestination}`} />
                    <span className={styles.sidebarTableItemName}>{table.name}</span>
                    <span className={styles.sidebarTableItemCount}>({table.columns.length})</span>
                  </div>
                  <button
                    onClick={() => toggleTableVisibility(table.id)}
                    className={styles.sidebarTableItemButton}
                  >
                    {visibleTables.has(table.id) ? (
                      <Eye className="w-4 h-4" />
                    ) : (
                      <EyeOff className="w-4 h-4" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Canvas */}
      <div className={styles.canvasContainer}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onEdgeDoubleClick={onEdgeDoubleClick}
          nodeTypes={nodeTypes}
          fitView
        >
          <Background gap={12} size={1} />
          <Controls />
          <MiniMap />

          <Panel position="top-left">
            <div className="bg-card border rounded-lg shadow-lg p-2 flex items-center gap-2">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className={styles.toolbarButton}
              >
                <ChevronRight
                  className={`w-4 h-4 transition-transform ${sidebarOpen ? "rotate-180" : ""}`}
                />
              </button>
              <div className={styles.toolbarDivider}></div>
              <button
                onClick={() => setIsImportModalOpen(true)}
                className={styles.toolbarButton}
              >
                <Upload className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsExportModalOpen(true)}
                className={styles.toolbarButton}
              >
                <Download className="w-4 h-4" />
              </button>
              <button onClick={onRefresh} className={styles.toolbarButton}>
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>
          </Panel>

          <Panel position="top-right">
            <div className="bg-card border rounded-lg shadow-lg px-4 py-2">
              <div className="text-xs text-muted-foreground">Doble click en línea para eliminar</div>
              <div className="text-sm font-semibold mt-1">{edges.length} mapeos</div>
            </div>
          </Panel>
        </ReactFlow>
      </div>

      <ImportModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        projectId={projectId}
        onSuccess={onRefresh}
      />

      <ExportModal
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        projectId={projectId}
      />
    </div>
  );
};

export const SidebarCanvasView: React.FC<SidebarCanvasViewProps> = (props) => {
  return (
    <ReactFlowProvider>
      <SidebarCanvasViewInner {...props} />
    </ReactFlowProvider>
  );
};