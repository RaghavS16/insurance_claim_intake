import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  onPageChange,
}) => {
  const pages = Array.from({ length: Math.min(5, totalPages) }, (_, i) => i + 1);

  return (
    <div
      className="snow-flex snow-justify-center snow-items-center snow-gap-2"
      style={{ marginTop: 20 }}
    >
      {pages.map((p) => (
        <button
          key={p}
          onClick={() => onPageChange(p)}
          style={{
            minWidth: 32,
            height: 32,
            padding: '0 8px',
            borderRadius: 8,
            border: 'none',
            background: p === currentPage ? '#EBECEF' : 'transparent',
            color: '#1C1C1C',
            fontWeight: p === currentPage ? 600 : 400,
            cursor: 'pointer',
            fontSize: 13,
            transition: 'background 0.15s ease',
          }}
        >
          {p}
        </button>
      ))}
      <button
        onClick={() => onPageChange(Math.max(1, currentPage - 1))}
        disabled={currentPage === 1}
        style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          border: 'none',
          background: 'transparent',
          cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
          opacity: currentPage === 1 ? 0.4 : 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        aria-label="Previous Page"
      >
        <ChevronLeft size={16} />
      </button>
      <button
        onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
        disabled={currentPage === totalPages}
        style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          border: 'none',
          background: 'transparent',
          cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
          opacity: currentPage === totalPages ? 0.4 : 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        aria-label="Next Page"
      >
        <ChevronRight size={16} />
      </button>
    </div>
  );
};
