// src/components/dashboard/StatCard.tsx
import React from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface StatCardProps {
  label: string;
  value: string | number;
  change: string;
  positive: boolean;
}

export const StatCard: React.FC<StatCardProps> = ({ label, value, change, positive }) => {
  const { t } = useTranslation(['dashboard', 'common']);
  return (
    <div className="stat-card">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      <p className={`stat-change ${positive ? 'positive' : 'negative'} flex items-center gap-1`}>
        {positive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
        {t(`dashboard:stat_card.${positive ? 'changePositive' : 'changeNegative'}`, {
          percent: change,
          since: t('common:time.since_last_month'),
        })}
      </p>
    </div>
  );
};