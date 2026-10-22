// src/pages/ProjectMapping.tsx
import React, { useState, useEffect, useMemo, useCallback, lazy, Suspense } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { Layers, TableIcon, Grid3x3, Upload, Download, RefreshCw, History, Maximize2, Minimize2, Database, Play } from "../components/icons";
import { mappingService } from "../services/mapping_service";
import { projectService } from "../services/project_service";
import { encryptionService } from "../services/encryption.service";
import { dbConnectionService } from "../services/db_connection.service";
import type { ConnectorTable } from "../types/db_connection_types";
import { useEncryption } from "../providers/EncryptionProvider";
import { EncryptionUnlockModal } from "../components/encryption/EncryptionUnlockModal";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { LoadingSpinner } from "../components/ui/LoadingSpinner";
import type { TableWithColumns, Mapping } from "../types/mapping-types";
import type { Project } from "../types/project_types";
import { toast } from "../utils/toast";
import { useFullscreen } from "../contexts/FullscreenContext";
import styles from "../styles/mapping/mapping.module.css";

// Lazy load view components with preload functions
const TwoColumnMappingView = lazy(() =>
  import("../components/mapping/TwoColumnView").then(m => ({ default: m.TwoColumnMappingView }))
);
const preloadTwoColumnView = () => import("../components/mapping/TwoColumnView");

const SidebarCanvasView = lazy(() =>
  import("../components/mapping/SidebarCanvasView").then(m => ({ default: m.SidebarCanvasView }))
);
const preloadSidebarView = () => import("../components/mapping/SidebarCanvasView");

const GridTableView = lazy(() =>
  import("../components/mapping/GridTableView").then(m => ({ default: m.GridTableView }))
);
const preloadGridView = () => import("../components/mapping/GridTableView");

const ImportModal = lazy(() =>
  import("../components/mapping/ImportModal").then(m => ({ default: m.ImportModal }))
);
const preloadImportModal = () => import("../components/mapping/ImportModal");

const ExportModal = lazy(() =>
  import("../components/mapping/ExportModal").then(m => ({ default: m.ExportModal }))
);
const preloadExportModal = () => import("../components/mapping/ExportModal");

const DatabaseConnectionModal = lazy(() =>
  import("../components/mapping/modals/DatabaseConnectionModal").then(m => ({ default: m.DatabaseConnectionModal }))
);
const preloadDatabaseConnectionModal = () => import("../components/mapping/modals/DatabaseConnectionModal");

const MigrationModal = lazy(() =>
  import("../components/mapping/MigrationModal").then(m => ({ default: m.MigrationModal }))
);

type ViewMode = "two-column" | "sidebar-canvas" | "grid-table";

