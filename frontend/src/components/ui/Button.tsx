import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  pill?: boolean;
  icon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  pill = false,
  icon,
  className = '',
  ...props
}) => {
  const classes = [
    'snow-btn',
    `snow-btn-${variant}`,
    size !== 'md' ? `snow-btn-${size}` : '',
    pill ? 'snow-btn-pill' : '',
    className,
  ].filter(Boolean).join(' ');

  return (
    <button className={classes} {...props}>
      {icon && <span className="snow-btn-icon-wrap" style={{ display: 'inline-flex' }}>{icon}</span>}
      {children}
    </button>
  );
};
