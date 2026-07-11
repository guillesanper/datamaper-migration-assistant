// frontend/src/services/type_validation_service.ts
import { apiService } from "./api.service";
import type {
  DataTypeDefinition,
  TypeValidationResult,
  TypeSuggestions,
  AvailableTypesResponse,
  BaseDataType
} from "../types/mapping-types";

/**
 * Servicio para validación y gestión de tipos de datos
 * FASE 2: Ampliación de tipos con validación de compatibilidad
 */
class TypeValidationService {
  /**
   * Validar un cambio de tipo de columna
   *
   * @param projectId ID del proyecto
   * @param columnId ID de la columna
   * @param newType Nuevo tipo (ej: "VARCHAR(255)", "NUMERIC(10,2)")
   * @returns Resultado de validación con nivel de riesgo
   */
  async validateTypeChange(
    projectId: string,
    columnId: string,
    newType: string
  ): Promise<TypeValidationResult> {
    try {
      const response = await apiService.post<{ status: string; validation: TypeValidationResult }>(
        `/api/projects/${projectId}/schemas/columns/${columnId}/validate-type-change`,
        { new_type: newType }
      );

      return response.validation;
    } catch (error: unknown) {
      console.error("Error validating type change:", error);

      // Return a default "danger" response if validation fails
      return {
        is_safe: false,
        risk_level: 'danger',
        message: (error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Error validando cambio de tipo',
        recommendation: 'Verificar el tipo de dato y los permisos.',
        old_type: '',
        new_type: newType,
        requires_confirmation: true,
        requires_backup: true
      };
    }
  }

  /**
   * Obtener sugerencias para un tipo base
   *
   * @param baseType Tipo base (VARCHAR, NUMERIC, etc.)
   * @returns Sugerencias de parámetros comunes
   */
  async getTypeSuggestions(baseType: string): Promise<TypeSuggestions> {
    try {
      const response = await apiService.get<{ status: string; suggestions: TypeSuggestions }>(
        `/api/schemas/types/${baseType}/suggestions`
      );

      return response.suggestions;
    } catch (error) {
      console.error("Error getting type suggestions:", error);

      // Return empty suggestions
      return {
        description: baseType,
        requires: []
      };
    }
  }

  /**
   * Obtener lista de todos los tipos disponibles
   *
   * @returns Lista organizada de tipos por categoría
   */
  async getAvailableTypes(): Promise<AvailableTypesResponse> {
    try {
      const response = await apiService.get<AvailableTypesResponse>("/api/schemas/types");
      return response;
    } catch (error) {
      console.error("Error getting available types:", error);

      // Return minimal fallback
      return {
        status: 'error',
        types: {
          text_types: ['TEXT', 'VARCHAR', 'CHAR'],
          integer_types: ['INTEGER', 'BIGINT', 'SMALLINT'],
          numeric_types: ['NUMERIC', 'DECIMAL', 'REAL'],
          boolean_type: ['BOOLEAN'],
          datetime_types: ['DATE', 'DATETIME', 'TIMESTAMP'],
          json_types: ['JSON', 'JSONB'],
          other_types: ['UUID']
        },
        parametrized_types: {
          VARCHAR: 'requires length',
          CHAR: 'requires length',
          NUMERIC: 'requires precision and scale',
          DECIMAL: 'requires precision and scale'
        },
        all_types: []
      };
    }
  }

  /**
   * Parsear un tipo de dato en sus componentes
   *
   * @param fullType Tipo completo (ej: "VARCHAR(255)", "NUMERIC(10,2)")
   * @returns Componentes del tipo
   *
   * @example
   * parseDataType("VARCHAR(255)")
   * // => { baseType: 'VARCHAR', parameters: { length: 255 }, fullType: 'VARCHAR(255)' }
   *
   * parseDataType("NUMERIC(10,2)")
   * // => { baseType: 'NUMERIC', parameters: { precision: 10, scale: 2 }, fullType: 'NUMERIC(10,2)' }
   *
   * parseDataType("INTEGER")
   * // => { baseType: 'INTEGER', parameters: {}, fullType: 'INTEGER' }
   */
  parseDataType(fullType: string): DataTypeDefinition {
    const trimmedType = fullType.trim().toUpperCase();

    // Check for parametrized types
    if (trimmedType.includes('(') && trimmedType.includes(')')) {
      const baseType = trimmedType.substring(0, trimmedType.indexOf('(')).trim() as BaseDataType;
      const paramsStr = trimmedType.substring(
        trimmedType.indexOf('(') + 1,
        trimmedType.indexOf(')')
      ).trim();

      const parameters: DataTypeDefinition['parameters'] = {};

      if (paramsStr.includes(',')) {
        // NUMERIC(10,2) or DECIMAL(10,2)
        const parts = paramsStr.split(',').map(p => p.trim());
        if (baseType === 'NUMERIC' || baseType === 'DECIMAL') {
          parameters.precision = parseInt(parts[0], 10);
          parameters.scale = parseInt(parts[1], 10);
        }
      } else {
        // VARCHAR(255) or CHAR(50)
        if (baseType === 'VARCHAR' || baseType === 'CHAR') {
          parameters.length = parseInt(paramsStr, 10);
        }
      }

      return {
        baseType,
        parameters,
        fullType: trimmedType
      };
    } else {
      // Simple type without parameters
      return {
        baseType: trimmedType as BaseDataType,
        parameters: {},
        fullType: trimmedType
      };
    }
  }

  /**
   * Formatear un tipo de dato desde sus componentes
   *
   * @param definition Definición del tipo
   * @returns String del tipo completo
   *
   * @example
   * formatDataType({ baseType: 'VARCHAR', parameters: { length: 255 } })
   * // => "VARCHAR(255)"
   *
   * formatDataType({ baseType: 'NUMERIC', parameters: { precision: 10, scale: 2 } })
   * // => "NUMERIC(10,2)"
   *
   * formatDataType({ baseType: 'INTEGER', parameters: {} })
   * // => "INTEGER"
   */
  formatDataType(definition: DataTypeDefinition): string {
    const { baseType, parameters } = definition;

    if (!parameters || Object.keys(parameters).length === 0) {
      return baseType;
    }

    // VARCHAR or CHAR with length
    if ((baseType === 'VARCHAR' || baseType === 'CHAR') && parameters.length) {
      return `${baseType}(${parameters.length})`;
    }

    // NUMERIC or DECIMAL with precision and scale
    if ((baseType === 'NUMERIC' || baseType === 'DECIMAL') && parameters.precision !== undefined) {
      const scale = parameters.scale !== undefined ? parameters.scale : 0;
      return `${baseType}(${parameters.precision},${scale})`;
    }

    return baseType;
  }

  /**
   * Validar formato de tipo de dato
   *
   * @param fullType Tipo completo como string
   * @returns True si el formato es válido
   */
  validateTypeFormat(fullType: string): boolean {
    try {
      const parsed = this.parseDataType(fullType);

      // Check if base type is valid
      if (!parsed.baseType) {
        return false;
      }

      // Validate parameter ranges
      if (parsed.parameters) {
        // VARCHAR/CHAR length
        if (parsed.parameters.length !== undefined) {
          if (parsed.parameters.length < 1 || parsed.parameters.length > 10485760) {
            return false;
          }
        }

        // NUMERIC/DECIMAL precision and scale
        if (parsed.parameters.precision !== undefined) {
          if (parsed.parameters.precision < 1 || parsed.parameters.precision > 1000) {
            return false;
          }
        }

        if (parsed.parameters.scale !== undefined) {
          const precision = parsed.parameters.precision || 1000;
          if (parsed.parameters.scale < 0 || parsed.parameters.scale > precision) {
            return false;
          }
        }
      }

      return true;
    } catch {
      return false;
    }
  }

  /**
   * Obtener icono representativo para un tipo de dato
   *
   * @param baseType Tipo base
   * @returns Emoji o símbolo representativo
   */
  getTypeIcon(baseType: BaseDataType): string {
    const icons: Record<string, string> = {
      // Text
      'TEXT': '📝',
      'VARCHAR': '📝',
      'CHAR': '📝',
      // Numbers
      'INTEGER': '🔢',
      'BIGINT': '🔢',
      'SMALLINT': '🔢',
      'NUMERIC': '🔢',
      'DECIMAL': '🔢',
      'REAL': '🔢',
      'FLOAT': '🔢',
      'DOUBLE PRECISION': '🔢',
      // Boolean
      'BOOLEAN': '✓✗',
      // Date/Time
      'DATE': '📅',
      'DATETIME': '📅',
      'TIME': '⏰',
      'TIMESTAMP': '📅',
      'TIMESTAMPTZ': '🌍',
      'INTERVAL': '⏱️',
      // JSON
      'JSON': '📦',
      'JSONB': '📦',
      // UUID
      'UUID': '🔑',
      // Binary
      'BYTEA': '💾',
      // Network
      'INET': '🌐',
      'MACADDR': '🌐',
      // Array
      'ARRAY': '📚'
    };

    return icons[baseType] || '📋';
  }

  /**
   * Obtener color representativo para un tipo de dato (para badges)
   *
   * @param baseType Tipo base
   * @returns Clase de color de Tailwind
   */
  getTypeColor(baseType: BaseDataType): string {
    const colors: Record<string, string> = {
      // Text - blue
      'TEXT': 'bg-blue-500',
      'VARCHAR': 'bg-blue-500',
      'CHAR': 'bg-blue-500',
      // Numbers - green
      'INTEGER': 'bg-green-500',
      'BIGINT': 'bg-green-500',
      'SMALLINT': 'bg-green-500',
      'NUMERIC': 'bg-green-600',
      'DECIMAL': 'bg-green-600',
      'REAL': 'bg-green-400',
      'FLOAT': 'bg-green-400',
      'DOUBLE PRECISION': 'bg-green-400',
      // Boolean - purple
      'BOOLEAN': 'bg-purple-500',
      // Date/Time - orange
      'DATE': 'bg-orange-500',
      'DATETIME': 'bg-orange-500',
      'TIME': 'bg-orange-400',
      'TIMESTAMP': 'bg-orange-600',
      'TIMESTAMPTZ': 'bg-orange-600',
      'INTERVAL': 'bg-orange-400',
      // JSON - yellow
      'JSON': 'bg-yellow-500',
      'JSONB': 'bg-yellow-600',
      // UUID - pink
      'UUID': 'bg-pink-500',
      // Binary - gray
      'BYTEA': 'bg-gray-500',
      // Network - cyan
      'INET': 'bg-cyan-500',
      'MACADDR': 'bg-cyan-500',
      // Array - indigo
      'ARRAY': 'bg-indigo-500'
    };

    return colors[baseType] || 'bg-gray-400';
  }
}

// Export singleton instance
export const typeValidationService = new TypeValidationService();
