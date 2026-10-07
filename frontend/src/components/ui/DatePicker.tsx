'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, X } from 'lucide-react';

export interface DatePickerProps {
  value?: string; // YYYY-MM-DD
  onChange?: (date: string) => void;
  placeholder?: string;
  label?: string;
  error?: string;
  disabled?: boolean;
  minDate?: string;
  maxDate?: string;
  className?: string;
  style?: React.CSSProperties;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

const WEEKDAY_NAMES = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

export const DatePicker: React.FC<DatePickerProps> = ({
  value,
  onChange,
  placeholder = 'Select date',
  label,
  error,
  disabled = false,
  minDate,
  maxDate,
  className = '',
  style,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Parse initial view month/year
  const selectedDate = value ? new Date(value + 'T00:00:00') : null;
  const initialDate = selectedDate || new Date();

  const [viewYear, setViewYear] = useState<number>(initialDate.getFullYear());
  const [viewMonth, setViewMonth] = useState<number>(initialDate.getMonth());

  useEffect(() => {
    if (value) {
      const d = new Date(value + 'T00:00:00');
      if (!isNaN(d.getTime())) {
        setViewYear(d.getFullYear());
        setViewMonth(d.getMonth());
      }
    }
  }, [value]);

  // Handle click outside to close popover
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

  const handlePrevMonth = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (viewMonth === 0) {
      setViewMonth(11);
      setViewYear((y) => y - 1);
    } else {
      setViewMonth((m) => m - 1);
    }
  };

  const handleNextMonth = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (viewMonth === 11) {
      setViewMonth(0);
      setViewYear((y) => y + 1);
    } else {
      setViewMonth((m) => m + 1);
    }
  };

  const handleSelectDay = (day: number) => {
    const mm = String(viewMonth + 1).padStart(2, '0');
    const dd = String(day).padStart(2, '0');
    const dateStr = `${viewYear}-${mm}-${dd}`;
    onChange?.(dateStr);
    setIsOpen(false);
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    onChange?.('');
    setIsOpen(false);
  };

  const handleSetToday = (e: React.MouseEvent) => {
    e.stopPropagation();
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    onChange?.(`${yyyy}-${mm}-${dd}`);
    setViewYear(yyyy);
    setViewMonth(today.getMonth());
    setIsOpen(false);
  };

  // Generate calendar days
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const firstDayOfWeek = new Date(viewYear, viewMonth, 1).getDay();
  const prevMonthDays = new Date(viewYear, viewMonth, 0).getDate();

  const formattedDisplay = selectedDate && !isNaN(selectedDate.getTime())
    ? selectedDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : '';

  const today = new Date();
  const isCurrentMonthToday = today.getFullYear() === viewYear && today.getMonth() === viewMonth;

