'use client';

import React from 'react';

export interface LiveIndicatorProps {
  secondsAgo: number;
  isRefreshing?: boolean;
  className?: string;
}

export function LiveIndicator({
  secondsAgo,
  isRefreshing,
  className = '',
}: LiveIndicatorProps) {
  const timeText = secondsAgo < 5 ? '0s ago' : `${secondsAgo}s ago`;
  return (
    <span
      className={`snow-badge-dot ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '3px 8px',
        borderRadius: '9999px',
        backgroundColor: '#ECFDF5',
        border: '1px solid #A7F3D0',
        fontSize: '11px',
        fontWeight: 500,
        color: '#065F46',
      }}
      title="Real-time live updates enabled"
    >
      <span
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          backgroundColor: isRefreshing ? '#059669' : '#10B981',
          boxShadow: isRefreshing
            ? '0 0 0 3px rgba(16, 185, 129, 0.4)'
            : '0 0 0 2px rgba(16, 185, 129, 0.2)',
          transition: 'all 0.2s ease',
        }}
      />
      <span>Live - updated {timeText}</span>
    </span>
  );
}
