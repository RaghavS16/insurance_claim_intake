'use client';

import React, { useState, useRef, useEffect, useId } from 'react';
import { ChevronDown, Check } from 'lucide-react';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  label?: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  error?: string;
  disabled?: boolean;
  required?: boolean;
  id?: string;
  className?: string;
  style?: React.CSSProperties;
}

export const Select: React.FC<SelectProps> = ({
  label,
  value,
  options,
  onChange,
  placeholder = 'Select option',
  error,
  disabled = false,
  required = false,
  id: propId,
  className = '',
  style,
}) => {
  const generatedId = useId();
  const id = propId || generatedId;
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const selectedOption = options.find((opt) => opt.value === value);

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Sync highlighted index when opened
  useEffect(() => {
    if (isOpen) {
      const idx = options.findIndex((opt) => opt.value === value);
      setHighlightedIndex(idx >= 0 ? idx : 0);
    }
  }, [isOpen, value, options]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (isOpen && listRef.current && highlightedIndex >= 0) {
      const activeEl = listRef.current.children[highlightedIndex] as HTMLElement;
      if (activeEl) {
        activeEl.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [highlightedIndex, isOpen]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;

    if (!isOpen) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev < options.length - 1 ? prev + 1 : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : options.length - 1));
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (highlightedIndex >= 0 && options[highlightedIndex]) {
        onChange(options[highlightedIndex].value);
        setIsOpen(false);
      }
    } else if (e.key === 'Escape' || e.key === 'Tab') {
      setIsOpen(false);
    }
  };

  return (
    <div
      ref={containerRef}
      className={`snow-form-group ${className}`}
      style={{ position: 'relative', width: '100%', marginBottom: 16, ...style }}
    >
      {label && (
        <label
          htmlFor={id}
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

      {/* Trigger Button */}
      <button
        type="button"
        id={id}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-disabled={disabled}
        onClick={() => !disabled && setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
        className="snow-flex snow-items-center snow-justify-between"
        style={{
          width: '100%',
          height: 40,
          padding: '8px 14px',
          backgroundColor: disabled ? '#F4F4F5' : '#FFFFFF',
          border: error ? '1px solid #EF4444' : isOpen ? '1px solid #1C1C1C' : '1px solid #E4E4E7',
          borderRadius: 10,
          cursor: disabled ? 'not-allowed' : 'pointer',
          outline: 'none',
          boxShadow: isOpen ? '0 0 0 2px rgba(28,28,28,0.08)' : 'none',
          transition: 'all 0.15s ease',
          textAlign: 'left',
        }}
      >
        <span
          className="snow-body"
          style={{
            fontSize: 14,
            fontWeight: selectedOption ? 500 : 400,
            color: selectedOption ? '#1C1C1C' : '#A1A1AA',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown
          size={16}
          style={{
            color: '#71717A',
            transition: 'transform 0.2s ease',
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            flexShrink: 0,
            marginLeft: 8,
          }}
        />
      </button>

      {error && (
        <div style={{ color: '#EF4444', fontSize: 12, marginTop: 4 }}>{error}</div>
      )}

      {/* Dropdown Popover */}
      {isOpen && (
        <ul
          ref={listRef}
          role="listbox"
          tabIndex={-1}
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 1100,
            backgroundColor: '#FFFFFF',
            border: '1px solid #EBECEF',
            borderRadius: 12,
            padding: '6px',
            boxShadow: '0 10px 28px rgba(0,0,0,0.08), 0 2px 6px rgba(0,0,0,0.04)',
            maxHeight: 240,
            overflowY: 'auto',
            listStyle: 'none',
            margin: 0,
            animation: 'snowFadeIn 0.12s ease-out',
          }}
        >
          {options.map((option, index) => {
            const isSelected = option.value === value;
            const isHighlighted = index === highlightedIndex;

            return (
              <li
                key={option.value}
                role="option"
                aria-selected={isSelected}
                onClick={() => {
                  onChange(option.value);
                  setIsOpen(false);
                }}
                onMouseEnter={() => setHighlightedIndex(index)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '9px 12px',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: isSelected ? 600 : 500,
                  color: isSelected ? '#1C1C1C' : '#3F3F46',
                  backgroundColor: isHighlighted ? '#F4F5F7' : isSelected ? '#F9FAFB' : 'transparent',
                  cursor: 'pointer',
                  transition: 'background-color 0.1s ease',
                  userSelect: 'none',
                }}
              >
                <span>{option.label}</span>
                {isSelected && <Check size={14} style={{ color: '#1C1C1C', flexShrink: 0 }} />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
