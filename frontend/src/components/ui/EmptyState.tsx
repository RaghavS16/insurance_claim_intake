import React from 'react';
import { PackageOpen, Plus } from 'lucide-react';
import { Button } from './Button';

export interface EmptyStateProps {
  title?: string;
  subtitle?: string;
  actionLabel?: string;
  onAction?: () => void;
  icon?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No data',
  subtitle = 'You may need',
  actionLabel = 'Add data',
  onAction,
  icon,
}) => {
  return (
    <div
      className="snow-flex-col snow-items-center snow-justify-center"
      style={{ padding: '60px 20px', textAlign: 'center' }}
    >
      <h2 className="snow-h2" style={{ marginBottom: 16 }}>{title}</h2>

      <div
        style={{
          width: 80,
          height: 80,
          borderRadius: 20,
          background: '#F4F5F7',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#71717A',
          marginBottom: 24,
        }}
      >
        {icon || <PackageOpen size={40} />}
      </div>

      <div
        style={{
          width: 140,
          height: 1,
          backgroundColor: '#EBECEF',
          marginBottom: 16,
        }}
      />

      <p className="snow-body-muted" style={{ marginBottom: 16 }}>{subtitle}</p>

      {onAction && (
        <Button
          pill
          variant="primary"
          icon={<Plus size={14} />}
          onClick={onAction}
        >
          {actionLabel}
        </Button>
      )}
    </div>
  );
};
