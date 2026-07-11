// src/components/mapping/MappingToolbar.tsx
import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Upload, 
  Download, 
  RefreshCw, 
  Link2, 
  Unlink, 
  Maximize2,
  Grid,
  Save,
  Play
} from '../icons';

interface MappingToolbarProps {
  onImport: () => void;
  onExport: () => void;
  onRefresh: () => void;
  onToggleConnectionMode: () => void;
  connectionMode: boolean;
  onAutoLayout?: () => void;
  onToggleGrid?: () => void;
  gridEnabled?: boolean;
  onRunMigration?: () => void;
  onSaveLayout?: () => void;
}

export const MappingToolbar: React.FC<MappingToolbarProps> = ({
  onImport,
  onExport,
  onRefresh,
  onToggleConnectionMode,
  connectionMode,
  onAutoLayout,
  onToggleGrid,
  gridEnabled = true,
  onRunMigration,
  onSaveLayout
}) => {
  const { t } = useTranslation('mapping');

  return (
    <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30">
      <div className="flex items-center gap-1">
        {/* Import/Export */}
        <button
          onClick={onImport}
          className="p-2 hover:bg-muted rounded-lg transition-colors group"
          title={t('toolbar.import')}
        >
          <Upload className="w-4 h-4 group-hover:text-primary" />
        </button>
        
        <button
          onClick={onExport}
          className="p-2 hover:bg-muted rounded-lg transition-colors group"
          title={t('toolbar.export')}
        >
          <Download className="w-4 h-4 group-hover:text-primary" />
        </button>

        <div className="w-px h-6 bg-border mx-1" />

        {/* Connection mode */}
        <button
          onClick={onToggleConnectionMode}
          className={`p-2 rounded-lg transition-all ${
            connectionMode 
              ? 'bg-primary text-primary-foreground' 
              : 'hover:bg-muted'
          }`}
          title={t(connectionMode ? 'toolbar.connectionOn' : 'toolbar.connectionOff')}
        >
          {connectionMode ? (
            <Unlink className="w-4 h-4" />
          ) : (
            <Link2 className="w-4 h-4" />
          )}
        </button>

        {/* Refresh */}
        <button
          onClick={onRefresh}
          className="p-2 hover:bg-muted rounded-lg transition-colors group"
          title={t('toolbar.refresh')}
        >
          <RefreshCw className="w-4 h-4 group-hover:text-primary" />
        </button>

        <div className="w-px h-6 bg-border mx-1" />

        {/* Layout controls */}
        {onAutoLayout && (
          <button
            onClick={onAutoLayout}
            className="p-2 hover:bg-muted rounded-lg transition-colors group"
            title={t('toolbar.autoLayout')}
          >
            <Maximize2 className="w-4 h-4 group-hover:text-primary" />
          </button>
        )}

        {onToggleGrid && (
          <button
            onClick={onToggleGrid}
            className={`p-2 rounded-lg transition-colors ${
              gridEnabled ? 'bg-muted' : 'hover:bg-muted'
            }`}
            title={t(gridEnabled ? 'toolbar.hideGrid' : 'toolbar.showGrid')}
          >
            <Grid className="w-4 h-4" />
          </button>
        )}

        {onSaveLayout && (
          <button
            onClick={onSaveLayout}
            className="p-2 hover:bg-muted rounded-lg transition-colors group"
            title={t('toolbar.saveLayout')}
          >
            <Save className="w-4 h-4 group-hover:text-primary" />
          </button>
        )}
      </div>

      {/* Right side actions */}
      <div className="flex items-center gap-2">
        {connectionMode && (
          <div className="px-3 py-1 bg-primary/10 text-primary rounded-lg text-sm font-medium animate-pulse">
            {t('toolbar.connectionActive')}
          </div>
        )}
        
        {onRunMigration && (
          <button
            onClick={onRunMigration}
            className="px-4 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
          >
            <Play className="w-4 h-4" />
            {t('toolbar.runMigration')}
          </button>
        )}
      </div>
    </div>
  );
};