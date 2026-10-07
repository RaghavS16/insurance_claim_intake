'use client';

import React, { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  iconLeft,
  iconRight,
  type = 'text',
  className = '',
  ...props
}) => {
  const [showPassword, setShowPassword] = useState(false);
  const isPassword = type === 'password';
  const effectiveType = isPassword ? (showPassword ? 'text' : 'password') : type;

  return (
    <div className="snow-form-group">
      {label && <label className="snow-label">{label}</label>}
      <div className="snow-input-wrapper">
        {iconLeft && (
          <span className="snow-input-adornment left">
            {iconLeft}
          </span>
        )}
        <input
          type={effectiveType}
          className={`snow-input ${iconLeft ? 'snow-input-icon-left' : ''} ${
            isPassword || iconRight ? 'snow-input-icon-right' : ''
          } ${className}`}
          {...props}
        />
        {isPassword ? (
          <button
            type="button"
            className="snow-input-adornment right"
            style={{ background: 'none', border: 'none', cursor: 'pointer' }}
            onClick={() => setShowPassword(!showPassword)}
            tabIndex={-1}
          >
            {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        ) : iconRight ? (
          <span className="snow-input-adornment right">{iconRight}</span>
        ) : null}
      </div>
      {error && <span className="snow-micro" style={{ color: '#EF4444' }}>{error}</span>}
    </div>
  );
};
