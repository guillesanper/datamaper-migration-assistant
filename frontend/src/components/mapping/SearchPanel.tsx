// src/components/mapping/SearchPanel.tsx
import React, { memo } from 'react';
import { Search, X } from '../icons';

interface SearchPanelProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

const SearchPanelComponent: React.FC<SearchPanelProps> = ({
  value,
  onChange,
  placeholder = "Buscar..."
}) => {
  return (
    <div className="bg-card/95 backdrop-blur border rounded-lg shadow-lg p-2 min-w-[250px]">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full pl-9 pr-9 py-2 bg-background rounded-md border text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
        {value && (
          <button
            onClick={() => onChange('')}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-muted rounded"
          >
            <X className="w-3 h-3" />
          </button>
        )}
      </div>
    </div>
  );
};

// Memoize to prevent unnecessary re-renders
export const SearchPanel = memo(SearchPanelComponent);