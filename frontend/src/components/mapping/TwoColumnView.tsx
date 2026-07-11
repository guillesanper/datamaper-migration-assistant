// src/components/mapping/TwoColumnMappingView.tsx
import React, { useState, useEffect, useMemo, useCallback, Suspense, lazy, useDeferredValue, useReducer, useRef } from "react";
import ReactFlow, {
  Background,
  useReactFlow,
  ReactFlowProvider,
  Panel,
  useViewport,
} from 'reactflow';
import type { Edge, Node, Connection } from 'reactflow';
import { ConnectionLineType, MarkerType } from 'reactflow';
import 'reactflow/dist/style.css';
import {
  Search,
  Filter,
  Plus,
} from "../icons";
import { mappingService } from "../../services/mapping_service";
import { CustomMappingEdge } from './CustomMappingEdge';
import { TableNode, type TableNodeData } from './TableNode';
import { CollaborativeCursors } from './CollaborativeCursors';
import type { Mapping, TableWithColumns } from "../../types/mapping-types";
import type { Project } from "../../types/project_types";
import type { ConnectorTable } from "../../types/db_connection_types";
import { connectorTablesToTableWithColumns } from "../../utils/connectorUtils";
import { toast } from "../../utils/toast";
import { realtimeService } from "../../services/version_control/realtime.service";
import type { MappingMessage } from "../../types/realtime_types";
import { useCollaborativeCursors } from "../../hooks/mapping/useCollaborativeCursors";
import { authService } from "../../services/auth_service";
import { useTranslation } from 'react-i18next';
import { getApiError } from '../../utils/apiError';
import { useTableCRUD } from "../../hooks/mapping/useTableCRUD";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '../ui/context-menu';

// Lazy load modales con preload functions
const TableModal = lazy(() => import('./modals/TableModal').then(m => ({ default: m.TableModal })));
const preloadTableModal = () => import('./modals/TableModal');

const ColumnModal = lazy(() => import('./modals/ColumnModal').then(m => ({ default: m.ColumnModal })));
const preloadColumnModal = () => import('./modals/ColumnModal');

const DeleteTableModal = lazy(() => import('./modals/DeleteTableModal').then(m => ({ default: m.DeleteTableModal })));
const preloadDeleteTableModal = () => import('./modals/DeleteTableModal');

const DeleteColumnModal = lazy(() => import('./modals/DeleteColumnModal').then(m => ({ default: m.DeleteColumnModal })));
const preloadDeleteColumnModal = () => import('./modals/DeleteColumnModal');

const PrimaryKeyModalLazy = lazy(() => import('./modals/PrimaryKeyModal').then(m => ({ default: m.PrimaryKeyModal })));
const preloadPrimaryKeyModal = () => import('./modals/PrimaryKeyModal');

interface TwoColumnMappingViewProps {
  projectId: string;
  project: Project | null;
  tables: TableWithColumns[];
  mappings: Mapping[];
  onRefresh: () => void;
  connectorTables?: ConnectorTable[];
}

//  CRÍTICO: nodeTypes y edgeTypes fuera del componente para estabilidad
const NODE_TYPES = {
  tableNode: TableNode,
};

const EDGE_TYPES = {
  custom: CustomMappingEdge,
};

//  CRÍTICO: Constantes memoizadas fuera del componente
const connectionLineStyle = { stroke: '#3b82f6', strokeWidth: 2 };
const defaultEdgeOptions = {
  type: 'custom' as const,
  animated: false,
};
const snapGrid: [number, number] = [30, 30];

// ============================================
// STATE MANAGEMENT - Reducer para estado de filtros
// ============================================
interface FilterState {
  searchOrigin: string;
  searchDestination: string;
  showFilters: boolean;
  onlyMapped: boolean;
  selectedOrigins: string[];
  selectedDestinations: string[];
}

type FilterAction =
  | { type: 'SET_SEARCH_ORIGIN'; payload: string }
  | { type: 'SET_SEARCH_DESTINATION'; payload: string }
  | { type: 'TOGGLE_FILTERS' }
  | { type: 'SET_ONLY_MAPPED'; payload: boolean }
  | { type: 'SET_SELECTED_ORIGINS'; payload: string[] }
  | { type: 'SET_SELECTED_DESTINATIONS'; payload: string[] }
  | { type: 'CLEAR_ORIGIN_SELECTION' }
  | { type: 'CLEAR_DESTINATION_SELECTION' }
  | { type: 'CLEAR_ALL_FILTERS' };

const initialFilterState: FilterState = {
  searchOrigin: '',
  searchDestination: '',
  showFilters: false,
  onlyMapped: false,
  selectedOrigins: [],
  selectedDestinations: [],
};

function filterReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case 'SET_SEARCH_ORIGIN':
      return { ...state, searchOrigin: action.payload };
    case 'SET_SEARCH_DESTINATION':
      return { ...state, searchDestination: action.payload };
    case 'TOGGLE_FILTERS':
      return { ...state, showFilters: !state.showFilters };
    case 'SET_ONLY_MAPPED':
      return { ...state, onlyMapped: action.payload };
    case 'SET_SELECTED_ORIGINS':
      return { ...state, selectedOrigins: action.payload };
    case 'SET_SELECTED_DESTINATIONS':
      return { ...state, selectedDestinations: action.payload };
    case 'CLEAR_ORIGIN_SELECTION':
      return { ...state, selectedOrigins: [] };
    case 'CLEAR_DESTINATION_SELECTION':
      return { ...state, selectedDestinations: [] };
    case 'CLEAR_ALL_FILTERS':
      return {
        ...state,
        onlyMapped: false,
        selectedOrigins: [],
        selectedDestinations: [],
      };
    default:
      return state;
  }
}

