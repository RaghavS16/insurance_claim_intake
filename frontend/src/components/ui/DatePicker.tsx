'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, X, ChevronDown } from 'lucide-react';

export interface DatePickerProps {
  value?: string; // YYYY-MM-DD
  onChange?: (date: string) => void;
  placeholder?: string;
  label?: string;
  error?: string;
  disabled?: boolean;
  required?: boolean;
  minDate?: string;
  maxDate?: string;
  className?: string;
  style?: React.CSSProperties;
  popoverDirection?: 'auto' | 'up' | 'down';
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

const WEEKDAY_NAMES = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

// Support years from 1930 up to 2050
const YEARS = Array.from({ length: 121 }, (_, i) => 1930 + i);

export const DatePicker: React.FC<DatePickerProps> = ({
  value,
  onChange,
  placeholder = 'YYYY-MM-DD',
  label,
  error,
  disabled = false,
  required = false,
  minDate,
  maxDate,
  className = '',
  style,
  popoverDirection = 'auto',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [typedValue, setTypedValue] = useState(value || '');
  const [monthPickerOpen, setMonthPickerOpen] = useState(false);
  const [yearPickerOpen, setYearPickerOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [popoverPlacement, setPopoverPlacement] = useState<{
    vertical: 'down' | 'up';
    horizontal: 'left' | 'right';
  }>({ vertical: 'down', horizontal: 'left' });

  // Update placement to avoid overflowing offscreen
  const updatePlacement = () => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const popoverHeight = 330;
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;

    let vertical: 'down' | 'up' = 'down';
    if (popoverDirection === 'up') {
      vertical = 'up';
    } else if (popoverDirection === 'down') {
      vertical = 'down';
    } else {
      if (spaceBelow < popoverHeight && spaceAbove > spaceBelow) {
        vertical = 'up';
      } else {
        vertical = 'down';
      }
    }

    const popoverWidth = 300;
    let horizontal: 'left' | 'right' = 'left';
    const modalEl = containerRef.current.closest('.snow-modal, [role="dialog"]');
    if (modalEl) {
      const modalRect = modalEl.getBoundingClientRect();
      if (rect.left + popoverWidth > modalRect.right - 16) {
        horizontal = 'right';
      }
    } else if (rect.left + popoverWidth > window.innerWidth - 16) {
      horizontal = 'right';
    }

    setPopoverPlacement({ vertical, horizontal });
  };

  const handleToggle = () => {
    if (disabled) return;
    if (!isOpen) {
      updatePlacement();
    }
    setIsOpen(!isOpen);
  };

  // Re-calculate placement on open, resize, or scroll
  useEffect(() => {
    if (isOpen) {
      updatePlacement();
      const onReposition = () => updatePlacement();
      window.addEventListener('resize', onReposition);
      window.addEventListener('scroll', onReposition, true);
      return () => {
        window.removeEventListener('resize', onReposition);
        window.removeEventListener('scroll', onReposition, true);
      };
    }
  }, [isOpen]);

  // Keep typedValue synced with value prop
  useEffect(() => {
    setTypedValue(value || '');
  }, [value]);

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

  // Validate and commit manual typed date
  const validateAndCommit = (rawStr: string) => {
    const trimmed = rawStr.trim();
    if (!trimmed) {
      onChange?.('');
      return;
    }

    // Try ISO format: YYYY-MM-DD or YYYY/MM/DD
    const isoMatch = trimmed.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/);
    if (isoMatch) {
      const y = parseInt(isoMatch[1], 10);
      const m = parseInt(isoMatch[2], 10);
      const d = parseInt(isoMatch[3], 10);
      if (m >= 1 && m <= 12 && d >= 1 && d <= 31) {
        const formatted = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const testDate = new Date(`${formatted}T00:00:00`);
        if (!isNaN(testDate.getTime())) {
          onChange?.(formatted);
          setViewYear(y);
          setViewMonth(m - 1);
          setTypedValue(formatted);
          return;
        }
      }
    }

    // Try parsing flexible formats (e.g. MM/DD/YYYY)
    const parsed = new Date(trimmed);
    if (!isNaN(parsed.getTime())) {
      const yyyy = parsed.getFullYear();
      const mm = String(parsed.getMonth() + 1).padStart(2, '0');
      const dd = String(parsed.getDate()).padStart(2, '0');
      const formatted = `${yyyy}-${mm}-${dd}`;
      onChange?.(formatted);
      setViewYear(yyyy);
      setViewMonth(parsed.getMonth());
      setTypedValue(formatted);
      return;
    }

    // Invalid format: reset back to current value
    setTypedValue(value || '');
  };

  // Handle click outside to close popover
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setMonthPickerOpen(false);
        setYearPickerOpen(false);
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
    setTypedValue(dateStr);
    setIsOpen(false);
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    onChange?.('');
    setTypedValue('');
    setIsOpen(false);
  };

