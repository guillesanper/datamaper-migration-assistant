// src/services/db_connection.service.ts
import { apiService } from './api.service';
import type {
  DBConnectionConfig,
  DBConnectionTestResult,
  DBConnectionSessionResponse,
  SchemaMetadata,
  TableMetadata,
  ExternalDBTable,
  ExternalDBColumn,
  ConnectorTable,
  ConnectorTablesResponse,
} from '../types/db_connection_types';

/**
 * Servicio para gestionar conexiones a bases de datos externas
 */
class DBConnectionService {
  private readonly baseUrl = '/api/db-connections';

  /**
   * Probar conexión sin crear sesión
   */
  async testConnection(config: DBConnectionConfig): Promise<DBConnectionTestResult> {
    try {
      const response = await apiService.post<DBConnectionTestResult>(
        `${this.baseUrl}/test`,
        config
      );
      return response;
    } catch (error: unknown) {
      // Si el backend devuelve 400/422 con detalle de error
      const e = error as { response?: { data?: { detail?: string; message?: string; error_type?: string } } };
      if (e.response?.data) {
        return {
          success: false,
          dialect: config.dialect,
          host: config.host,
          database: config.database,
          error_message: e.response.data.detail || e.response.data.message || 'Error al probar la conexión',
          error_type: e.response.data.error_type || 'connection_error',
        };
      }

      throw error;
    }
  }

  /**
   * Crear sesión de conexión (persiste en Redis con TTL)
   */
  async createSession(
    config: DBConnectionConfig,
    testConnection: boolean = true,
    ttlHours: number = 3
  ): Promise<DBConnectionSessionResponse> {
    const response = await apiService.post<DBConnectionSessionResponse>(
      `${this.baseUrl}/sessions`,
      {
        connection: config,
        test_connection: testConnection,
        ttl_hours: ttlHours,
      }
    );
    return response;
  }

  /**
   * Listar sesiones activas del usuario
   * El backend verifica cookies httpOnly automáticamente
   */
  async listSessions(): Promise<DBConnectionSessionResponse[]> {
    const response = await apiService.get<DBConnectionSessionResponse[]>(
      `${this.baseUrl}/sessions`
    );
    return response;
  }

  /**
   * Eliminar sesión (también elimina cookie)
   */
  async deleteSession(sessionId: string): Promise<void> {
    await apiService.delete(`${this.baseUrl}/sessions/${sessionId}`);
  }

  /**
   * Refrescar TTL de sesión (extender tiempo de vida)
   */
  async refreshSession(sessionId: string, ttlHours: number = 3): Promise<DBConnectionSessionResponse> {
    const response = await apiService.post<DBConnectionSessionResponse>(
      `${this.baseUrl}/sessions/${sessionId}/refresh?ttl_hours=${ttlHours}`,
      null
    );
    return response;
  }

  /**
   * Listar schemas de una sesión
   */
  async listSchemas(sessionId: string): Promise<string[]> {
    const response = await apiService.get<string[]>(
      `${this.baseUrl}/sessions/${sessionId}/schemas`
    );
    return response;
  }

  /**
   * Listar tablas de un schema
   */
  async listTables(sessionId: string, schema: string): Promise<TableMetadata[]> {
    const response = await apiService.get<TableMetadata[]>(
      `${this.baseUrl}/sessions/${sessionId}/schemas/${encodeURIComponent(schema)}/tables`
    );
    return response;
  }

  /**
   * Obtener metadata completa de un schema
   */
  async getSchemaMetadata(sessionId: string, schema: string): Promise<SchemaMetadata> {
    const response = await apiService.get<SchemaMetadata>(
      `${this.baseUrl}/sessions/${sessionId}/schemas/${encodeURIComponent(schema)}/metadata`
    );
    return response;
  }

  /**
   * Importar todas las tablas de una sesión como ExternalDBTable
   * @param sessionId ID de la sesión activa
   * @param tableType Tipo de tablas (origin o destination)
   * @returns Array de tablas externas en memoria
   */
  async importAllTables(
    sessionId: string,
    tableType: 'origin' | 'destination'
  ): Promise<ExternalDBTable[]> {
    // 1. Obtener lista de schemas
    const schemas = await this.listSchemas(sessionId);

    if (schemas.length === 0) {
      return [];
    }

    // 2. Obtener metadata de cada schema
    const allTables: ExternalDBTable[] = [];
    const timestamp = new Date().toISOString();

    for (const schema of schemas) {
      try {
        const metadata = await this.getSchemaMetadata(sessionId, schema);

        // 3. Convertir cada tabla a ExternalDBTable
        for (const table of metadata.tables) {
          const externalTable: ExternalDBTable = {
            id: `${sessionId}:${schema}:${table.name}`,
            name: schema === 'public' || schema === 'dbo' ? table.name : `${schema}.${table.name}`,
            schema,
            type: tableType,
            is_external_db: true,
            session_id: sessionId,
            columns: table.columns.map((col): ExternalDBColumn => ({
              id: `${sessionId}:${schema}:${table.name}:${col.name}`,
              table_id: `${sessionId}:${schema}:${table.name}`,
              name: col.name,
              data_type: col.data_type,
              native_type: col.native_type,
              is_nullable: col.is_nullable,
              is_primary_key: col.is_primary_key,
              is_auto_increment: col.is_auto_increment,
              default_value: col.default_value,
              max_length: col.max_length,
              table_type: tableType,
            })),
            created_at: timestamp,
          };

          allTables.push(externalTable);
        }
      } catch (error) {
        console.error(`Error importing schema ${schema}:`, error);
        // Continuar con el siguiente schema
      }
    }

    return allTables;
  }

  /**
   * Obtener tablas de la BD externa con hashes pre-computados (modo connector).
   * La estructura NO se guarda localmente — solo se usa para mostrar al usuario
   * y para crear mappings con table_hash/column_hash.
   *
   * @param sessionId ID de la sesión activa
   * @param tableType Tipo (origin o destination) asignado al conectar
   * @param schema Filtrar por schema específico (opcional, por defecto todos)
   */
  async getConnectorTables(
    sessionId: string,
    tableType: 'origin' | 'destination',
    schema?: string
  ): Promise<ConnectorTable[]> {
    const url = schema
      ? `${this.baseUrl}/sessions/${sessionId}/connector-tables?schema=${encodeURIComponent(schema)}`
      : `${this.baseUrl}/sessions/${sessionId}/connector-tables`;

    const response = await apiService.get<ConnectorTablesResponse>(url);

    return response.tables.map(table => ({
      ...table,
      id: `connector:${sessionId}:${table.schema}:${table.name}`,
      type: tableType,
      session_id: sessionId,
      is_connector: true as const,
    }));
  }

  /**
   * Verificar si una sesión sigue activa
   */
  async isSessionActive(sessionId: string): Promise<boolean> {
    try {
      const sessions = await this.listSessions();
      return sessions.some(session => session.session_id === sessionId);
    } catch {
      return false;
    }
  }

  /**
   * Obtener sesiones activas agrupadas por tipo
   */
  async getActiveSessionsByType(): Promise<{
    origin?: string;
    destination?: string;
  }> {
    try {
      await this.listSessions();

      // El backend no guarda el tipo, así que necesitamos una manera de identificarlo
      // Por ahora retornamos solo los session_ids
      // TODO: Implementar lógica para identificar tipo de sesión

      return {};
    } catch (error) {
      console.error('Error getting active sessions:', error);
      return {};
    }
  }
}

export const dbConnectionService = new DBConnectionService();
