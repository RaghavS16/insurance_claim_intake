'use client';

import React, { useId } from 'react';
import { Check } from 'lucide-react';

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: React.ReactNode;
  description?: string;
  error?: string;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ label, description, error, checked, defaultChecked, onChange, disabled, className = '', id: propId, style, ...props }, ref) => {
    const generatedId = useId();
    const id = propId || generatedId;

    return (
      <div className={`snow-checkbox-wrapper ${className}`} style={{ display: 'inline-flex', flexDirection: 'column', ...style }}>
        <label
          htmlFor={id}
          style={{
            display: 'inline-flex',
            alignItems: 'flex-start',
            gap: 10,
            cursor: disabled ? 'not-allowed' : 'pointer',
            opacity: disabled ? 0.6 : 1,
            userSelect: 'none',
          }}
        >
          <div style={{ position: 'relative', width: 18, height: 18, flexShrink: 0, marginTop: 1 }}>
            <input
              ref={ref}
              type="checkbox"
              id={id}
              checked={checked}
              defaultChecked={defaultChecked}
              onChange={onChange}
              disabled={disabled}
              className="snow-checkbox-input"
              style={{
                position: 'absolute',
                opacity: 0,
                width: '100%',
                height: '100%',
                margin: 0,
                cursor: disabled ? 'not-allowed' : 'pointer',
                zIndex: 1,
              }}
              {...props}
            />
            <div
              className={`snow-checkbox-box ${checked ? 'checked' : ''}`}
              style={{
                width: 18,
                height: 18,
                borderRadius: 5,
                border: checked ? '1.5px solid #007AFF' : '1.5px solid #D1D5DB',
                backgroundColor: checked ? '#007AFF' : '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.15s ease',
                boxShadow: checked ? '0 1px 3px rgba(0, 122, 255, 0.25)' : 'none',
              }}
            >
              {checked && <Check size={12} color="#FFFFFF" strokeWidth={3} />}
            </div>
          </div>

          {(label || description) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {label && (
                <span className="snow-body" style={{ fontSize: 13, fontWeight: 500, color: '#1F2937', lineHeight: 1.4 }}>
                  {label}
                </span>
              )}
              {description && (
                <span className="snow-caption" style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.3 }}>
                  {description}
                </span>
              )}
            </div>
          )}
        </label>

        {error && (
          <span className="snow-error" style={{ fontSize: 11, color: '#EF4444', marginTop: 4, marginLeft: 28 }}>
            {error}
          </span>
        )}
      </div>
    );
  }
);

Checkbox.displayName = 'Checkbox';
