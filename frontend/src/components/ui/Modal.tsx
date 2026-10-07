'use client';

import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { Button } from './Button';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidth?: number;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  footer,
  maxWidth = 520,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.body.style.overflow = '';
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="snow-modal-backdrop" onClick={onClose}>
      <div
        className="snow-modal"
        style={{ maxWidth }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="snow-modal-header">
          <h2 className="snow-h2" style={{ textAlign: 'center', width: '100%' }}>
            {title}
          </h2>
          <button className="snow-modal-close" onClick={onClose} aria-label="Close modal">
            <X size={16} />
          </button>
        </div>
        <div className="snow-modal-body" style={{ margin: '16px 0' }}>
          {children}
        </div>
        {footer && (
          <div
            className="snow-modal-footer snow-flex snow-justify-between"
            style={{ gap: 12, marginTop: 24 }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};
