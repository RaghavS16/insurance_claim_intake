import React from 'react';

export interface CardProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({
  title,
  subtitle,
  action,
  children,
  className = '',
  ...props
}) => {
  return (
    <div className={`snow-card ${className}`} {...props}>
      {(title || action) && (
        <div
          className="snow-flex snow-items-center snow-justify-between"
          style={{ marginBottom: subtitle ? 4 : 16 }}
        >
          {title && <h3 className="snow-h3">{title}</h3>}
          {action && <div>{action}</div>}
        </div>
      )}
      {subtitle && (
        <p className="snow-caption" style={{ marginBottom: 16 }}>
          {subtitle}
        </p>
      )}
      {children}
    </div>
  );
};
