import React from 'react';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';

export interface MetricCardProps {
  title: string;
  value: string | number;
  trend?: string;
  trendDirection?: 'up' | 'down';
  tint?: 'sky' | 'indigo' | 'purple' | 'mint' | 'amber' | 'rose';
  icon?: React.ReactNode;
  onClick?: () => void;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  trend,
  trendDirection = 'up',
  tint = 'sky',
  icon,
  onClick,
}) => {
  return (
    <div
      className={`snow-metric-card ${tint}`}
      onClick={onClick}
      style={{ cursor: onClick ? 'pointer' : 'default' }}
    >
      <div className="snow-flex snow-justify-between snow-items-center">
        <span className="snow-metric-title">{title}</span>
        {icon && (
          <span className="metric-icon" style={{ display: 'inline-flex', opacity: 0.85 }}>
            {icon}
          </span>
        )}
      </div>
      <div className="snow-metric-val-wrap">
        <span className="snow-metric-value">{value}</span>
        {trend && (
          <span className={`snow-metric-trend ${trendDirection}`}>
            {trendDirection === 'up' ? (
              <ArrowUpRight size={14} />
            ) : (
              <ArrowDownRight size={14} />
            )}
            {trend}
          </span>
        )}
      </div>
    </div>
  );
};