export const ProjectMapping: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [viewMode, setViewMode] = useState<ViewMode>("two-column");
  const [project, setProject] = useState<Project | null>(null);
  const [tables, setTables] = useState<TableWithColumns[]>([]);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);
  const [isDBConnectionModalOpen, setIsDBConnectionModalOpen] = useState(false);
  const [dbConnectionTargetType, setDbConnectionTargetType] = useState<'origin' | 'destination' | null>(null);
  const [isMigrationModalOpen, setIsMigrationModalOpen] = useState(false);
  const [activeDBSessions, setActiveDBSessions] = useState<{origin?: string, destination?: string}>({});
  const [connectorTables, setConnectorTables] = useState<ConnectorTable[]>([]);
  const { isFullscreen, toggleFullscreen } = useFullscreen();

  // Encryption state
  const [isEncryptionModalOpen, setIsEncryptionModalOpen] = useState(false);
  const { checkSessionStatus } = useEncryption();

  // Check encryption and load data
  useEffect(() => {
    if (projectId) {
      checkEncryptionAndLoad();
    }
  }, [projectId]);

  useEffect(() => {
    if (searchParams.get('action') === 'migrate') {
      setIsMigrationModalOpen(true);
    }
  }, []);

  const checkEncryptionAndLoad = async () => {
    if (!projectId) return;

    try {
      setIsLoading(true);

      // First, check if project has encryption enabled
      const status = await encryptionService.checkEncryptionStatus(projectId);

      if (status.encryption_enabled) {
        // Project is encrypted - check backend for valid session (restores from cookie)
        const hasValidSession = await checkSessionStatus(projectId);

        if (!hasValidSession) {
          // No valid session - show unlock modal and wait
          console.log('[ProjectMapping] No valid encryption session, showing unlock modal');
          setIsEncryptionModalOpen(true);
          setIsLoading(false);
          return;
        }

        console.log('[ProjectMapping] Valid encryption session restored, proceeding to load data');
      }

      // Either no encryption or valid session exists - load data
      await loadProjectData();
    } catch (error: unknown) {
      console.error('[ProjectMapping] Error checking encryption:', error);
      toast.error(error instanceof Error ? error.message : 'Error al verificar el cifrado del proyecto');
      setIsLoading(false);
    }
  };

  // Helpers para persistir sesiones de connector en localStorage
  const SESSIONS_KEY = (pid: string) => `relan:connector_sessions:${pid}`;

  const saveConnectorSessions = (pid: string, sessions: {origin?: string, destination?: string}) => {
    localStorage.setItem(SESSIONS_KEY(pid), JSON.stringify(sessions));
  };

  const loadConnectorSessions = (pid: string): {origin?: string, destination?: string} => {
    try {
      const raw = localStorage.getItem(SESSIONS_KEY(pid));
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  };

  const clearConnectorSession = (pid: string, type: 'origin' | 'destination') => {
    const sessions = loadConnectorSessions(pid);
    delete sessions[type];
    if (sessions.origin || sessions.destination) {
      localStorage.setItem(SESSIONS_KEY(pid), JSON.stringify(sessions));
    } else {
      localStorage.removeItem(SESSIONS_KEY(pid));
    }
  };

  const loadProjectData = useCallback(async () => {
    if (!projectId) return;

    try {
      setIsLoading(true);
      const [projectData, tablesData, mappingsData] = await Promise.all([
        projectService.getProjectById(projectId),
        mappingService.getTables(projectId),
        mappingService.getMappings(projectId),
      ]);

      setProject(projectData);
      setTables(tablesData);
      setMappings(mappingsData);

      // Restaurar connector tables de sesiones guardadas en localStorage
      const savedSessions = loadConnectorSessions(projectId);
      const restoredConnectorTables: ConnectorTable[] = [];
      const validSessions: {origin?: string, destination?: string} = {};

      for (const type of ['origin', 'destination'] as const) {
        const sessionId = savedSessions[type];
        if (!sessionId) continue;

        const isActive = await dbConnectionService.isSessionActive(sessionId);
        if (!isActive) {
          clearConnectorSession(projectId, type);
          continue;
        }

        try {
          const { tables } = await dbConnectionService.getConnectorTables(sessionId, type);
          restoredConnectorTables.push(...tables);
          validSessions[type] = sessionId;
        } catch (err) {
          console.warn(`[ProjectMapping] Error restoring connector tables for ${type}:`, err);
          clearConnectorSession(projectId, type);
        }
      }

      if (restoredConnectorTables.length > 0) {
        setConnectorTables(restoredConnectorTables);
        setActiveDBSessions(validSessions);
      }
    } catch (error) {
      console.error("Error loading project data:", error);
      toast.error("Error al cargar los datos del proyecto");
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  // Handle successful encryption unlock
  const handleEncryptionUnlock = async () => {
    console.log('[ProjectMapping] Encryption unlocked successfully, loading project data');
    setIsEncryptionModalOpen(false);
    await loadProjectData();
  };

  // Handle encryption modal close (user cancels)
  const handleEncryptionModalClose = () => {
    console.log('[ProjectMapping] User cancelled encryption unlock, navigating to dashboard');
    navigate('/dashboard');
  };

  // Handle successful database connection
  const handleDBConnectionSuccess = async (sessionId: string, tableType: 'origin' | 'destination') => {
    console.log(`[ProjectMapping] DB connection successful: ${sessionId} (${tableType})`);

    // Actualizar indicador de sesión activa
    const newSessions = { ...activeDBSessions, [tableType]: sessionId };
    setActiveDBSessions(newSessions);

    // Guardar sesión en localStorage para restaurar al recargar
    if (projectId) {
      saveConnectorSessions(projectId, newSessions);
    }

    // Cerrar modal
    setIsDBConnectionModalOpen(false);

    // Cargar tablas del connector (sin guardar estructura en BD local)
    try {
      const { tables: newConnectorTables, failedSchemas } =
        await dbConnectionService.getConnectorTables(sessionId, tableType);

      // Reemplazar tablas del mismo tipo en el estado (en caso de reconexión)
      setConnectorTables(prev => [
        ...prev.filter(t => t.type !== tableType),
        ...newConnectorTables,
      ]);

      toast.success(`Conectado como ${tableType}: ${newConnectorTables.length} tablas cargadas`);
      if (failedSchemas.length > 0) {
        toast.error(`No se pudieron leer los schemas: ${failedSchemas.join(', ')}`);
      }
    } catch (err) {
      console.error(`[ProjectMapping] Error loading connector tables:`, err);
      toast.error('Conexión creada pero no se pudieron cargar las tablas');
    }
  };

  // Listen for encryption session errors (expiration)
  useEffect(() => {
    const handleSessionError = (event: Event) => {
      const customEvent = event as CustomEvent;
      console.warn('[ProjectMapping] Encryption session error detected:', customEvent.detail);

      if (projectId && project?.encryption_enabled) {
        toast.error('Tu sesión de cifrado ha expirado. Por favor, desbloquea el proyecto nuevamente.');
        setIsEncryptionModalOpen(true);
      }
    };

    window.addEventListener('encryption-session-error', handleSessionError);

    return () => {
      window.removeEventListener('encryption-session-error', handleSessionError);
    };
  }, [projectId, project?.encryption_enabled]);

  // Memoize expensive calculations
  const viewModes = useMemo(() => [
    { id: "two-column" as ViewMode, name: "Dos Columnas", icon: Layers },
    { id: "sidebar-canvas" as ViewMode, name: "Canvas Interactivo", icon: Grid3x3 },
    { id: "grid-table" as ViewMode, name: "Tabla/Grid", icon: TableIcon },
  ], []);

  const originCount = useMemo(() => tables.filter((t) => t.type === "origin").length, [tables]);
  const destCount = useMemo(() => tables.filter((t) => t.type === "destination").length, [tables]);

  if (isLoading) {
    return <LoadingSpinner fullscreen size="lg" />;
  }

  // No mostrar botón de fullscreen en vista de grid
  const showFullscreenButton = viewMode !== "grid-table";

  return (
    <div className={styles.mappingContainer}>
      {/* Encryption Unlock Modal */}
      <EncryptionUnlockModal
        isOpen={isEncryptionModalOpen}
        onClose={handleEncryptionModalClose}
        onUnlock={handleEncryptionUnlock}
        projectId={projectId || ''}
        projectName={project?.name || 'Proyecto'}
      />

      {/* Botón de fullscreen flotante - No aparece en vista de grid */}
      {showFullscreenButton && (
        <button
          onClick={toggleFullscreen}
          className={`fixed ${isFullscreen ? 'top-4' : 'top-31'} right-4 z-50 p-2 bg-card border rounded-lg shadow-lg hover:bg-muted transition-all`}
          title={isFullscreen ? "Salir de pantalla completa" : "Pantalla completa"}
        >
          {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
        </button>
      )}

      {/* Header Ultra Compacto - TODO EN 1 LÍNEA - Se oculta en fullscreen */}
      {!isFullscreen && (
        <div className={styles.mappingHeaderCompact}>
        <div className={styles.mappingHeaderSingleLine}>
          {/* Título del proyecto */}
          <div className={styles.mappingHeaderInfo}>
            <h1 className={styles.mappingHeaderTitle}>{project?.name}</h1>
            <p className={styles.mappingHeaderSubtitle}>
              {project?.origin_db} → {project?.destination_db}
            </p>
          </div>

          {/* Stats con indicadores visuales */}
          <div className={styles.mappingStats}>
            <div className={styles.mappingStat}>
              <div className={`${styles.statDot} ${styles.statDotOrigin}`}></div>
              <span className={styles.statValue}>{originCount}</span>
              <span className={styles.statLabel}>origen</span>
            </div>
            <div className={styles.mappingStat}>
              <div className={`${styles.statDot} ${styles.statDotDestination}`}></div>
              <span className={styles.statValue}>{destCount}</span>
              <span className={styles.statLabel}>destino</span>
            </div>
            <div className={styles.mappingStat}>
              <span className={styles.statValue}>{mappings.length}</span>
              <span className={styles.statLabel}>mapeos</span>
            </div>
          </div>

          {/* Indicador de conexiones BD activas */}
          {(activeDBSessions.origin || activeDBSessions.destination) && (
            <>
              <div className={styles.headerDivider}></div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Conectado:</span>
                {activeDBSessions.origin && (
                  <div className="flex items-center gap-1 px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs">
                    <Database className="w-3 h-3" />
                    <span>Origen</span>
                  </div>
                )}
                {activeDBSessions.destination && (
                  <div className="flex items-center gap-1 px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded text-xs">
                    <Database className="w-3 h-3" />
                    <span>Destino</span>
                  </div>
                )}
              </div>
            </>
          )}

          {/* Divisor vertical */}
          <div className={styles.headerDivider}></div>

          {/* Selector de vista con Select */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground font-medium">Vista:</span>
            <Select value={viewMode} onValueChange={(value) => setViewMode(value as ViewMode)}>
              <SelectTrigger
                size="sm"
                className="w-[180px]"
                onMouseEnter={() => {
                  // Preload all views when user hovers over selector
                  preloadTwoColumnView();
                  preloadSidebarView();
                  preloadGridView();
                }}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {viewModes.map((mode) => {
                  const Icon = mode.icon;
                  return (
                    <SelectItem
                      key={mode.id}
                      value={mode.id}
                      onMouseEnter={() => {
                        // Preload specific view on hover
                        if (mode.id === 'two-column') preloadTwoColumnView();
                        else if (mode.id === 'sidebar-canvas') preloadSidebarView();
                        else if (mode.id === 'grid-table') preloadGridView();
                      }}
                    >
                      <span className="flex items-center gap-2">
                        <Icon className="w-4 h-4" />
                        {mode.name}
                      </span>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>

          {/* Divisor vertical */}
          <div className={styles.headerDivider}></div>

          {/* Selector de operaciones */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground font-medium">Operaciones:</span>
            <Select value="" onValueChange={(value) => {
              if (value === "import") setIsImportModalOpen(true);
              else if (value === "export") setIsExportModalOpen(true);
              else if (value === "db-connect-origin") { setDbConnectionTargetType('origin'); setIsDBConnectionModalOpen(true); }
              else if (value === "db-connect-destination") { setDbConnectionTargetType('destination'); setIsDBConnectionModalOpen(true); }
              else if (value === "versions") navigate(`/projects/${projectId}/versions`);
              else if (value === "refresh") loadProjectData();
              else if (value === "migration") setIsMigrationModalOpen(true);
            }}>
              <SelectTrigger
                size="sm"
                className="w-[160px]"
                onMouseEnter={() => {
                  // Preload modals when user hovers
                  preloadImportModal();
                  preloadExportModal();
                  preloadDatabaseConnectionModal();
                }}
              >
                <SelectValue placeholder="Seleccionar..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem
                  value="import"
                  onMouseEnter={() => preloadImportModal()}
                >
                  <span className="flex items-center gap-2">
                    <Download className="w-4 h-4" />
                    Importar
                  </span>
                </SelectItem>
                <SelectItem
                  value="export"
                  onMouseEnter={() => preloadExportModal()}
                >
                  <span className="flex items-center gap-2">
                    <Upload className="w-4 h-4" />
                    Exportar
                  </span>
                </SelectItem>
                <SelectItem
                  value="db-connect-origin"
                  onMouseEnter={() => preloadDatabaseConnectionModal()}
                >
                  <span className="flex items-center gap-2">
                    <Database className="w-4 h-4" />
                    Conectar Origen
                  </span>
                </SelectItem>
                <SelectItem
                  value="db-connect-destination"
                  onMouseEnter={() => preloadDatabaseConnectionModal()}
                >
                  <span className="flex items-center gap-2">
                    <Database className="w-4 h-4" />
                    Conectar Destino
                  </span>
                </SelectItem>
                <SelectItem value="versions">
                  <span className="flex items-center gap-2">
                    <History className="w-4 h-4" />
                    Versiones
                  </span>
                </SelectItem>
                <SelectItem value="refresh">
                  <span className="flex items-center gap-2">
                    <RefreshCw className="w-4 h-4" />
                    Recargar
                  </span>
                </SelectItem>
                <SelectItem value="migration">
                  <span className="flex items-center gap-2">
                    <Play className="w-4 h-4" />
                    Generar y ejecutar migración
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        </div>
      )}

      {/* View Content */}
      <div className={styles.mappingContent}>
        <Suspense fallback={<LoadingSpinner fullscreen size="md" />}>
          {viewMode === "two-column" && (
            <TwoColumnMappingView
              projectId={projectId!}
              project={project}
              tables={tables}
              mappings={mappings}
              onRefresh={loadProjectData}
              connectorTables={connectorTables}
            />
          )}
          {viewMode === "sidebar-canvas" && (
            <SidebarCanvasView
              projectId={projectId!}
              project={project}
              tables={tables}
              mappings={mappings}
              onRefresh={loadProjectData}
              connectorTables={connectorTables}
            />
          )}
          {viewMode === "grid-table" && (
            <GridTableView
              projectId={projectId!}
              project={project}
              tables={tables}
              mappings={mappings}
              onRefresh={loadProjectData}
              connectorTables={connectorTables}
            />
          )}
        </Suspense>
      </div>

      {/* Modals */}
      <Suspense fallback={null}>
        {isImportModalOpen && (
          <ImportModal
            isOpen={isImportModalOpen}
            onClose={() => setIsImportModalOpen(false)}
            projectId={projectId!}
            onSuccess={loadProjectData}
          />
        )}

        {isExportModalOpen && (
          <ExportModal
            isOpen={isExportModalOpen}
            onClose={() => setIsExportModalOpen(false)}
            projectId={projectId!}
          />
        )}

        <DatabaseConnectionModal
          isOpen={isDBConnectionModalOpen}
          onClose={() => { setIsDBConnectionModalOpen(false); setDbConnectionTargetType(null); }}
          projectId={projectId || ''}
          onSuccess={handleDBConnectionSuccess}
          targetType={dbConnectionTargetType ?? undefined}
        />

        <MigrationModal
          isOpen={isMigrationModalOpen}
          onClose={() => setIsMigrationModalOpen(false)}
          projectId={projectId || ''}
          destConnectionSessionId={activeDBSessions.destination ?? null}
          destinationDb={project?.destination_db}
        />
      </Suspense>
    </div>
  );
};
