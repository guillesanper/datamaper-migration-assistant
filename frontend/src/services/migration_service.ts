import { apiService } from "./api.service";

export interface RecentMigration {
  execution_id: string;
  project_id: string;
  project_name: string;
  status: "running" | "success" | "failed" | "pending";
  started_at: string;
  completed_at: string | null;
}

export interface GenerateScriptOptions {
  batch_size?: number;
  include_constraints?: boolean;
  include_validation?: boolean;
  dialect: "postgresql" | "mysql" | "sqlserver" | "oracle";
  /** Sesiones de conexión con las que resolver mappings de BD conectada */
  origin_connection_session_id?: string;
  dest_connection_session_id?: string;
}

export interface GeneratedScript {
  script_id: string;
  script: string;
  estimated_duration_seconds: number;
  estimated_rows: number;
  dependency_order: string[];
  created_at: string;
}

export interface ExecutionRequest {
  script_id?: string;
  dry_run: boolean;
  dest_connection_session_id: string;
  /** Si el origen es otra BD, el backend copia los datos por lotes */
  origin_connection_session_id?: string;
}

export interface ExecutionStarted {
  execution_id: string;
  status: string;
  message: string;
}

export interface ExecutionStatus {
  execution_id: string;
  status: "pending" | "running" | "success" | "failed" | "rolled_back" | "dry_run_complete";
  progress_percent: number;
  rows_migrated: number;
  estimated_remaining_seconds: number | null;
  current_step: string | null;
  execution_log: Array<{
    step: number;
    type?: string;
    table?: string;
    rows?: number;
    duration?: number;
    status?: string;
    total_statements?: number;
  }>;
  errors: string | null;
}

export interface ExecutionListItem {
  execution_id: string;
  status: string;
  rows_migrated: number;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  dry_run: boolean;
}

export interface ExecutionList {
  executions: ExecutionListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface DependencyGraph {
  execution_order: string[];
  circular_dependencies: string[][];
  independent_tables: string[];
  graph_visualization: Record<string, string[]>;
}

class MigrationService {
  async getRecentMigrations(limit = 5): Promise<RecentMigration[]> {
    return apiService.get<RecentMigration[]>(
      `/api/migrations/recent?limit=${limit}`
    );
  }

  async generateScript(
    projectId: string,
    options?: GenerateScriptOptions
  ): Promise<GeneratedScript> {
    return apiService.post<GeneratedScript>(
      `/api/projects/${projectId}/migration/generate-script`,
      options ?? {}
    );
  }

  async executeScript(
    projectId: string,
    body: ExecutionRequest
  ): Promise<ExecutionStarted> {
    return apiService.post<ExecutionStarted>(
      `/api/projects/${projectId}/migration/execute`,
      body
    );
  }

  async getExecutionStatus(
    projectId: string,
    executionId: string
  ): Promise<ExecutionStatus> {
    return apiService.get<ExecutionStatus>(
      `/api/projects/${projectId}/migration/executions/${executionId}`
    );
  }

  async listExecutions(
    projectId: string,
    params?: { status_filter?: string; limit?: number; offset?: number }
  ): Promise<ExecutionList> {
    const query = new URLSearchParams();
    if (params?.status_filter) query.set("status_filter", params.status_filter);
    if (params?.limit !== undefined) query.set("limit", String(params.limit));
    if (params?.offset !== undefined) query.set("offset", String(params.offset));
    const qs = query.toString();
    return apiService.get<ExecutionList>(
      `/api/projects/${projectId}/migration/executions${qs ? `?${qs}` : ""}`
    );
  }

  async getDependencyGraph(
    projectId: string,
    destSessionId?: string
  ): Promise<DependencyGraph> {
    const qs = destSessionId ? `?dest_session_id=${encodeURIComponent(destSessionId)}` : "";
    return apiService.get<DependencyGraph>(
      `/api/projects/${projectId}/migration/dependency-graph${qs}`
    );
  }
}

export const migrationService = new MigrationService();
