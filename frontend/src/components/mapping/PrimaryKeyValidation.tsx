// src/components/mapping/PrimaryKeyValidation.tsx
import React, { useState, useEffect } from 'react';
import { Key, AlertTriangle, CheckCircle2, RefreshCw, ChevronDown, ChevronUp } from '../icons';
import { pkService } from '../../services/pk_service';
import type { PrimaryKeyValidation as PKValidationType } from '../../types/mapping-types';
import { Button } from '../ui/button';

interface PrimaryKeyValidationProps {
  projectId: string;
  onNavigateToColumn?: (tableName: string, columnName: string) => void;
}

/**
 * Component to display Primary Key mapping validation status
 * Shows warnings when PK columns are not mapped
 */
export const PrimaryKeyValidation: React.FC<PrimaryKeyValidationProps> = ({
  projectId,
  onNavigateToColumn
}) => {
  const [validation, setValidation] = useState<PKValidationType | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  const loadValidation = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await pkService.validatePrimaryKeyMappings(projectId);
      setValidation(result);
      // Auto-expand if there are warnings
      if (result.warnings.length > 0) {
        setIsExpanded(true);
      }
    } catch (err: unknown) {
      console.error('Error loading PK validation:', err);
      setError(err instanceof Error ? err.message : 'Error al validar Primary Keys');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadValidation();
  }, [projectId]);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-muted/50 rounded-lg">
        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary"></div>
        <span className="text-sm text-muted-foreground">Validando Primary Keys...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg">
        <AlertTriangle className="w-4 h-4 text-red-500" />
        <span className="text-sm text-red-700 dark:text-red-300">{error}</span>
        <Button
          size="icon-sm"
          variant="ghost"
          onClick={loadValidation}
          className="ml-auto"
        >
          <RefreshCw className="w-4 h-4" />
        </Button>
      </div>
    );
  }

  if (!validation) {
    return null;
  }

  const hasWarnings = validation.total_missing > 0;
  const bgColor = hasWarnings
    ? 'bg-yellow-50 dark:bg-yellow-950/30 border-yellow-200 dark:border-yellow-800'
    : 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800';
  const textColor = hasWarnings
    ? 'text-yellow-700 dark:text-yellow-300'
    : 'text-green-700 dark:text-green-300';
  const iconColor = hasWarnings ? 'text-yellow-500' : 'text-green-500';

  return (
    <div className={`border rounded-lg ${bgColor}`}>
      {/* Header */}
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <Key className={`w-4 h-4 ${iconColor}`} />

        {hasWarnings ? (
          <AlertTriangle className={`w-4 h-4 ${iconColor}`} />
        ) : (
          <CheckCircle2 className={`w-4 h-4 ${iconColor}`} />
        )}

        <div className="flex-1">
          <span className={`text-sm font-medium ${textColor}`}>
            {hasWarnings
              ? `${validation.total_missing} columna${validation.total_missing !== 1 ? 's' : ''} PK sin mapear`
              : 'Todas las Primary Keys mapeadas'}
          </span>
          <span className={`text-xs ml-2 ${textColor} opacity-75`}>
            ({validation.checked_tables} tabla{validation.checked_tables !== 1 ? 's' : ''} revisada{validation.checked_tables !== 1 ? 's' : ''})
          </span>
        </div>

        <Button
          size="icon-sm"
          variant="ghost"
          onClick={(e) => {
            e.stopPropagation();
            loadValidation();
          }}
          title="Actualizar validación"
        >
          <RefreshCw className="w-4 h-4" />
        </Button>

        {hasWarnings && (
          isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />
        )}
      </div>

      {/* Expanded Details */}
      {isExpanded && hasWarnings && validation.missing_mappings.length > 0 && (
        <div className="border-t border-yellow-200 dark:border-yellow-800">
          <div className="px-3 py-2 space-y-2">
            <p className="text-xs text-yellow-700 dark:text-yellow-300 font-medium mb-2">
              Columnas Primary Key sin mapear:
            </p>

            <div className="space-y-1.5 max-h-60 overflow-y-auto">
              {validation.missing_mappings.map((missing, idx) => (
                <div
                  key={idx}
                  className={`
                    flex items-center justify-between gap-2 px-2 py-1.5 rounded
                    bg-white dark:bg-gray-900/50 border border-yellow-200 dark:border-yellow-800
                    ${onNavigateToColumn ? 'hover:bg-yellow-100 dark:hover:bg-yellow-900/20 cursor-pointer' : ''}
                  `}
                  onClick={() => onNavigateToColumn?.(missing.table, missing.column)}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <Key className="w-3 h-3 text-yellow-600 flex-shrink-0" />
                    <span className="text-sm font-medium text-foreground truncate">
                      {missing.table}
                    </span>
                    <span className="text-xs text-muted-foreground">→</span>
                    <span className="text-sm text-foreground truncate">
                      {missing.column}
                    </span>
                  </div>

                  {missing.is_pk_column && (
                    <span className="text-xs px-1.5 py-0.5 bg-yellow-200 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-200 rounded flex-shrink-0">
                      PK
                    </span>
                  )}
                </div>
              ))}
            </div>

            {validation.warnings.length > 0 && (
              <div className="mt-3 pt-2 border-t border-yellow-200 dark:border-yellow-800">
                <p className="text-xs text-yellow-700 dark:text-yellow-300 font-medium mb-1">
                  Advertencias:
                </p>
                <ul className="space-y-1">
                  {validation.warnings.map((warning, idx) => (
                    <li key={idx} className="text-xs text-yellow-600 dark:text-yellow-400 flex items-start gap-1">
                      <span className="text-yellow-500 mt-0.5">•</span>
                      <span>{warning}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Success state details */}
      {isExpanded && !hasWarnings && (
        <div className="border-t border-green-200 dark:border-green-800 px-3 py-2">
          <p className="text-xs text-green-700 dark:text-green-300">
            Todas las columnas Primary Key están correctamente mapeadas en las tablas de origen y destino.
          </p>
        </div>
      )}
    </div>
  );
};

export default PrimaryKeyValidation;
