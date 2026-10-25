'use client';

import React, { useRef, useState } from 'react';
import { Upload, FileText, X } from 'lucide-react';
import { Button } from './Button';

export interface FileUploadProps {
  label?: string;
  accept?: string;
  required?: boolean;
  value?: File | null;
  file?: File | null;
  onChange?: (file: File | null) => void;
  onFileSelect?: (file: File | null) => void;
  helperText?: string;
  hint?: string;
  error?: string;
  disabled?: boolean;
  className?: string;
  buttonLabel?: string;
}

export const FileUpload: React.FC<FileUploadProps> = ({
  label,
  accept,
  required = false,
  value,
  file,
  onChange,
  onFileSelect,
  helperText,
  hint,
  error,
  disabled = false,
  className = '',
  buttonLabel = 'Choose File',
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const activeFile = value !== undefined ? value : file || null;
  const activeHelperText = helperText || hint;

  const notifyChange = (f: File | null) => {
    onChange?.(f);
    onFileSelect?.(f);
  };

  const handleButtonClick = () => {
    if (!disabled && inputRef.current) {
      inputRef.current.click();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      notifyChange(e.target.files[0]);
    }
  };

  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (inputRef.current) {
      inputRef.current.value = '';
    }
    notifyChange(null);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (!disabled && e.dataTransfer.files && e.dataTransfer.files[0]) {
      notifyChange(e.dataTransfer.files[0]);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className={`snow-form-group ${className}`} style={{ marginBottom: 16 }}>
      {label && (
        <label
          className="snow-label"
          style={{
            display: 'block',
            marginBottom: 6,
            fontSize: 13,
            fontWeight: 500,
            color: '#3F3F46',
          }}
        >
          {label} {required && <span style={{ color: '#EF4444' }}>*</span>}
        </label>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleFileChange}
        style={{ display: 'none' }}
        disabled={disabled}
      />

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={!activeFile ? handleButtonClick : undefined}
        style={{
          border: error
            ? '1.5px dashed #EF4444'
            : isDragOver
            ? '1.5px dashed #007AFF'
            : '1.5px dashed #D4D4D8',
          borderRadius: 12,
          padding: '12px 16px',
          backgroundColor: isDragOver ? '#F0F7FF' : activeFile ? '#FBFBFC' : '#FAFAFB',
          transition: 'all 0.15s ease',
          cursor: disabled ? 'not-allowed' : activeFile ? 'default' : 'pointer',
          opacity: disabled ? 0.6 : 1,
        }}
      >
        {activeFile ? (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  backgroundColor: '#EFF6FF',
                  color: '#2563EB',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <FileText size={18} />
              </div>
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: '#1C1C1C',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {activeFile.name}
                </div>
                <div style={{ fontSize: 11, color: '#71717A', marginTop: 2 }}>
                  {formatFileSize(activeFile.size)} • Ready to upload
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={handleButtonClick}
                disabled={disabled}
              >
                Change
              </Button>
              <button
                type="button"
                onClick={handleRemove}
                disabled={disabled}
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  border: 'none',
                  backgroundColor: '#F4F5F7',
                  color: '#71717A',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  transition: 'background-color 0.15s ease',
                }}
                title="Remove file"
              >
                <X size={14} />
              </button>
            </div>
          </div>
        ) : (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  backgroundColor: '#F4F5F7',
                  color: '#71717A',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <Upload size={18} />
              </div>
              <div>
                <span style={{ fontSize: 13, fontWeight: 500, color: '#1C1C1C' }}>
                  {buttonLabel}
                </span>
                {activeHelperText && (
                  <div style={{ fontSize: 11, color: '#71717A', marginTop: 2 }}>
                    {activeHelperText}
                  </div>
                )}
              </div>
            </div>

            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={handleButtonClick}
              disabled={disabled}
              icon={<Upload size={13} />}
            >
              Browse
            </Button>
          </div>
        )}
      </div>

      {error && (
        <span className="snow-form-error" style={{ display: 'block', marginTop: 4 }}>
          {error}
        </span>
      )}
    </div>
  );
};
