'use client';

import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Plus, ArrowUpDown, Search, MoreHorizontal, Copy, Eye, Download, Check, Edit2 } from 'lucide-react';
import { Button } from './Button';
import { useToast } from './Toast';
import { Checkbox } from './Checkbox';

export interface Column<T> {
  key: string;
  header: string;
  render?: (item: T) => React.ReactNode;
  width?: string;
}

export interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyField: keyof T;
  onAdd?: () => void;
  addLabel?: string;
  searchPlaceholder?: string;
  onRowClick?: (item: T) => void;
  selectedIds?: string[];
  onSelectChange?: (ids: string[]) => void;
  hideToolbar?: boolean;
  hideRowActions?: boolean;
  renderRowActions?: (item: T) => React.ReactNode;
  onEditRow?: (item: T) => void;
}

export function Table<T extends Record<string, any>>({
  columns,
  data,
  keyField,
  onAdd,
  addLabel = 'New',
  searchPlaceholder = 'Search...',
  onRowClick,
  selectedIds = [],
  onSelectChange,
  hideToolbar = false,
  hideRowActions = false,
  renderRowActions,
  onEditRow,
}: TableProps<T>) {
  const { showToast } = useToast();
  const [searchTerm, setSearchTerm] = useState('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc' | 'none'>('none');
  const [activeMenuRowId, setActiveMenuRowId] = useState<string | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<{
    rect: DOMRect;
    row: T;
    id: string;
  } | null>(null);
  const [isMounted, setIsMounted] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const actionMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Close row action menu on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (actionMenuRef.current && !actionMenuRef.current.contains(e.target as Node)) {
        setActiveMenuRowId(null);
        setMenuAnchor(null);
      }
    };
    if (activeMenuRowId) {
      document.addEventListener('mousedown', handleOutsideClick);
    }
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
    };
  }, [activeMenuRowId]);

  // Close row action menu on window scroll or resize
  useEffect(() => {
    if (!activeMenuRowId) return;
    const handleClose = () => {
      setActiveMenuRowId(null);
      setMenuAnchor(null);
    };
    window.addEventListener('scroll', handleClose, true);
    window.addEventListener('resize', handleClose);
    return () => {
      window.removeEventListener('scroll', handleClose, true);
      window.removeEventListener('resize', handleClose);
    };
  }, [activeMenuRowId]);

  // Global Cmd+K / Ctrl+K keyboard shortcut to focus search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        if (!hideToolbar && searchInputRef.current) {
          e.preventDefault();
          searchInputRef.current.focus();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [hideToolbar]);

  // Filter and sort data
  let processedData = data.filter((item) => {
    if (!searchTerm) return true;
    return Object.values(item).some(
      (val) => typeof val === 'string' && val.toLowerCase().includes(searchTerm.toLowerCase())
    );
  });

  if (sortDirection !== 'none') {
    processedData = [...processedData].sort((a, b) => {
      const firstCol = columns[0]?.key || String(keyField);
      const valA = String(a[firstCol] ?? '');
      const valB = String(b[firstCol] ?? '');
      if (sortDirection === 'asc') {
        return valA.localeCompare(valB);
      } else {
        return valB.localeCompare(valA);
      }
    });
  }

  const handleToggleSort = () => {
    if (sortDirection === 'none') {
      setSortDirection('asc');
      showToast('Sorting records ascending', 'info');
    } else if (sortDirection === 'asc') {
      setSortDirection('desc');
      showToast('Sorting records descending', 'info');
    } else {
      setSortDirection('none');
      showToast('Sorting reset to default', 'info');
    }
  };

  const toggleSelectAll = () => {
    if (!onSelectChange) return;
    if (selectedIds.length === processedData.length) {
      onSelectChange([]);
    } else {
      onSelectChange(processedData.map((d) => String(d[keyField])));
    }
  };

  const toggleSelectRow = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!onSelectChange) return;
    if (selectedIds.includes(id)) {
      onSelectChange(selectedIds.filter((item) => item !== id));
    } else {
      onSelectChange([...selectedIds, id]);
    }
  };

  const handleCopyId = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(id);
    showToast(`Copied identifier: ${id}`, 'success');
    setActiveMenuRowId(null);
  };

  return (
    <div className="snow-flex-col" style={{ width: '100%', gap: 16 }}>
      {/* Table Action Bar (hidden when hideToolbar is true) */}
      {!hideToolbar && (
        <div className="snow-table-toolbar" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div className="snow-flex snow-items-center snow-gap-2">
            {onAdd && (
              <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={onAdd}>
                {addLabel}
              </Button>
            )}
            <Button
              size="sm"
              variant={sortDirection !== 'none' ? 'secondary' : 'ghost'}
              icon={<ArrowUpDown size={14} />}
              aria-label="Sort records"
              onClick={handleToggleSort}
            />
          </div>

          <div style={{ position: 'relative', width: 240, maxWidth: '100%', flex: '1 1 200px' }}>
            <Search
              size={14}
              style={{ position: 'absolute', left: 10, top: 11, color: '#A1A1AA' }}
            />
            <input
              ref={searchInputRef}
              type="text"
              className="snow-input"
              style={{ height: 34, paddingLeft: 30, paddingRight: 40, fontSize: 13 }}
              placeholder={searchPlaceholder}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            <button
              type="button"
              className="snow-micro"
              style={{
                position: 'absolute',
                right: 8,
                top: 7,
                background: '#F4F5F7',
                border: 'none',
                cursor: 'pointer',
                padding: '2px 6px',
                borderRadius: 4,
                color: '#71717A',
                fontSize: 11,
                fontWeight: 600,
              }}
              onClick={() => searchInputRef.current?.focus()}
              title="Press ⌘K or Ctrl+K to search"
            >
              ⌘K
            </button>
          </div>
        </div>
      )}

      {/* Main Table */}
      <div className="snow-table-container snow-card" style={{ padding: 0, position: 'relative' }}>
        <table className="snow-table">
          <thead>
            <tr>
              {onSelectChange && (
                <th style={{ width: 40, textAlign: 'center' }}>
                  <Checkbox
                    checked={processedData.length > 0 && selectedIds.length === processedData.length}
                    onChange={toggleSelectAll}
                  />
                </th>
              )}
              {columns.map((col) => (
                <th key={col.key} style={{ width: col.width }}>
                  {col.header}
                </th>
              ))}
              {!hideRowActions && (
                <th style={{ width: renderRowActions ? 90 : 44, textAlign: 'right' }} />
              )}
            </tr>
          </thead>
          <tbody>
            {processedData.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length + (onSelectChange ? 1 : 0) + (!hideRowActions ? 1 : 0)}
                  style={{ textAlign: 'center', padding: '36px 0', color: '#71717A' }}
                >
                  No matching records found.
                </td>
              </tr>
            ) : (
              processedData.map((row, index) => {
                const rowId = row[keyField] ?? row.id ?? row.ticket_id ?? row.policy_number ?? row.code ?? `row-${index}`;
                const id = String(rowId);
                const isSelected = selectedIds.includes(id);
                const isMenuOpen = activeMenuRowId === id;

                return (
                  <tr
                    key={id}
                    onClick={() => onRowClick && onRowClick(row)}
                    style={{ cursor: onRowClick ? 'pointer' : 'default', position: 'relative' }}
                  >
                    {onSelectChange && (
                      <td style={{ textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          checked={isSelected}
                          onChange={(e) => toggleSelectRow(id, e as any)}
                        />
                      </td>
                    )}
                    {columns.map((col) => (
                      <td key={col.key}>
                        {col.render ? col.render(row) : row[col.key]}
                      </td>
                    ))}
                    {!hideRowActions && (
                      <td style={{ textAlign: 'right' }} onClick={(e) => e.stopPropagation()}>
                        {renderRowActions ? (
                          renderRowActions(row)
                        ) : (
                          <button
                            type="button"
                            className="snow-btn snow-btn-ghost snow-btn-sm"
                            style={{
                              background: isMenuOpen ? '#E4E4E7' : 'none',
                              border: 'none',
                              cursor: 'pointer',
                              color: '#71717A',
                              padding: 6,
                              borderRadius: 6,
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                            }}
                            aria-label="Row actions"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (isMenuOpen) {
                                setActiveMenuRowId(null);
                                setMenuAnchor(null);
                              } else {
                                const rect = e.currentTarget.getBoundingClientRect();
                                setMenuAnchor({ rect, row, id });
                                setActiveMenuRowId(id);
                              }
                            }}
                          >
                            <MoreHorizontal size={16} />
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Row Action Popover Portaled to document.body */}
      {isMounted && activeMenuRowId && menuAnchor && typeof document !== 'undefined' && createPortal(
        (() => {
          const MENU_WIDTH = 140;
          const optionsCount = (onEditRow ? 1 : 0) + (onRowClick ? 1 : 0) + 1;
          const estimatedHeight = optionsCount * 36 + 12;
          const spaceBelow = window.innerHeight - menuAnchor.rect.bottom;
          const openUp = spaceBelow < estimatedHeight + 12 && menuAnchor.rect.top > estimatedHeight;
          const top = openUp ? menuAnchor.rect.top - estimatedHeight - 4 : menuAnchor.rect.bottom + 4;
          const left = Math.max(8, Math.min(window.innerWidth - MENU_WIDTH - 8, menuAnchor.rect.right - MENU_WIDTH));

          return (
            <div
              ref={actionMenuRef}
              style={{
                position: 'fixed',
                top,
                left,
                zIndex: 9999,
                backgroundColor: '#FFFFFF',
                border: '1px solid #EBECEF',
                borderRadius: 10,
                padding: '4px',
                boxShadow: '0 10px 24px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.06)',
                minWidth: MENU_WIDTH,
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: 2,
                animation: 'snowFadeIn 0.12s ease-out',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {onEditRow && (
                <button
                  type="button"
                  className="snow-btn-ghost"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '7px 10px',
                    fontSize: 12,
                    fontWeight: 500,
                    borderRadius: 6,
                    border: 'none',
                    background: 'none',
                    cursor: 'pointer',
                    width: '100%',
                    textAlign: 'left',
                    color: '#1C1C1C',
                  }}
                  onClick={() => {
                    const r = menuAnchor.row;
                    setActiveMenuRowId(null);
                    setMenuAnchor(null);
                    onEditRow(r);
                  }}
                >
                  <Edit2 size={13} />
                  <span>Edit</span>
                </button>
              )}
              {onRowClick && (
                <button
                  type="button"
                  className="snow-btn-ghost"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '7px 10px',
                    fontSize: 12,
                    fontWeight: 500,
                    borderRadius: 6,
                    border: 'none',
                    background: 'none',
                    cursor: 'pointer',
                    width: '100%',
                    textAlign: 'left',
                    color: '#1C1C1C',
                  }}
                  onClick={() => {
                    const r = menuAnchor.row;
                    setActiveMenuRowId(null);
                    setMenuAnchor(null);
                    onRowClick(r);
                  }}
                >
                  <Eye size={13} />
                  <span>View Details</span>
                </button>
              )}
              <button
                type="button"
                className="snow-btn-ghost"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '7px 10px',
                  fontSize: 12,
                  fontWeight: 500,
                  borderRadius: 6,
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  width: '100%',
                  textAlign: 'left',
                  color: '#1C1C1C',
                }}
                onClick={(e) => {
                  const idToCopy = menuAnchor.id;
                  handleCopyId(idToCopy, e);
                  setMenuAnchor(null);
                }}
              >
                <Copy size={13} />
                <span>Copy ID</span>
              </button>
            </div>
          );
        })(),
        document.body
      )}
    </div>
  );
}
