'use client';

import React, { useState, useRef } from 'react';

export interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
  variant?: 'dark' | 'light';
  delay?: number;
  className?: string;
  style?: React.CSSProperties;
}

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  position = 'top',
  variant = 'dark',
  delay = 150,
  className = '',
  style,
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const showTooltip = () => {
    timeoutRef.current = setTimeout(() => {
      setIsVisible(true);
    }, delay);
  };

  const hideTooltip = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setIsVisible(false);
  };

  // Position calculation styles
  const getPositionStyles = (): React.CSSProperties => {
    switch (position) {
      case 'bottom':
        return {
          top: 'calc(100% + 6px)',
          left: '50%',
          transform: 'translateX(-50%)',
        };
      case 'left':
        return {
          top: '50%',
          right: 'calc(100% + 6px)',
          transform: 'translateY(-50%)',
        };
      case 'right':
        return {
          top: '50%',
          left: 'calc(100% + 6px)',
          transform: 'translateY(-50%)',
        };
      case 'top':
      default:
        return {
          bottom: 'calc(100% + 6px)',
          left: '50%',
          transform: 'translateX(-50%)',
        };
    }
  };

  const isDark = variant === 'dark';

  return (
    <div
      className={`snow-tooltip-wrapper ${className}`}
      style={{ position: 'relative', display: 'inline-flex', ...style }}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {children}

      {isVisible && content && (
        <div
          role="tooltip"
          className="snow-tooltip-bubble"
          style={{
            position: 'absolute',
            zIndex: 2000,
            whiteSpace: 'nowrap',
            padding: '5px 10px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            lineHeight: 1.3,
            pointerEvents: 'none',
            backgroundColor: isDark ? '#1C1C1C' : '#FFFFFF',
            color: isDark ? '#FFFFFF' : '#1C1C1C',
            border: isDark ? 'none' : '1px solid #EBECEF',
            boxShadow: isDark
              ? '0 4px 12px rgba(0, 0, 0, 0.15)'
              : '0 4px 14px rgba(0, 0, 0, 0.08), 0 1px 3px rgba(0, 0, 0, 0.05)',
            animation: 'snowTooltipFade 0.12s ease-out',
            ...getPositionStyles(),
          }}
        >
          {content}
        </div>
      )}
    </div>
  );
};
