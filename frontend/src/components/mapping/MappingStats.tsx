// src/components/mapping/MappingStats.tsx
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Database, Link2, AlertCircle, CheckCircle } from '../icons';

interface MappingStatsProps {
  totalMappings: number;
  tablesCount: number;
  originCount: number;
  destCount: number;
  unmappedRequired?: number;
}

export const MappingStats: React.FC<MappingStatsProps> = ({
  totalMappings,
  originCount,
  destCount,
  unmappedRequired = 0
}) => {
  const { t } = useTranslation('mapping');

  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-2">
        <Database className="w-4 h-4 text-muted-foreground" />
        <span className="text-sm">
          <span className="font-medium">{originCount}</span>
          <span className="text-muted-foreground"> {t('stats.origin')}</span>
        </span>
      </div>
      
      <div className="flex items-center gap-2">
        <Database className="w-4 h-4 text-muted-foreground" />
        <span className="text-sm">
          <span className="font-medium">{destCount}</span>
          <span className="text-muted-foreground"> {t('stats.dest')}</span>
        </span>
      </div>
      
      <div className="flex items-center gap-2">
        <Link2 className="w-4 h-4 text-muted-foreground" />
        <span className="text-sm">
          <span className="font-medium">{totalMappings}</span>
          <span className="text-muted-foreground"> {t('stats.mappings')}</span>
        </span>
      </div>

      {unmappedRequired > 0 ? (
        <div className="flex items-center gap-2 px-2 py-1 bg-yellow-100 dark:bg-yellow-900/20 rounded-lg">
          <AlertCircle className="w-4 h-4 text-yellow-600 dark:text-yellow-400" />
          <span className="text-sm text-yellow-700 dark:text-yellow-300">
            {t('stats.unmapped', { count: unmappedRequired })}
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-2 px-2 py-1 bg-green-100 dark:bg-green-900/20 rounded-lg">
          <CheckCircle className="w-4 h-4 text-green-600 dark:text-green-400" />
          <span className="text-sm text-green-700 dark:text-green-300">
            {t('stats.allMapped')}
          </span>
        </div>
      )}
    </div>
  );
};