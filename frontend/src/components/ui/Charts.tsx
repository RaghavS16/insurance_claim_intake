import React from 'react';

// Donut Chart
export interface DonutSegment {
  label: string;
  value: number;
  color: string;
}

export const DonutChart: React.FC<{
  segments: DonutSegment[];
  size?: number;
  strokeWidth?: number;
}> = ({ segments, size = 160, strokeWidth = 24 }) => {
  const total = segments.reduce((acc, s) => acc + s.value, 0) || 1;
  const radius = (size - strokeWidth) / 2;
  const center = size / 2;
  const circumference = 2 * Math.PI * radius;

  let currentOffset = 0;

  return (
    <div className="snow-flex snow-items-center snow-gap-4">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {segments.map((seg, i) => {
          const strokeDasharray = `${(seg.value / total) * circumference} ${circumference}`;
          const strokeDashoffset = -currentOffset;
          currentOffset += (seg.value / total) * circumference;

          return (
            <circle
              key={i}
              cx={center}
              cy={center}
              r={radius}
              fill="transparent"
              stroke={seg.color}
              strokeWidth={strokeWidth}
              strokeDasharray={strokeDasharray}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              style={{ transition: 'stroke-dasharray 0.3s ease' }}
            />
          );
        })}
      </svg>

      <div className="snow-flex-col snow-gap-2">
        {segments.map((seg, i) => (
          <div key={i} className="snow-flex snow-items-center snow-gap-2">
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: seg.color,
                display: 'inline-block',
              }}
            />
            <span className="snow-caption" style={{ minWidth: 80 }}>{seg.label}</span>
            <span className="snow-caption" style={{ fontWeight: 600 }}>
              {Math.round((seg.value / total) * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

// Bar Chart
export interface BarDataPoint {
  label: string;
  value: number;
  color?: string;
}

export const BarChart: React.FC<{
  data: BarDataPoint[];
  height?: number;
  defaultColor?: string;
}> = ({ data, height = 180, defaultColor = '#00D1FF' }) => {
  const maxVal = Math.max(...data.map((d) => d.value), 10);

  return (
    <div style={{ width: '100%', height, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          height: height - 24,
          gap: 12,
        }}
      >
        {data.map((d, i) => {
          const barHeight = (d.value / maxVal) * (height - 30);
          return (
            <div
              key={i}
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                height: '100%',
                justifyContent: 'flex-end',
              }}
            >
              <div
                style={{
                  width: '100%',
                  maxWidth: 24,
                  height: Math.max(barHeight, 4),
                  backgroundColor: d.color || defaultColor,
                  borderRadius: 6,
                  transition: 'height 0.3s ease',
                }}
              />
            </div>
          );
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
        {data.map((d, i) => (
          <span key={i} className="snow-micro" style={{ flex: 1, textAlign: 'center' }}>
            {d.label}
          </span>
        ))}
      </div>
    </div>
  );
};
