import React from "react";

interface MetricItem {
  label: string;
  value: string | number;
  icon: string;
  trend?: string;
}

interface MetricsGridProps {
  metrics: MetricItem[];
}

export const MetricsGrid: React.FC<MetricsGridProps> = ({ metrics }) => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {metrics.map((m, idx) => (
        <div
          key={idx}
          className="bg-surface border border-surface-container-highest rounded-2xl p-5 shadow-sm flex items-center justify-between"
        >
          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-secondary block">
              {m.label}
            </span>
            <span className="text-2xl font-bold font-headline text-on-surface mt-1 block">
              {m.value}
            </span>
            {m.trend && (
              <span className="text-[10px] text-emerald-600 font-semibold mt-1 block">
                {m.trend}
              </span>
            )}
          </div>
          <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
            <span className="material-symbols-outlined text-2xl">{m.icon}</span>
          </div>
        </div>
      ))}
    </div>
  );
};