  const handleSetToday = (e: React.MouseEvent) => {
    e.stopPropagation();
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    const dateStr = `${yyyy}-${mm}-${dd}`;
    onChange?.(dateStr);
    setTypedValue(dateStr);
    setViewYear(yyyy);
    setViewMonth(today.getMonth());
    setIsOpen(false);
  };

  // Generate calendar days
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const firstDayOfWeek = new Date(viewYear, viewMonth, 1).getDay();
  const prevMonthDays = new Date(viewYear, viewMonth, 0).getDate();

  const today = new Date();
  const isCurrentMonthToday = today.getFullYear() === viewYear && today.getMonth() === viewMonth;

  return (
    <div
      ref={containerRef}
      className={`snow-datepicker-wrapper ${className}`}
      style={{ position: 'relative', width: '100%', marginBottom: label ? 16 : 0, ...style }}
    >
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

      {/* Input trigger with editable text & calendar action */}
      <div
        className="snow-flex snow-items-center snow-justify-between"
        style={{
          height: 40,
          padding: '4px 12px',
          backgroundColor: '#FFFFFF',
          border: error ? '1px solid #EF4444' : isOpen ? '1px solid #1C1C1C' : '1px solid #E4E4E7',
          borderRadius: 10,
          opacity: disabled ? 0.6 : 1,
          transition: 'all 0.15s ease',
          boxShadow: isOpen ? '0 0 0 2px rgba(28,28,28,0.08)' : 'none',
        }}
      >
        <div className="snow-flex snow-items-center snow-gap-2" style={{ flex: 1, overflow: 'hidden' }}>
          <button
            type="button"
            onClick={handleToggle}
            aria-label="Toggle calendar"
            disabled={disabled}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: disabled ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <CalendarIcon size={16} style={{ color: isOpen ? '#1C1C1C' : '#71717A', flexShrink: 0 }} />
          </button>
          <input
            ref={inputRef}
            type="text"
            value={typedValue}
            placeholder={placeholder}
            disabled={disabled}
            onChange={(e) => {
              setTypedValue(e.target.value);
              if (/^\d{4}-\d{2}-\d{2}$/.test(e.target.value.trim())) {
                validateAndCommit(e.target.value.trim());
              }
            }}
            onFocus={() => {
              if (!isOpen) {
                updatePlacement();
                setIsOpen(true);
              }
            }}
            onBlur={() => validateAndCommit(typedValue)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                validateAndCommit(typedValue);
                setIsOpen(false);
              }
            }}
            style={{
              width: '100%',
              border: 'none',
              outline: 'none',
              backgroundColor: 'transparent',
              fontSize: 14,
              color: '#1C1C1C',
              fontFamily: 'inherit',
            }}
          />
        </div>

        {value && !disabled && (
          <button
            type="button"
            onClick={handleClear}
            style={{
              background: 'none',
              border: 'none',
              padding: 4,
              cursor: 'pointer',
              color: '#A1A1AA',
              display: 'flex',
              alignItems: 'center',
              marginLeft: 4,
            }}
          >
            <X size={14} />
          </button>
        )}
      </div>

      {error && <span className="snow-form-error">{error}</span>}

      {/* Expanded Popover Calendar with Month & Year dropdown jump selectors */}
      {isOpen && (
        <div
          className="snow-datepicker-popover"
          style={{
            position: 'absolute',
            ...(popoverPlacement.vertical === 'up'
              ? { bottom: 'calc(100% + 6px)', top: 'auto' }
              : { top: 'calc(100% + 6px)', bottom: 'auto' }),
            ...(popoverPlacement.horizontal === 'right'
              ? { right: 0, left: 'auto' }
              : { left: 0, right: 'auto' }),
            zIndex: 1100,
            width: 300,
            backgroundColor: '#FFFFFF',
            border: '1px solid #EBECEF',
            borderRadius: 16,
            padding: 16,
            boxShadow: '0 12px 32px rgba(0, 0, 0, 0.08), 0 2px 6px rgba(0, 0, 0, 0.04)',
            userSelect: 'none',
            animation: 'snowFadeIn 0.15s ease-out',
          }}
        >
          {/* Header Month / Year Dropdowns & Nav */}
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

            {/* Custom Jump Selectors for Month and Year */}
            <div className="snow-flex snow-items-center snow-gap-1">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setMonthPickerOpen((prev) => !prev);
                  setYearPickerOpen(false);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '4px 8px',
                  fontSize: 13,
                  fontWeight: 600,
                  borderRadius: 8,
                  border: monthPickerOpen ? '1px solid #007AFF' : '1px solid #E4E4E7',
                  backgroundColor: monthPickerOpen ? '#F0F7FF' : '#FFFFFF',
                  color: monthPickerOpen ? '#007AFF' : '#1C1C1C',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
                aria-label="Select month"
              >
                <span>{MONTH_NAMES[viewMonth]}</span>
                <ChevronDown size={12} style={{ transform: monthPickerOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s ease' }} />
              </button>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setYearPickerOpen((prev) => !prev);
                  setMonthPickerOpen(false);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '4px 8px',
                  fontSize: 13,
                  fontWeight: 600,
                  borderRadius: 8,
                  border: yearPickerOpen ? '1px solid #007AFF' : '1px solid #E4E4E7',
                  backgroundColor: yearPickerOpen ? '#F0F7FF' : '#FFFFFF',
                  color: yearPickerOpen ? '#007AFF' : '#1C1C1C',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
                aria-label="Select year"
              >
                <span>{viewYear}</span>
                <ChevronDown size={12} style={{ transform: yearPickerOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s ease' }} />
              </button>
            </div>

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

          {/* Body: Custom Month Grid / Custom Year Grid / Calendar Days Grid */}
          {monthPickerOpen ? (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 8,
                padding: '8px 0',
                minHeight: 216,
                alignContent: 'center',
              }}
            >
              {MONTH_NAMES.map((name, idx) => {
                const isSelected = viewMonth === idx;
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setViewMonth(idx);
                      setMonthPickerOpen(false);
                    }}
                    style={{
                      padding: '10px 6px',
                      fontSize: 12,
                      fontWeight: isSelected ? 700 : 500,
                      borderRadius: 8,
                      border: isSelected ? '1px solid #007AFF' : '1px solid #F4F5F7',
                      backgroundColor: isSelected ? '#007AFF' : '#F9FAFB',
                      color: isSelected ? '#FFFFFF' : '#374151',
                      cursor: 'pointer',
                      transition: 'all 0.12s ease',
                      textAlign: 'center',
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = '#EFF6FF';
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = '#F9FAFB';
                    }}
                  >
                    {name.substring(0, 3)}
                  </button>
                );
              })}
            </div>
          ) : yearPickerOpen ? (
            <div
              className="snow-scrollbar"
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: 6,
                padding: '6px 4px',
                maxHeight: 216,
                overflowY: 'auto',
              }}
            >
              {YEARS.map((y) => {
                const isSelected = viewYear === y;
                return (
                  <button
                    key={y}
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setViewYear(y);
                      setYearPickerOpen(false);
                    }}
                    style={{
                      padding: '7px 4px',
                      fontSize: 12,
                      fontWeight: isSelected ? 700 : 500,
                      borderRadius: 8,
                      border: isSelected ? '1px solid #007AFF' : '1px solid transparent',
                      backgroundColor: isSelected ? '#007AFF' : 'transparent',
                      color: isSelected ? '#FFFFFF' : '#374151',
                      cursor: 'pointer',
                      transition: 'all 0.12s ease',
                      textAlign: 'center',
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = '#EFF6FF';
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent';
                    }}
                  >
                    {y}
                  </button>
                );
              })}
            </div>
          ) : (
            <>
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
            </>
          )}

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
