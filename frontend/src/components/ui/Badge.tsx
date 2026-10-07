import React from 'react';

export interface BadgeDotProps {
  status: 'progress' | 'complete' | 'pending' | 'warning' | 'rejected' | 'neutral';
  label: string;
}

export const BadgeDot: React.FC<BadgeDotProps> = ({ status, label }) => {
  return (
    <span className="snow-badge-dot">
      <span className={`snow-dot ${status}`} />
      <span>{label}</span>
    </span>
  );
};

export interface BadgePillProps {
  variant?: 'sky' | 'mint' | 'amber' | 'rose' | 'purple' | 'neutral';
  children: React.ReactNode;
}

export const BadgePill: React.FC<BadgePillProps> = ({ variant = 'neutral', children }) => {
  return <span className={`snow-badge-pill ${variant}`}>{children}</span>;
};
