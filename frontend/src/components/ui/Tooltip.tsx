'use client';

import React, { useState, useRef, useEffect } from 'react';

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
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [effectivePosition, setEffectivePosition] = useState<'top' | 'bottom' | 'left' | 'right'>(position);
  const [horizontalShift, setHorizontalShift] = useState<'center' | 'left' | 'right'>('center');

  useEffect(() => {
    setEffectivePosition(position);
  }, [position]);

  const showTooltip = () => {
    timeoutRef.current = setTimeout(() => {
      if (wrapperRef.current) {
        const rect = wrapperRef.current.getBoundingClientRect();
        // Check top boundary collision: if element is close to top of viewport (< 42px), flip to 'bottom'
        if ((position === 'top' || !position) && rect.top < 42) {
          setEffectivePosition('bottom');
        } else if (position === 'bottom' && window.innerHeight - rect.bottom < 42) {
          setEffectivePosition('top');
        } else {
          setEffectivePosition(position);
        }

        // Check horizontal boundaries to avoid clipping on left or right viewport edges
        if (rect.left + rect.width / 2 + 70 > window.innerWidth) {
          setHorizontalShift('right'); // align flush right with trigger
        } else if (rect.left - 50 < 0) {
          setHorizontalShift('left'); // align flush left with trigger
        } else {
          setHorizontalShift('center');
        }
      }
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
    switch (effectivePosition) {
      case 'bottom': {
        const hStyle: React.CSSProperties =
          horizontalShift === 'right'
            ? { right: 0, left: 'auto', transform: 'none' }
            : horizontalShift === 'left'
            ? { left: 0, right: 'auto', transform: 'none' }
            : { left: '50%', transform: 'translateX(-50%)' };
        return {
          top: 'calc(100% + 6px)',
          ...hStyle,
        };
      }
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
      default: {
        const hStyle: React.CSSProperties =
          horizontalShift === 'right'
            ? { right: 0, left: 'auto', transform: 'none' }
            : horizontalShift === 'left'
            ? { left: 0, right: 'auto', transform: 'none' }
            : { left: '50%', transform: 'translateX(-50%)' };
        return {
          bottom: 'calc(100% + 6px)',
          ...hStyle,
        };
      }
    }
  };

  const isDark = variant === 'dark';

  return (
    <div
      ref={wrapperRef}
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
