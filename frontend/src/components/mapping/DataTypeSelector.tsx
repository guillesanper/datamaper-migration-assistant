// frontend/src/components/mapping/DataTypeSelector.tsx
import React, { useState, useEffect, useCallback, useRef } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Info } from "lucide-react";
import { typeValidationService } from "../../services/type_validation_service";
import type { BaseDataType, TypeSuggestions } from "../../types/mapping-types";

interface DataTypeSelectorProps {
  value: string;  // Full type string: "VARCHAR(255)", "NUMERIC(10,2)", "INTEGER"
  onChange: (fullType: string) => void;
  disabled?: boolean;
  showDescription?: boolean;
}

export const DataTypeSelector: React.FC<DataTypeSelectorProps> = ({
  value,
  onChange,
  disabled = false,
  showDescription = true
}) => {
  const [selectedBaseType, setSelectedBaseType] = useState<BaseDataType>('TEXT');
  const [parameters, setParameters] = useState<{
    length?: number;
    precision?: number;
    scale?: number;
  }>({});
  const [suggestions, setSuggestions] = useState<TypeSuggestions | null>(null);
  const [, setShowSuggestions] = useState(false);
  const isSyncingFromProps = useRef(false);

  // Categories of types
  const typeCategories = {
    text: [
      { value: 'TEXT', label: 'TEXT', description: 'Variable-length text (unlimited)' },
      { value: 'VARCHAR', label: 'VARCHAR', description: 'Variable-length text (with limit)' },
      { value: 'CHAR', label: 'CHAR', description: 'Fixed-length text (padded)' }
    ],
    numbers: [
      { value: 'SMALLINT', label: 'SMALLINT', description: '2-byte integer (−32,768 to 32,767)' },
      { value: 'INTEGER', label: 'INTEGER', description: '4-byte integer' },
      { value: 'BIGINT', label: 'BIGINT', description: '8-byte integer' },
      { value: 'NUMERIC', label: 'NUMERIC', description: 'Exact numeric with precision' },
      { value: 'DECIMAL', label: 'DECIMAL', description: 'Exact numeric (same as NUMERIC)' },
      { value: 'REAL', label: 'REAL', description: 'Single precision float' },
      { value: 'FLOAT', label: 'FLOAT', description: 'Floating-point number' },
      { value: 'DOUBLE PRECISION', label: 'DOUBLE PRECISION', description: 'Double precision float' }
    ],
    datetime: [
      { value: 'DATE', label: 'DATE', description: 'Calendar date (YYYY-MM-DD)' },
      { value: 'DATETIME', label: 'DATETIME', description: 'Date and time' },
      { value: 'TIME', label: 'TIME', description: 'Time of day (HH:MM:SS)' },
      { value: 'TIMESTAMP', label: 'TIMESTAMP', description: 'Date and time (no timezone)' },
      { value: 'TIMESTAMPTZ', label: 'TIMESTAMPTZ', description: 'Date and time (with timezone)' },
      { value: 'INTERVAL', label: 'INTERVAL', description: 'Time interval' }
    ],
    other: [
      { value: 'BOOLEAN', label: 'BOOLEAN', description: 'True/false value' },
      { value: 'JSON', label: 'JSON', description: 'JSON data (text format)' },
      { value: 'JSONB', label: 'JSONB', description: 'JSON data (binary, efficient)' },
      { value: 'UUID', label: 'UUID', description: 'Universally unique identifier' },
      { value: 'BYTEA', label: 'BYTEA', description: 'Binary data' },
      { value: 'INET', label: 'INET', description: 'IP address' },
      { value: 'MACADDR', label: 'MACADDR', description: 'MAC address' },
      { value: 'ARRAY', label: 'ARRAY', description: 'Array of values' }
    ]
  };

  // Load suggestions from API
  const loadSuggestions = useCallback(async (baseType: string) => {
    try {
      const sugg = await typeValidationService.getTypeSuggestions(baseType);
      setSuggestions(sugg);
    } catch (error) {
      console.error("Error loading suggestions:", error);
    }
  }, []);

  // Parse initial value
  useEffect(() => {
    isSyncingFromProps.current = true;

    if (value) {
      const parsed = typeValidationService.parseDataType(value);
      setSelectedBaseType(parsed.baseType);
      setParameters(parsed.parameters || {});

      // Load suggestions for parametrized types
      if (['VARCHAR', 'CHAR', 'NUMERIC', 'DECIMAL'].includes(parsed.baseType)) {
        loadSuggestions(parsed.baseType);
      }
    } else {
      // Reset to default when value is empty
      setSelectedBaseType('TEXT');
      setParameters({});
      setSuggestions(null);
    }

    // Reset flag after state updates are done
    setTimeout(() => {
      isSyncingFromProps.current = false;
    }, 0);
  }, [value, loadSuggestions]);

  // Handle base type change
  const handleBaseTypeChange = (newBaseType: string) => {
    // Don't emit changes when syncing from props
    if (isSyncingFromProps.current) {
      return;
    }

    const baseType = newBaseType as BaseDataType;
    setSelectedBaseType(baseType);

    // Reset parameters
    const newParams: typeof parameters = {};

    // Set default parameters if needed
    if (baseType === 'VARCHAR' || baseType === 'CHAR') {
      newParams.length = 255; // Default length
    } else if (baseType === 'NUMERIC' || baseType === 'DECIMAL') {
      newParams.precision = 10;
      newParams.scale = 2; // Default precision/scale
    }

    setParameters(newParams);

    // Load suggestions
    if (['VARCHAR', 'CHAR', 'NUMERIC', 'DECIMAL'].includes(baseType)) {
      loadSuggestions(baseType);
      setShowSuggestions(true);
    } else {
      setShowSuggestions(false);
      setSuggestions(null);
    }

    // Emit change
    emitChange(baseType, newParams);
  };

  // Handle parameter change
  const handleParameterChange = (paramName: string, value: string) => {
    const numValue = parseInt(value, 10);

    if (isNaN(numValue) || numValue < 0) {
      return; // Don't update with invalid values
    }

    const newParams = {
      ...parameters,
      [paramName]: numValue
    };

    setParameters(newParams);
    emitChange(selectedBaseType, newParams);
  };

  // Apply suggestion
  const applySuggestion = (suggestion: { length?: number; precision?: number; scale?: number }) => {
    const newParams: typeof parameters = {};

    if ('length' in suggestion) {
      newParams.length = suggestion.length;
    }

    if ('precision' in suggestion && 'scale' in suggestion) {
      newParams.precision = suggestion.precision;
      newParams.scale = suggestion.scale;
    }

    setParameters(newParams);
    emitChange(selectedBaseType, newParams);
  };

  // Emit formatted type to parent
  const emitChange = (baseType: BaseDataType, params: typeof parameters) => {
    const fullType = typeValidationService.formatDataType({
      baseType,
      parameters: params,
      fullType: '' // Will be generated
    });

    onChange(fullType);
  };


  // Get current formatted type
  const currentFullType = typeValidationService.formatDataType({
    baseType: selectedBaseType,
    parameters,
    fullType: ''
  });

  return (
    <div className="space-y-4">
      {/* Base Type Selector */}
      <div className="space-y-2">
        <Label htmlFor="base-type">Tipo de Dato</Label>
        <Select
          value={selectedBaseType}
          onValueChange={handleBaseTypeChange}
          disabled={disabled}
        >
          <SelectTrigger id="base-type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {/* Text Types */}
            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
              Texto
            </div>
            {typeCategories.text.map((type) => (
              <SelectItem key={type.value} value={type.value}>
                <div>
                  <div className="font-medium">{type.label}</div>
                  {showDescription && (
                    <div className="text-xs text-muted-foreground">{type.description}</div>
                  )}
                </div>
              </SelectItem>
            ))}

            {/* Number Types */}
            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground border-t mt-1">
              Números
            </div>
            {typeCategories.numbers.map((type) => (
              <SelectItem key={type.value} value={type.value}>
                <div>
                  <div className="font-medium">{type.label}</div>
                  {showDescription && (
                    <div className="text-xs text-muted-foreground">{type.description}</div>
                  )}
                </div>
              </SelectItem>
            ))}

            {/* Date/Time Types */}
            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground border-t mt-1">
              Fecha/Hora
            </div>
            {typeCategories.datetime.map((type) => (
              <SelectItem key={type.value} value={type.value}>
                <div>
                  <div className="font-medium">{type.label}</div>
                  {showDescription && (
                    <div className="text-xs text-muted-foreground">{type.description}</div>
                  )}
                </div>
              </SelectItem>
            ))}

            {/* Other Types */}
            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground border-t mt-1">
              Otros
            </div>
            {typeCategories.other.map((type) => (
              <SelectItem key={type.value} value={type.value}>
                <div>
                  <div className="font-medium">{type.label}</div>
                  {showDescription && (
                    <div className="text-xs text-muted-foreground">{type.description}</div>
                  )}
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Parameters for VARCHAR/CHAR */}
      {(selectedBaseType === 'VARCHAR' || selectedBaseType === 'CHAR') && (
        <div className="space-y-2">
          <Label htmlFor="length">Longitud</Label>
          <Input
            id="length"
            type="number"
            min="1"
            max="10485760"
            value={parameters.length || ''}
            onChange={(e) => handleParameterChange('length', e.target.value)}
            disabled={disabled}
            placeholder="255"
          />

          {/* Suggestions */}
          {suggestions && suggestions.common_lengths && (
            <div className="flex flex-wrap gap-2">
              <span className="text-xs text-muted-foreground">Comunes:</span>
              {suggestions.common_lengths.map((len) => (
                <button
                  key={len}
                  type="button"
                  onClick={() => applySuggestion({ length: len })}
                  className="px-2 py-1 text-xs bg-muted hover:bg-muted/80 rounded"
                  disabled={disabled}
                >
                  {len}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Parameters for NUMERIC/DECIMAL */}
      {(selectedBaseType === 'NUMERIC' || selectedBaseType === 'DECIMAL') && (
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="precision">Precisión</Label>
            <Input
              id="precision"
              type="number"
              min="1"
              max="1000"
              value={parameters.precision || ''}
              onChange={(e) => handleParameterChange('precision', e.target.value)}
              disabled={disabled}
              placeholder="10"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="scale">Escala</Label>
            <Input
              id="scale"
              type="number"
              min="0"
              max={parameters.precision || 1000}
              value={parameters.scale || ''}
              onChange={(e) => handleParameterChange('scale', e.target.value)}
              disabled={disabled}
              placeholder="2"
            />
          </div>

          {/* Suggestions */}
          {suggestions && suggestions.common_configs && (
            <div className="col-span-2 space-y-2">
              <span className="text-xs text-muted-foreground">Configuraciones comunes:</span>
              <div className="flex flex-wrap gap-2">
                {suggestions.common_configs.map((config, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => applySuggestion(config)}
                    className="px-3 py-2 text-xs bg-muted hover:bg-muted/80 rounded"
                    disabled={disabled}
                  >
                    <div className="font-medium">
                      {config.precision},{config.scale}
                    </div>
                    <div className="text-muted-foreground">{config.description}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Preview */}
      <div className="flex items-center gap-2 p-3 bg-muted rounded-lg">
        <Info className="w-4 h-4 text-muted-foreground flex-shrink-0" />
        <div className="text-sm">
          <span className="text-muted-foreground">Tipo completo:</span>{' '}
          <code className="font-mono font-bold text-foreground">{currentFullType}</code>
        </div>
      </div>

      {/* Description */}
      {suggestions && suggestions.description && (
        <div className="text-xs text-muted-foreground">
          {suggestions.description}
        </div>
      )}
    </div>
  );
};
