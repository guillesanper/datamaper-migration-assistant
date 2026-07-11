// src/services/mapping_service.ts
import { apiService } from './api.service';
import type {
  Mapping,
  TableWithColumns,
  ImportStructureResponse,
  CreateTableData,
  UpdateTableData,
  CreateColumnData,
  UpdateColumnData,
  Table,
  Column
} from '../types/mapping-types';

class MappingService {
  private readonly BASE_PATH = '/api/mappings';
  private readonly BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  async getTables(projectId: string): Promise<TableWithColumns[]> {
    const response = await apiService.get<{ tables: TableWithColumns[] }>(
      `${this.BASE_PATH}/projects/${projectId}/tables`
    );
    return response.tables;
  }

  async createMapping(mapping: Mapping): Promise<Mapping> {
    // Extract project_id from mapping and remove it from the body
    const { project_id, ...mappingData } = mapping;
    await apiService.post<{ status: string }>(
      `${this.BASE_PATH}/projects/${project_id}/save`,
      mappingData
    );
    // El servidor solo devuelve {status: "ok"}, así que devolvemos el mapping original
    return mapping;
  }

  async deleteMapping(mapping: Mapping): Promise<void> {
    // Extract project_id and remove it from the body
    const { project_id, ...mappingData } = mapping;
    await apiService.delete(`${this.BASE_PATH}/projects/${project_id}/delete`, {
      body: JSON.stringify(mappingData),
      headers: { 'Content-Type': 'application/json' }
    });
  }

  async getMappings(projectId: string): Promise<Mapping[]> {
    const response = await apiService.get<{ mappings: Mapping[] }>(
      `${this.BASE_PATH}/projects/${projectId}`
    );
    return response.mappings;
  }

  async importStructure(
    projectId: string,
    file: File,
    format: 'json' | 'csv' | 'excel',
    duplicateStrategy: 'skip' | 'replace' = 'skip'
  ): Promise<ImportStructureResponse> {
    const formData = new FormData();
    formData.append('file', file);
    // project_id now comes from path, not form data
    formData.append('format', format);
    formData.append('duplicate_strategy', duplicateStrategy);

    // Usar fetch directamente con BASE_URL para no romper el FormData
    const response = await fetch(`${this.BASE_URL}${this.BASE_PATH}/projects/${projectId}/import_structure`, {
      method: 'POST',
      body: formData,
      credentials: 'include'
      // NO poner Content-Type, fetch lo establece automáticamente para FormData
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Import error response:', errorText);
      throw new Error(`Import failed: ${response.status} ${response.statusText}`);
    }

    return await response.json();
  }

  async exportMappings(
    projectId: string,
    format: 'json' | 'csv' | 'excel'
  ): Promise<Blob> {
    const response = await fetch(
      `${this.BASE_URL}${this.BASE_PATH}/projects/${projectId}/export?format=${format}`,
      { credentials: 'include' }
    );

    if (!response.ok) {
      // Leer el cuerpo de la respuesta solo UNA vez
      const contentType = response.headers.get('content-type');
      let errorMessage = `Export failed: ${response.status} ${response.statusText}`;
      
      if (contentType?.includes('application/json')) {
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorData.message || errorMessage;
        } catch (e) {
          console.error('Failed to parse error JSON:', e);
        }
      } else {
        try {
          const errorText = await response.text();
          if (errorText) {
            errorMessage = errorText;
          }
        } catch (e) {
          console.error('Failed to read error text:', e);
        }
      }
      
      throw new Error(errorMessage);
    }

    return await response.blob();
  }

  async validateMappings(projectId: string): Promise<{
    isValid: boolean;
    errors: string[];
  }> {
    const response = await apiService.post<{ isValid: boolean; errors: string[] }>(
      `${this.BASE_PATH}/projects/${projectId}/validate`
    );
    return response;
  }

  // ==================== TABLE CRUD ====================

  async createTable(projectId: string, data: CreateTableData): Promise<Table> {
    // Remove project_id from data as it now comes from path
    const { project_id: _project_id, ...tableData } = data as CreateTableData & { project_id?: string };
    const response = await apiService.post<{ status: string; message: string; table: Table }>(
      `/api/projects/${projectId}/schemas/tables`,
      tableData
    );
    return response.table;
  }

  async updateTable(projectId: string, tableId: string, data: UpdateTableData): Promise<Table> {
    const response = await apiService.put<{ status: string; message: string; table: Table }>(
      `/api/projects/${projectId}/schemas/tables/${tableId}`,
      data
    );
    return response.table;
  }

  async deleteTable(projectId: string, tableId: string): Promise<{ columns_deleted: number; mappings_deleted: number }> {
    const response = await apiService.delete<{
      status: string;
      message: string;
      columns_deleted: number;
      mappings_deleted: number;
    }>(`/api/projects/${projectId}/schemas/tables/${tableId}`);
    return {
      columns_deleted: response.columns_deleted,
      mappings_deleted: response.mappings_deleted
    };
  }

  async getTable(projectId: string, tableId: string): Promise<Table> {
    const response = await apiService.get<{ status: string; table: Table }>(
      `/api/projects/${projectId}/schemas/tables/${tableId}`
    );
    return response.table;
  }

  // ==================== COLUMN CRUD ====================

  async createColumn(projectId: string, tableId: string, data: CreateColumnData): Promise<Column> {
    // Remove table_id from data as it now comes from path
    const { table_id: _table_id, ...columnData } = data as CreateColumnData & { table_id?: string };
    const response = await apiService.post<{ status: string; message: string; column: Column }>(
      `/api/projects/${projectId}/schemas/tables/${tableId}/columns`,
      columnData
    );
    return response.column;
  }

  async updateColumn(projectId: string, columnId: string, data: UpdateColumnData): Promise<{ column: Column; mappings_renamed: number }> {
    const response = await apiService.put<{
      status: string;
      message: string;
      column: Column;
      mappings_renamed: number;
    }>(`/api/projects/${projectId}/schemas/columns/${columnId}`, data);
    return {
      column: response.column,
      mappings_renamed: response.mappings_renamed
    };
  }

  async deleteColumn(projectId: string, columnId: string): Promise<{ mappings_deleted: number }> {
    const response = await apiService.delete<{
      status: string;
      message: string;
      mappings_deleted: number;
    }>(`/api/projects/${projectId}/schemas/columns/${columnId}`);
    return {
      mappings_deleted: response.mappings_deleted
    };
  }

  async getColumn(projectId: string, columnId: string): Promise<Column> {
    const response = await apiService.get<{ status: string; column: Column }>(
      `/api/projects/${projectId}/schemas/columns/${columnId}`
    );
    return response.column;
  }
}

export const mappingService = new MappingService();
