'use client';

import React, { useState } from 'react';
import { Plus, Filter, ArrowUpDown, Search, MoreHorizontal, Calendar } from 'lucide-react';
import { Button } from './Button';

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
}: TableProps<T>) {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredData = data.filter((item) => {
    if (!searchTerm) return true;
    return Object.values(item).some(
      (val) => typeof val === 'string' && val.toLowerCase().includes(searchTerm.toLowerCase())
    );
  });

  const toggleSelectAll = () => {
    if (!onSelectChange) return;
    if (selectedIds.length === filteredData.length) {
      onSelectChange([]);
    } else {
      onSelectChange(filteredData.map((d) => String(d[keyField])));
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

  return (
    <div className="snow-flex-col" style={{ width: '100%', gap: 16 }}>
      {/* Table Action Bar */}
      <div className="snow-flex snow-justify-between snow-items-center">
        <div className="snow-flex snow-items-center snow-gap-2">
          {onAdd && (
            <Button size="sm" variant="secondary" icon={<Plus size={14} />} onClick={onAdd}>
              {addLabel}
            </Button>
          )}
          <Button size="sm" variant="ghost" icon={<Filter size={14} />} aria-label="Filter" />
          <Button size="sm" variant="ghost" icon={<ArrowUpDown size={14} />} aria-label="Sort" />
        </div>

        <div style={{ position: 'relative', width: 240 }}>
          <Search
            size={14}
            style={{ position: 'absolute', left: 10, top: 11, color: '#A1A1AA' }}
          />
          <input
            type="text"
            className="snow-input"
            style={{ height: 34, paddingLeft: 30, paddingRight: 40, fontSize: 13 }}
            placeholder={searchPlaceholder}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <span
            className="snow-micro"
            style={{
              position: 'absolute',
              right: 10,
              top: 8,
              background: '#F4F5F7',
              padding: '2px 5px',
              borderRadius: 4,
              color: '#71717A',
            }}
          >
            ⌘K
          </span>
        </div>
      </div>

      {/* Main Table */}
      <div className="snow-table-container snow-card" style={{ padding: 0 }}>
        <table className="snow-table">
          <thead>
            <tr>
              {onSelectChange && (
                <th style={{ width: 40, textAlign: 'center' }}>
                  <input
                    type="checkbox"
                    checked={filteredData.length > 0 && selectedIds.length === filteredData.length}
                    onChange={toggleSelectAll}
                    style={{ cursor: 'pointer' }}
                  />
                </th>
              )}
              {columns.map((col) => (
                <th key={col.key} style={{ width: col.width }}>
                  {col.header}
                </th>
              ))}
              <th style={{ width: 40 }} />
            </tr>
          </thead>
          <tbody>
            {filteredData.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length + (onSelectChange ? 2 : 1)}
                  style={{ textAlign: 'center', padding: '36px 0', color: '#71717A' }}
                >
                  No matching records found.
                </td>
              </tr>
            ) : (
              filteredData.map((row, index) => {
                const rowId = row[keyField] ?? row.id ?? row.ticket_id ?? row.policy_number ?? row.code ?? `row-${index}`;
                const id = String(rowId);
                const isSelected = selectedIds.includes(id);

                return (
                  <tr
                    key={id}
                    onClick={() => onRowClick && onRowClick(row)}
                    style={{ cursor: onRowClick ? 'pointer' : 'default' }}
                  >
                    {onSelectChange && (
                      <td style={{ textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={(e) => toggleSelectRow(id, e as any)}
                          style={{ cursor: 'pointer' }}
                        />
                      </td>
                    )}
                    {columns.map((col) => (
                      <td key={col.key}>
                        {col.render ? col.render(row) : row[col.key]}
                      </td>
                    ))}
                    <td style={{ textAlign: 'right' }}>
                      <button
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#A1A1AA' }}
                        onClick={(e) => {
                          e.stopPropagation();
                        }}
                      >
                        <MoreHorizontal size={16} />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