  return (
    <div
      ref={containerRef}
      className={`snow-datepicker-wrapper ${className}`}
      style={{ position: 'relative', width: '100%', marginBottom: label ? 16 : 0, ...style }}
    >
      {label && <label className="snow-form-label">{label}</label>}

      {/* Input trigger */}
      <div
        onClick={() => !disabled && setIsOpen(!isOpen)}
        className="snow-flex snow-items-center snow-justify-between"
        style={{
          height: 40,
          padding: '8px 14px',
          backgroundColor: '#FFFFFF',
          border: error ? '1px solid #EF4444' : isOpen ? '1px solid #1C1C1C' : '1px solid #E4E4E7',
          borderRadius: 10,
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.6 : 1,
          transition: 'all 0.15s ease',
          boxShadow: isOpen ? '0 0 0 2px rgba(28,28,28,0.08)' : 'none',
        }}
      >
        <div className="snow-flex snow-items-center snow-gap-2" style={{ overflow: 'hidden' }}>
          <CalendarIcon size={16} style={{ color: isOpen ? '#1C1C1C' : '#71717A', flexShrink: 0 }} />
          <span
            className="snow-body"
            style={{
              color: formattedDisplay ? '#1C1C1C' : '#A1A1AA',
              fontSize: 14,
              whiteSpace: 'nowrap',
              textOverflow: 'ellipsis',
              overflow: 'hidden',
            }}
          >
            {formattedDisplay || placeholder}
          </span>
        </div>

        {value && !disabled && (
          <button
            type="button"
            onClick={handleClear}
            style={{
              background: 'none',
              border: 'none',
              padding: 2,
              cursor: 'pointer',
              color: '#A1A1AA',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={14} />
          </button>
        )}
      </div>

      {error && <span className="snow-form-error">{error}</span>}

      {/* Expanded Popover Calendar */}
      {isOpen && (
        <div
          className="snow-datepicker-popover"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            zIndex: 1000,
            width: 290,
            backgroundColor: '#FFFFFF',
            border: '1px solid #EBECEF',
            borderRadius: 16,
            padding: 16,
            boxShadow: '0 12px 32px rgba(0, 0, 0, 0.08), 0 2px 6px rgba(0, 0, 0, 0.04)',
            userSelect: 'none',
            animation: 'snowFadeIn 0.15s ease-out',
          }}
        >
          {/* Header Month / Year & Nav */}
          <div className="snow-flex snow-items-center snow-justify-between" style={{ marginBottom: 12 }}>
            <button
              type="button"
              onClick={handlePrevMonth}
              style={{
                background: 'none',
                border: 'none',
                padding: '4px 6px',
                borderRadius: 6,
                cursor: 'pointer',
                color: '#1C1C1C',
                display: 'flex',
                alignItems: 'center',
                transition: 'background-color 0.1s ease',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#F4F5F7')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
            >
              <ChevronLeft size={16} />
            </button>

            <span className="snow-body" style={{ fontWeight: 600, fontSize: 14 }}>
              {MONTH_NAMES[viewMonth]} {viewYear}
            </span>

            <button
              type="button"
              onClick={handleNextMonth}
              style={{
                background: 'none',
                border: 'none',
                padding: '4px 6px',
                borderRadius: 6,
                cursor: 'pointer',
                color: '#1C1C1C',
                display: 'flex',
                alignItems: 'center',
                transition: 'background-color 0.1s ease',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#F4F5F7')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
            >
              <ChevronRight size={16} />
            </button>
          </div>

          {/* Weekday Row */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(7, 1fr)',
              textAlign: 'center',
              marginBottom: 8,
            }}
          >
            {WEEKDAY_NAMES.map((wd) => (
              <span key={wd} className="snow-caption" style={{ color: '#A1A1AA', fontSize: 11, fontWeight: 500 }}>
                {wd}
              </span>
            ))}
          </div>

          {/* Days Grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(7, 1fr)',
              gap: '2px',
              textAlign: 'center',
            }}
          >
            {/* Previous month trailing days */}
            {Array.from({ length: firstDayOfWeek }).map((_, i) => {
              const day = prevMonthDays - firstDayOfWeek + i + 1;
              return (
                <div
                  key={`prev-${i}`}
                  style={{
                    height: 32,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#D4D4D8',
                    fontSize: 12,
                  }}
                >
                  {day}
                </div>
              );
            })}

            {/* Current month days */}
            {Array.from({ length: daysInMonth }).map((_, i) => {
              const day = i + 1;
              const isSelected =
                selectedDate &&
                selectedDate.getFullYear() === viewYear &&
                selectedDate.getMonth() === viewMonth &&
                selectedDate.getDate() === day;
              const isToday = isCurrentMonthToday && today.getDate() === day;

              return (
                <button
                  type="button"
                  key={`cur-${day}`}
                  onClick={() => handleSelectDay(day)}
                  style={{
                    height: 32,
                    width: 32,
                    margin: '0 auto',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderRadius: '50%',
                    border: isToday && !isSelected ? '1px solid #1C1C1C' : 'none',
                    backgroundColor: isSelected ? '#1C1C1C' : 'transparent',
                    color: isSelected ? '#FFFFFF' : '#1C1C1C',
                    fontSize: 13,
                    fontWeight: isSelected || isToday ? 600 : 400,
                    cursor: 'pointer',
                    transition: 'all 0.12s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = '#F4F5F7';
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  {day}
                </button>
              );
            })}
          </div>

          {/* Footer Controls */}
          <div
            className="snow-flex snow-justify-between snow-items-center"
            style={{
              marginTop: 12,
              paddingTop: 8,
              borderTop: '1px solid #EBECEF',
            }}
          >
            <button
              type="button"
              onClick={handleClear}
              className="snow-caption"
              style={{
                background: 'none',
                border: 'none',
                color: '#71717A',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              Clear
            </button>
            <button
              type="button"
              onClick={handleSetToday}
              className="snow-caption"
              style={{
                background: 'none',
                border: 'none',
                color: '#007AFF',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Today
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