// ============================================
// LAYOUT HORIZONTAL - Fuera del componente para no recrearlo
// ============================================
const getLayoutedElements = (
  nodes: Node<TableNodeData>[],
  edges: Edge[],
  expandedNodes: Record<string, boolean> = {},
) => {
  const originNodes = nodes.filter(n => n.id.startsWith('origin-'));
  const destNodes = nodes.filter(n => n.id.startsWith('destination-'));

  const LEFT_X = 100;
  const RIGHT_X = 900;
  const COLUMN_ROW_HEIGHT = 36;
  const SPACING_BETWEEN_TABLES = 80;

  const calculateTableHeight = (table: TableWithColumns, nodeId: string) => {
    const isExpanded = expandedNodes[nodeId] !== false;
    const headerHeight = 50;
    if (!isExpanded) return headerHeight;
    const searchHeight = table.columns.length > 8 ? 50 : 0;
    const maxVisibleRows = Math.min(table.columns.length, 10);
    const columnsHeight = maxVisibleRows * COLUMN_ROW_HEIGHT;

    return headerHeight + searchHeight + columnsHeight + 20;
  };

  let currentYOrigin = 50;
  const layoutedOriginNodes = originNodes.map((node) => {
    const tableData = node.data as TableNodeData;
    const height = calculateTableHeight(tableData.table, node.id);

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

  let currentYDest = 50;
  const layoutedDestNodes = destNodes.map((node) => {
    const tableData = node.data as TableNodeData;
    const height = calculateTableHeight(tableData.table, node.id);

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
};

// ============================================
// COMPONENTE PRINCIPAL
// ============================================
const TwoColumnMappingViewInner: React.FC<TwoColumnMappingViewProps> = ({
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
  const [mappings, setMappings] = useState(initialMappings);
  const [tableSearchTerms, setTableSearchTerms] = useState<Record<string, string>>({});

  // Consolidate filter state with useReducer (OPTIMIZATION: reduces re-renders)
  const [filterState, dispatchFilter] = useReducer(filterReducer, initialFilterState);

  // Deferred values for search to avoid blocking UI during typing
  const deferredSearchOrigin = useDeferredValue(filterState.searchOrigin);
  const deferredSearchDestination = useDeferredValue(filterState.searchDestination);
  const [isWebSocketConnected, setIsWebSocketConnected] = useState(false);
  const [currentUserId, setCurrentUserId] = useState<string | undefined>(undefined);
  const [isConnecting, setIsConnecting] = useState(false);
  const [selectedAttribute, setSelectedAttribute] = useState<{ tableName: string; columnName: string } | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});
  const [pkModalState, setPkModalState] = useState<{ isOpen: boolean; table: TableWithColumns | null }>({
    isOpen: false,
    table: null
  });

  // Set persistente para rastrear mensajes ya procesados (evitar duplicados)
  const processedMessagesRef = useRef(new Set<string>());

  // Usar ref para currentUserId para que el closure del WebSocket siempre tenga el valor actual
  const currentUserIdRef = useRef<string | undefined>(undefined);

  // Hook para CRUD de tablas y columnas
  const {
    modalState,
    openCreateTableModal,
    openEditTableModal,
    openDeleteTableModal,
    openCreateColumnModal,
    openEditColumnModal,
    openDeleteColumnModal,
    closeModal
  } = useTableCRUD();

  // Obtener el ID del usuario actual
  useEffect(() => {
    const fetchCurrentUser = async () => {
      try {
        const user = await authService.getCurrentUser();
        if (user) {
          console.log('[TwoColumnView] Current user fetched:', user.id);
          setCurrentUserId(user.id);
          currentUserIdRef.current = user.id; // Actualizar ref también
        }
      } catch (error) {
        console.error('[TwoColumnView] Error fetching current user:', error);
      }
    };

    fetchCurrentUser();
  }, []);

  // Hook para cursores colaborativos - solo habilitado cuando WebSocket está conectado
  const {
    cursors,
    broadcastCursorPosition,
    broadcastCursorLeave,
  } = useCollaborativeCursors(projectId, isWebSocketConnected, currentUserId);

  const reactFlowInstance = useReactFlow();
  const viewport = useViewport(); // Para coordenadas del canvas

  useEffect(() => {
    setMappings(initialMappings);
  }, [initialMappings]);

  //  Conectar al WebSocket y suscribirse a eventos de mapeos
  useEffect(() => {
    let unsubscribe: (() => void) | null = null;
    let connectionCheckInterval: ReturnType<typeof setInterval> | null = null;

    const connectAndSubscribe = async () => {
      try {
        console.log('[TwoColumnView] Connecting to WebSocket for project:', projectId);

        // Conectar al WebSocket del proyecto
        if (!realtimeService.isConnected()) {
          await realtimeService.connect(projectId);
          console.log('[TwoColumnView] WebSocket connected successfully');
        } else {
          console.log('[TwoColumnView] WebSocket already connected');
        }

        // Esperar a que la conexión se establezca completamente
        connectionCheckInterval = setInterval(() => {
          const isConnected = realtimeService.isConnected();
          setIsWebSocketConnected(isConnected);

          if (isConnected) {
            console.log('[TwoColumnView]  WebSocket connection confirmed');
            if (connectionCheckInterval) {
              clearInterval(connectionCheckInterval);
              connectionCheckInterval = null;
            }
          }
        }, 100);

        // Suscribirse a eventos de mapeos
        console.log('[TwoColumnView] Subscribing to mapping events...');
        console.log('[TwoColumnView] Current user ID at subscription time:', currentUserIdRef.current);

        unsubscribe = realtimeService.subscribeToMappings((message) => {
          const typedMsg = message as MappingMessage & { ts?: string };
          console.log('[TwoColumnView] Mapping event received:', typedMsg);

          // Crear ID único para el mensaje basado en tipo, timestamp y contenido
          // El backend envía 'ts' en lugar de 'timestamp'
          const timestamp = typedMsg.ts || typedMsg.timestamp || Date.now().toString();
          const messageId = `${typedMsg.type}_${timestamp}_${JSON.stringify(typedMsg.mapping)}`;

          // Si ya procesamos este mensaje, ignorarlo
          if (processedMessagesRef.current.has(messageId)) {
            console.log('[TwoColumnView] Duplicate message detected, skipping:', messageId.substring(0, 100));
            return;
          }

          // Marcar como procesado
          processedMessagesRef.current.add(messageId);

          // Limpiar mensajes antiguos después de 10 segundos para evitar memory leak
          setTimeout(() => {
            processedMessagesRef.current.delete(messageId);
          }, 10000);

          // Verificar si el usuario actual es quien realizó la acción (no mostrar notificación de tus propias acciones)
          // Usar ref para obtener siempre el valor más reciente
          const currentUserIdValue = currentUserIdRef.current;
          const isOwnAction = typedMsg.actor_id && currentUserIdValue && String(typedMsg.actor_id) === String(currentUserIdValue);

          console.log('[TwoColumnView] Actor comparison:', {
            actor_id: typedMsg.actor_id,
            actor_id_type: typeof typedMsg.actor_id,
            currentUserId: currentUserIdValue,
            currentUserId_type: typeof currentUserIdValue,
            isOwnAction,
            comparison: `${String(typedMsg.actor_id)} === ${String(currentUserIdValue)}`
          });

          if (isOwnAction) {
            console.log('[TwoColumnView] ✅ Own action detected, updating state without notification');
          } else {
            console.log('[TwoColumnView] ⚠️ Not own action, will show notification');
          }

          if (typedMsg.type === 'mapping_added') {
            const { mapping } = typedMsg;
            const actorName = typedMsg.actor_name || 'Un usuario';

            // Variable para rastrear si realmente agregamos el mapping
            let wasAdded = false;

            // Agregar el mapping al estado local
            setMappings((prev) => {
              // Verificar que no exista ya (evitar duplicados)
              const exists = prev.some(m =>
                m.origin_table === mapping.origin_table &&
                m.origin_column === mapping.origin_column &&
                m.destination_table === mapping.destination_table &&
                m.destination_column === mapping.destination_column
              );

              if (exists) {
                console.log('[TwoColumnView] Mapping already exists, skipping');
                return prev;
              }

              console.log('[TwoColumnView] Adding new mapping to state');
              wasAdded = true;

              return [...prev, mapping as Mapping];
            });

            // Notificar al usuario solo cuando se agrega un mapping nuevo Y no es tu propia acción
            if (wasAdded && !isOwnAction) {
              toast.success(`${actorName} creó un mapeo: ${mapping.origin_table}.${mapping.origin_column} → ${mapping.destination_table}.${mapping.destination_column}`, {
                duration: 3000,
              });
            }
          } else if (typedMsg.type === 'mapping_deleted') {
            const { mapping } = typedMsg;
            const actorName = typedMsg.actor_name || 'Un usuario';

            console.log('[TwoColumnView] Deleting mapping from state');

            // Eliminar el mapping del estado local
            setMappings((prev) => prev.filter(m =>
              !(m.origin_table === mapping.origin_table &&
                m.origin_column === mapping.origin_column &&
                m.destination_table === mapping.destination_table &&
                m.destination_column === mapping.destination_column)
            ));

            // Notificar al usuario solo si no es tu propia acción
            if (!isOwnAction) {
              toast.custom(`🗑️ ${actorName} eliminó un mapeo: ${mapping.origin_table}.${mapping.origin_column} → ${mapping.destination_table}.${mapping.destination_column}`, {
                duration: 3000,
              });
            }
          }
        });

        console.log('[TwoColumnView] Subscribed to mapping events');
      } catch (error) {
        console.error('[TwoColumnView] Error connecting to WebSocket:', error);
        toast.error(getApiError(error, t));
      }
    };

    connectAndSubscribe();

    // Cleanup al desmontar
    return () => {
      if (unsubscribe) {
        console.log('[TwoColumnView] Unsubscribing from mapping events');
        unsubscribe();
      }
      if (connectionCheckInterval) {
        clearInterval(connectionCheckInterval);
      }
      setIsWebSocketConnected(false);
    };
  }, [projectId]);

  const handleToggleExpand = useCallback((nodeId: string) => {
    setExpandedNodes(prev => {
      const isCurrentlyExpanded = prev[nodeId] !== false;
      return { ...prev, [nodeId]: !isCurrentlyExpanded };
    });
  }, []);

  //  Callback para cambios de búsqueda en tablas individuales
  const handleTableSearchChange = useCallback((tableName: string, searchTerm: string) => {
    setTableSearchTerms(prev => ({
      ...prev,
      [tableName]: searchTerm
    }));
  }, []);

  //  Callback para manejar click en atributo
  const handleAttributeClick = useCallback((tableName: string, columnName: string) => {
    setSelectedAttribute(prev => {
      // Si ya está seleccionado el mismo atributo, deseleccionar
      if (prev?.tableName === tableName && prev?.columnName === columnName) {
        return null;
      }
      // Seleccionar el nuevo atributo
      return { tableName, columnName };
    });
  }, []);

  //  Callback para manejar click en edge
  const handleEdgeClick = useCallback((event: React.MouseEvent, edge: Edge) => {
    event.stopPropagation();
    setSelectedEdgeId(edge.id);
    setSelectedAttribute(null); // Limpiar selección de atributo si había una
  }, []);

  //  Callback para desmarcar al hacer click en el canvas
  const handlePaneClick = useCallback(() => {
    setSelectedAttribute(null);
    setSelectedEdgeId(null);
  }, []);

  // Callback para refrescar después de operaciones CRUD
  const handleRefreshAfterCRUD = useCallback(() => {
    closeModal();
    onRefresh();
  }, [closeModal, onRefresh]);

  //  CRÍTICO: Memoizar handleDeleteMapping con useCallback
  const handleDeleteMapping = useCallback(async (mapping: Mapping) => {
    try {
      await mappingService.deleteMapping(mapping);
      setMappings((prev) => prev.filter((m) =>
        !(m.origin_table === mapping.origin_table &&
          m.origin_column === mapping.origin_column &&
          m.destination_table === mapping.destination_table &&
          m.destination_column === mapping.destination_column)
      ));
      toast.success("Mapeo eliminado");
      // No llamar a onRefresh() para evitar re-render completo y zoom reset
    } catch (error) {
      console.error("Error deleting mapping:", error);
      toast.error(getApiError(error, t));
    }
  }, [t]);

  // Handlers para preload de modales (cuando se hace hover)
  const handlePreloadPKModal = useCallback(() => {
    preloadPrimaryKeyModal();
  }, []);

  const handlePreloadTableModal = useCallback(() => {
    preloadTableModal();
  }, []);

  const handlePreloadColumnModal = useCallback(() => {
    preloadColumnModal();
  }, []);

  const handlePreloadDeleteTableModal = useCallback(() => {
    preloadDeleteTableModal();
  }, []);

  const handlePreloadDeleteColumnModal = useCallback(() => {
    preloadDeleteColumnModal();
  }, []);

  // Handler para abrir modal de Primary Key
  const handleOpenPKModal = useCallback((table: TableWithColumns) => {
    setPkModalState({ isOpen: true, table });
  }, []);

  // Handler para cerrar modal de Primary Key
  const handleClosePKModal = useCallback(() => {
    setPkModalState({ isOpen: false, table: null });
  }, []);

  // Handler para cuando se configura exitosamente una PK
  const handlePKSuccess = useCallback(() => {
    onRefresh(); // Refrescar datos para obtener la nueva configuración de PK
    handleClosePKModal();
  }, [onRefresh]);

  //  CRÍTICO: Memoizar onConnect con useCallback - Conexión optimista
  const onConnect = useCallback(async (connection: Connection) => {
    if (!connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) return;

    console.log('[TwoColumnView] Creating mapping from connection:', {
      sourceHandle: connection.sourceHandle,
      targetHandle: connection.targetHandle
    });

    const [originTable, originColumn] = connection.sourceHandle.split('::');
    const [destTable, destColumn] = connection.targetHandle.split('::');

    console.log('[TwoColumnView] Parsed handles:', {
      originTable,
      originColumn,
      destTable,
      destColumn
    });

    // Detectar si alguna tabla es connector y añadir hashes al mapping
    const originTableObj = tables.find(t => t.name === originTable);
    const destTableObj = tables.find(t => t.name === destTable);
    const originColObj = originTableObj?.columns.find(c => c.name === originColumn);
    const destColObj = destTableObj?.columns.find(c => c.name === destColumn);

    const optimisticMapping: Mapping = {
      project_id: projectId,
      origin_table: originTable,
      origin_column: originColumn,
      destination_table: destTable,
      destination_column: destColumn,
      ...(originTableObj?.is_connector && {
        origin_source_type: 'connector' as const,
        origin_table_hash: originTableObj.table_hash,
        origin_column_hash: originColObj?.column_hash,
        origin_session_id: originTableObj.session_id,
      }),
      ...(destTableObj?.is_connector && {
        destination_source_type: 'connector' as const,
        destination_table_hash: destTableObj.table_hash,
        destination_column_hash: destColObj?.column_hash,
        destination_session_id: destTableObj.session_id,
      }),
    };

    console.log('[TwoColumnView] Optimistic mapping to send:', optimisticMapping);

    //  Agregar mapping optimista inmediatamente (visual)
    setMappings((prev) => [...prev, optimisticMapping]);

    try {
      //  Crear en servidor en background
      const created = await mappingService.createMapping(optimisticMapping);

      //  Reemplazar el mapping optimista con el real del servidor
      setMappings((prev) =>
        prev.map(m =>
          m.origin_table === optimisticMapping.origin_table &&
          m.origin_column === optimisticMapping.origin_column &&
          m.destination_table === optimisticMapping.destination_table &&
          m.destination_column === optimisticMapping.destination_column
            ? created
            : m
        )
      );

      toast.success("Mapeo creado");
      // No llamar a onRefresh() para evitar re-render completo y zoom reset
    } catch (error: unknown) {
      console.error("Error creating mapping:", error);

      //  Revertir el mapping optimista si falla
      setMappings((prev) =>
        prev.filter(m =>
          !(m.origin_table === optimisticMapping.origin_table &&
            m.origin_column === optimisticMapping.origin_column &&
            m.destination_table === optimisticMapping.destination_table &&
            m.destination_column === optimisticMapping.destination_column)
        )
      );

      // Mostrar el mensaje de error del backend
      const errObj = error as Record<string, unknown>;
      const errorMessage = (error instanceof Error ? error.message : null) || String(errObj.detail ?? '') || "Error al crear mapeo";
      toast.error(errorMessage);
    }
  }, [projectId, onRefresh]);


  //  Memoizar listas de tablas para filtros (con búsqueda deferred para mejor performance)
  const filteredOriginTableNames = useMemo(() => {
    const allOrigins = tables.filter(t => t.type === 'origin').map(t => t.name);
    if (deferredSearchOrigin) {
      return allOrigins.filter(name =>
        name.toLowerCase().includes(deferredSearchOrigin.toLowerCase())
      ).sort();
    }
    return allOrigins.sort();
  }, [tables, deferredSearchOrigin]);

  const filteredDestTableNames = useMemo(() => {
    const allDests = tables.filter(t => t.type === 'destination').map(t => t.name);
    if (deferredSearchDestination) {
      return allDests.filter(name =>
        name.toLowerCase().includes(deferredSearchDestination.toLowerCase())
      ).sort();
    }
    return allDests.sort();
  }, [tables, deferredSearchDestination]);

  //  OPTIMIZACIÓN CLAVE: Separar el filtrado de tablas del cálculo de nodes/edges
  const filteredTables = useMemo(() => {
    let originTables = tables.filter((t) => t.type === "origin");
    let destTables = tables.filter((t) => t.type === "destination");

    if (deferredSearchOrigin) {
      originTables = originTables.filter(t =>
        t.name.toLowerCase().includes(deferredSearchOrigin.toLowerCase()) ||
        t.columns.some(c => c.name.toLowerCase().includes(deferredSearchOrigin.toLowerCase()))
      );
    }

    if (deferredSearchDestination) {
      destTables = destTables.filter(t =>
        t.name.toLowerCase().includes(deferredSearchDestination.toLowerCase()) ||
        t.columns.some(c => c.name.toLowerCase().includes(deferredSearchDestination.toLowerCase()))
      );
    }

    if (filterState.onlyMapped) {
      const mappedOrigins = new Set(mappings.map(m => m.origin_table));
      const mappedDests = new Set(mappings.map(m => m.destination_table));

      originTables = originTables.filter(t => mappedOrigins.has(t.name));
      destTables = destTables.filter(t => mappedDests.has(t.name));
    }

    if (filterState.selectedOrigins.length > 0) {
      originTables = originTables.filter(t => filterState.selectedOrigins.includes(t.name));
    }
    if (filterState.selectedDestinations.length > 0) {
      destTables = destTables.filter(t => filterState.selectedDestinations.includes(t.name));
    }

    const MAX_TABLES_PER_SIDE = 20;
    return {
      originTables: originTables.slice(0, MAX_TABLES_PER_SIDE),
      destTables: destTables.slice(0, MAX_TABLES_PER_SIDE),
      stats: {
        totalOrigin: originTables.length,
        totalDest: destTables.length,
        showingOrigin: Math.min(originTables.length, MAX_TABLES_PER_SIDE),
        showingDest: Math.min(destTables.length, MAX_TABLES_PER_SIDE),
        hiddenOrigin: Math.max(0, originTables.length - MAX_TABLES_PER_SIDE),
        hiddenDest: Math.max(0, destTables.length - MAX_TABLES_PER_SIDE),
      }
    };
  }, [tables, deferredSearchOrigin, deferredSearchDestination, filterState.onlyMapped, filterState.selectedOrigins, filterState.selectedDestinations, mappings]);

  //  OPTIMIZACIÓN: Crear nodes solo cuando cambian las tablas filtradas, NO cuando cambian mappings
  const { nodes, edges } = useMemo(() => {
    const { originTables, destTables } = filteredTables;

    //  Los nodos se crean con datos estables
    const nodes: Node<TableNodeData>[] = [
      ...originTables.map((table) => ({
        id: `origin-${table.id}`,
        type: 'tableNode' as const,
        position: { x: 0, y: 0 },
        data: {
          table,
          type: 'origin' as const,
          mappings, //  Pasamos mappings aquí, pero el node debería memoizarse con React.memo
          projectId,
          onDeleteMapping: handleDeleteMapping,
          onSearchChange: handleTableSearchChange,
          // Connector tables son read-only: sin edición de estructura
          onEditTable: table.is_connector ? undefined : openEditTableModal,
          onDeleteTable: table.is_connector ? undefined : openDeleteTableModal,
          onAddColumn: table.is_connector ? undefined : openCreateColumnModal,
          onEditColumn: table.is_connector ? undefined : openEditColumnModal,
          onDeleteColumn: table.is_connector ? undefined : openDeleteColumnModal,
          onDefinePrimaryKey: table.is_connector ? undefined : handleOpenPKModal,
          onPreloadPrimaryKey: handlePreloadPKModal,
          onPreloadTableModal: handlePreloadTableModal,
          onPreloadColumnModal: handlePreloadColumnModal,
          onPreloadDeleteTableModal: handlePreloadDeleteTableModal,
          onPreloadDeleteColumnModal: handlePreloadDeleteColumnModal,
          onAttributeClick: handleAttributeClick,
          selectedAttribute,
          isExpanded: expandedNodes[`origin-${table.id}`] !== false,
          onToggleExpand: handleToggleExpand,
        },
      })),
      ...destTables.map((table) => ({
        id: `destination-${table.id}`,
        type: 'tableNode' as const,
        position: { x: 0, y: 0 },
        data: {
          table,
          type: 'destination' as const,
          mappings,
          projectId,
          onDeleteMapping: handleDeleteMapping,
          onSearchChange: handleTableSearchChange,
          onEditTable: table.is_connector ? undefined : openEditTableModal,
          onDeleteTable: table.is_connector ? undefined : openDeleteTableModal,
          onAddColumn: table.is_connector ? undefined : openCreateColumnModal,
          onEditColumn: table.is_connector ? undefined : openEditColumnModal,
          onDeleteColumn: table.is_connector ? undefined : openDeleteColumnModal,
          onDefinePrimaryKey: table.is_connector ? undefined : handleOpenPKModal,
          onPreloadPrimaryKey: handlePreloadPKModal,
          onPreloadTableModal: handlePreloadTableModal,
          onPreloadColumnModal: handlePreloadColumnModal,
          onPreloadDeleteTableModal: handlePreloadDeleteTableModal,
          onPreloadDeleteColumnModal: handlePreloadDeleteColumnModal,
          onAttributeClick: handleAttributeClick,
          selectedAttribute,
          isExpanded: expandedNodes[`destination-${table.id}`] !== false,
          onToggleExpand: handleToggleExpand,
        },
      })),
    ];

    const visibleOriginNames = new Set(originTables.map(t => t.name));
    const visibleDestNames = new Set(destTables.map(t => t.name));

    //  Filtrar edges según búsquedas en tablas individuales
    const shouldShowEdge = (mapping: Mapping) => {
      const originSearch = tableSearchTerms[mapping.origin_table]?.toLowerCase() || '';
      const destSearch = tableSearchTerms[mapping.destination_table]?.toLowerCase() || '';

      // Si hay búsqueda en origen, verificar que la columna coincida
      if (originSearch && !mapping.origin_column.toLowerCase().includes(originSearch)) {
        return false;
      }

      // Si hay búsqueda en destino, verificar que la columna coincida
      if (destSearch && !mapping.destination_column.toLowerCase().includes(destSearch)) {
        return false;
      }

      return true;
    };

    //  Los edges se filtran y crean eficientemente
    const edges: Edge[] = mappings
      .filter(m => visibleOriginNames.has(m.origin_table) && visibleDestNames.has(m.destination_table))
      .filter(shouldShowEdge)
      .map((mapping) => {
        const sourceTable = originTables.find(t => t.name === mapping.origin_table);
        const targetTable = destTables.find(t => t.name === mapping.destination_table);

        if (!sourceTable || !targetTable) return null;

        const sourceHandleId = `${mapping.origin_table}::${mapping.origin_column}`;
        const targetHandleId = `${mapping.destination_table}::${mapping.destination_column}`;

        const edgeId = `${sourceHandleId}--${targetHandleId}`;

        return {
          id: edgeId,
          source: `origin-${sourceTable.id}`,
          target: `destination-${targetTable.id}`,
          sourceHandle: sourceHandleId,
          targetHandle: targetHandleId,
          type: 'custom',
          animated: false,
          selected: selectedEdgeId === edgeId,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 20,
            height: 20,
          },
          data: {
            mapping,
            onDelete: handleDeleteMapping,
            isConnecting,
            selectedAttribute,
          },
        };
      })
      .filter(Boolean) as Edge[];

    return getLayoutedElements(nodes, edges, expandedNodes);
  }, [
    filteredTables,
    mappings,
    handleDeleteMapping,
    handleTableSearchChange,
    tableSearchTerms,
    openEditTableModal,
    openDeleteTableModal,
    openCreateColumnModal,
    openEditColumnModal,
    openDeleteColumnModal,
    handleOpenPKModal,
    handlePreloadPKModal,
    handlePreloadTableModal,
    handlePreloadColumnModal,
    handlePreloadDeleteTableModal,
    handlePreloadDeleteColumnModal,
    projectId,
    isConnecting,
    handleAttributeClick,
    selectedAttribute,
    selectedEdgeId,
    expandedNodes,
    handleToggleExpand,
  ]);

  //  Auto-centrado del viewport solo en montaje inicial
  const hasInitializedViewport = React.useRef(false);

  useEffect(() => {
    if (nodes.length > 0 && !hasInitializedViewport.current) {
      hasInitializedViewport.current = true;
      setTimeout(() => {
        const firstOrigin = nodes.find(n => n.id.startsWith('origin-'));
        const firstDest = nodes.find(n => n.id.startsWith('destination-'));

        if (firstOrigin && firstDest) {
          // Calcular el punto medio entre las dos primeras tablas
          const centerX = (firstOrigin.position.x + firstDest.position.x) / 2;
          // Posicionar la vista para que la parte superior de las tablas esté visible
          const centerY = firstOrigin.position.y - 50; // Ajustar para ver desde arriba

          reactFlowInstance.setCenter(centerX, centerY, {
            zoom: 0.9, // Zoom óptimo para ver tablas grandes pero completas
            duration: 300,
          });
        } else {
          // Si no hay pares, centrar en la primera tabla que encuentre
          const firstNode = nodes[0];
          if (firstNode) {
            reactFlowInstance.setCenter(firstNode.position.x + 160, firstNode.position.y + 100, {
              zoom: 0.9,
              duration: 300,
            });
          }
        }
      }, 200);
    }
  }, [nodes.length, reactFlowInstance]);

  //  Memoizar stats para el panel
  const stats = filteredTables.stats;

  //  CRÍTICO: Memoizar nodeTypes y edgeTypes para evitar recreación
  const nodeTypes = useMemo(() => NODE_TYPES, []);
  const edgeTypes = useMemo(() => EDGE_TYPES, []);

  // Manejador de movimiento del cursor
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();

    // Coordenadas absolutas en el viewport del navegador
    const screenX = e.clientX - rect.left;
    const screenY = e.clientY - rect.top;

    // Convertir coordenadas de pantalla a coordenadas del canvas de ReactFlow
    // Fórmula: canvasCoord = (screenCoord - viewportPosition) / zoom
    const canvasX = (screenX - viewport.x) / viewport.zoom;
    const canvasY = (screenY - viewport.y) / viewport.zoom;

    // Enviar coordenadas del canvas junto con información del viewport
    // El hook agregará automáticamente user_id y username del usuario actual
    broadcastCursorPosition({
      user_id: '', // Se agregará automáticamente por el servicio
      username: '', // Se agregará automáticamente por el servicio
      x: canvasX,
      y: canvasY,
      viewport: {
        x: viewport.x,
        y: viewport.y,
        zoom: viewport.zoom
      },
      timestamp: new Date().toISOString()
    });
  }, [broadcastCursorPosition, viewport]);

  // Manejador de salida del cursor
  const handleMouseLeave = useCallback(() => {
    broadcastCursorLeave();
  }, [broadcastCursorLeave]);

  return (
    <div
      className="h-full flex flex-col relative"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      {/* Indicador de conexión - movido a abajo a la derecha para evitar superposición con filtros */}
      <div className="absolute bottom-4 right-4 z-50 px-3 py-2 rounded-md text-xs font-medium bg-card border border-border shadow-lg">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isWebSocketConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
          <span>{isWebSocketConnected ? 'Conectado' : 'Desconectado'}</span>
          {cursors.length > 0 && (
            <span className="text-muted-foreground">
              | {cursors.length} cursor{cursors.length > 1 ? 'es' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Cursores colaborativos */}
      <CollaborativeCursors cursors={cursors} />

      {/* Menú contextual en el canvas para crear tablas */}
      <ContextMenu>
        <ContextMenuTrigger asChild>
          <div className="h-full">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onConnect={onConnect}
              onConnectStart={() => setIsConnecting(true)}
              onConnectEnd={() => setIsConnecting(false)}
              onPaneClick={handlePaneClick}
              onEdgeClick={handleEdgeClick}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              connectionLineType={ConnectionLineType.Bezier}
              connectionLineStyle={connectionLineStyle}
              minZoom={0.1}
              maxZoom={1.5}
              defaultViewport={{ x: 0, y: 0, zoom: 1 }}
              proOptions={{ hideAttribution: true }}
              panOnScroll={true}
              selectionOnDrag={false}
              panOnDrag={true}
              zoomOnDoubleClick={false}
              connectionRadius={30}
              snapGrid={snapGrid}
              deleteKeyCode="Delete"
              defaultEdgeOptions={defaultEdgeOptions}
              //  IMPORTANTE: Solo renderizar elementos visibles (mejora mucho con 180 tablas)
              onlyRenderVisibleElements={true}
            >
        <Background gap={16} size={1} />

        {/* Panel de búsqueda y filtros */}
        <Panel position="top-left">
          <div className="bg-card border border-border rounded-lg shadow-lg max-h-[80vh] overflow-y-auto filter-panel-scroll">
            {!filterState.showFilters ? (
              <button
                onClick={() => dispatchFilter({ type: 'TOGGLE_FILTERS' })}
                className="p-2 rounded-md bg-transparent border-none cursor-pointer transition-colors hover:bg-muted flex items-center justify-center"
                title="Mostrar filtros"
              >
                <Filter className="w-4 h-4" />
              </button>
            ) : (
              <div className="p-3 flex flex-col gap-3 min-w-[280px]">
                {/* Header con botón de filtros */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => dispatchFilter({ type: 'TOGGLE_FILTERS' })}
                    className="p-1.5 rounded-md bg-muted border-none cursor-pointer transition-colors hover:bg-muted/80 flex items-center justify-center"
                    title="Ocultar filtros"
                  >
                    <Filter className="w-4 h-4" />
                  </button>
                  <span className="text-xs font-semibold">Filtros</span>
                </div>

                {/* Advertencia de tablas ocultas */}
                {(stats.hiddenOrigin > 0 || stats.hiddenDest > 0) && (
                  <div className="text-xs bg-yellow-50 dark:bg-yellow-950/20 text-yellow-700 dark:text-yellow-300 px-2 py-2 rounded-md">
                    ⚠️ {stats.hiddenOrigin + stats.hiddenDest} tablas ocultas. Usa filtros para verlas.
                  </div>
                )}

                {/* Contenido expandido */}
                <div className="flex flex-col gap-3 pt-2 border-t border-border">
                {/* Checkbox de solo mapeados */}
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="onlyMapped"
                    checked={filterState.onlyMapped}
                    onChange={(e) => dispatchFilter({ type: 'SET_ONLY_MAPPED', payload: e.target.checked })}
                    className="checkbox-dark"
                  />
                  <label htmlFor="onlyMapped" className="text-sm cursor-pointer">
                    Solo tablas con mapeos
                  </label>
                </div>

                {/* Sección de Origen */}
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0"></div>
                    <span className="text-xs font-semibold">Tablas origen</span>
                  </div>

                  <div className="flex items-center gap-1.5 px-2 py-2 text-xs border border-border rounded-md bg-background">
                    <Search className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                    <input
                      type="text"
                      placeholder="Buscar origen..."
                      value={filterState.searchOrigin}
                      onChange={(e) => dispatchFilter({ type: 'SET_SEARCH_ORIGIN', payload: e.target.value })}
                      className="flex-1 bg-transparent outline-none min-w-0"
                    />
                  </div>

                  <select
                    multiple
                    value={filterState.selectedOrigins}
                    onChange={(e) => {
                      const selected = Array.from(e.target.selectedOptions, option => option.value);
                      dispatchFilter({ type: 'SET_SELECTED_ORIGINS', payload: selected });
                    }}
                    className="w-full text-xs border border-border rounded-md bg-background text-foreground p-1 max-h-[120px] overflow-y-auto"
                    size={5}
                  >
                    {filteredOriginTableNames.length === 0 ? (
                      <option disabled>No hay resultados</option>
                    ) : (
                      filteredOriginTableNames.map(name => (
                        <option key={name} value={name}>{name}</option>
                      ))
                    )}
                  </select>

                  {filterState.selectedOrigins.length > 0 && (
                    <button
                      onClick={() => dispatchFilter({ type: 'CLEAR_ORIGIN_SELECTION' })}
                      className="text-xs text-blue-500 hover:underline text-left"
                    >
                      Limpiar ({filterState.selectedOrigins.length})
                    </button>
                  )}
                </div>

                {/* Sección de Destino */}
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-green-500 flex-shrink-0"></div>
                    <span className="text-xs font-semibold">Tablas destino</span>
                  </div>

                  <div className="flex items-center gap-1.5 px-2 py-2 text-xs border border-border rounded-md bg-background">
                    <Search className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                    <input
                      type="text"
                      placeholder="Buscar destino..."
                      value={filterState.searchDestination}
                      onChange={(e) => dispatchFilter({ type: 'SET_SEARCH_DESTINATION', payload: e.target.value })}
                      className="flex-1 bg-transparent outline-none min-w-0"
                    />
                  </div>

                  <select
                    multiple
                    value={filterState.selectedDestinations}
                    onChange={(e) => {
                      const selected = Array.from(e.target.selectedOptions, option => option.value);
                      dispatchFilter({ type: 'SET_SELECTED_DESTINATIONS', payload: selected });
                    }}
                    className="w-full text-xs border border-border rounded-md bg-background text-foreground p-1 max-h-[120px] overflow-y-auto"
                    size={5}
                  >
                    {filteredDestTableNames.length === 0 ? (
                      <option disabled>No hay resultados</option>
                    ) : (
                      filteredDestTableNames.map(name => (
                        <option key={name} value={name}>{name}</option>
                      ))
                    )}
                  </select>

                  {filterState.selectedDestinations.length > 0 && (
                    <button
                      onClick={() => dispatchFilter({ type: 'CLEAR_DESTINATION_SELECTION' })}
                      className="text-xs text-blue-500 hover:underline text-left"
                    >
                      Limpiar ({filterState.selectedDestinations.length})
                    </button>
                  )}
                </div>

                  {/* Limpiar todos los filtros */}
                  <button
                    onClick={() => dispatchFilter({ type: 'CLEAR_ALL_FILTERS' })}
                    className="text-xs text-red-500 hover:underline text-center w-full py-1"
                  >
                    Limpiar todos los filtros
                  </button>
                </div>
              </div>
            )}
          </div>
        </Panel>
      </ReactFlow>
    </div>
  </ContextMenuTrigger>
  <ContextMenuContent>
    <ContextMenuItem
      onClick={openCreateTableModal}
      onMouseEnter={handlePreloadTableModal}
    >
      <Plus className="w-4 h-4 mr-2" />
      Nueva Tabla
    </ContextMenuItem>
  </ContextMenuContent>
</ContextMenu>

      {/* Modales con lazy loading */}
      <Suspense fallback={null}>
        <TableModal
          isOpen={modalState.type === 'create-table' || modalState.type === 'edit-table'}
          onClose={closeModal}
          projectId={projectId}
          table={modalState.table}
          onSuccess={handleRefreshAfterCRUD}
        />

        <ColumnModal
          isOpen={modalState.type === 'create-column' || modalState.type === 'edit-column'}
          onClose={closeModal}
          projectId={projectId}
          tableId={modalState.tableId || ''}
          tableName={modalState.tableName || ''}
          tableType={modalState.tableType || 'origin'}
          column={modalState.column}
          onSuccess={handleRefreshAfterCRUD}
        />

        <DeleteTableModal
          isOpen={modalState.type === 'delete-table'}
          onClose={closeModal}
          projectId={projectId}
          table={modalState.table || null}
          onSuccess={handleRefreshAfterCRUD}
        />

        <DeleteColumnModal
          isOpen={modalState.type === 'delete-column'}
          onClose={closeModal}
          projectId={projectId}
          column={modalState.column || null}
          tableName={modalState.tableName || ''}
          onSuccess={handleRefreshAfterCRUD}
        />

        <PrimaryKeyModalLazy
          isOpen={pkModalState.isOpen}
          onClose={handleClosePKModal}
          projectId={projectId}
          tableId={pkModalState.table?.id || ''}
          tableName={pkModalState.table?.name || ''}
          columns={pkModalState.table?.columns || []}
          onSuccess={handlePKSuccess}
        />
      </Suspense>
    </div>
  );
};

export const TwoColumnMappingView: React.FC<TwoColumnMappingViewProps> = (props) => {
  return (
    <ReactFlowProvider>
      <TwoColumnMappingViewInner {...props} />
    </ReactFlowProvider>
  );
};