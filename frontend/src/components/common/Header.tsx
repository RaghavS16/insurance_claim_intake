import React from "react";
import Link from "next/link";

interface HeaderProps {
  title: string;
  userName?: string;
  userRole?: string;
  onLogout?: () => void;
  extraActions?: React.ReactNode;
}

export const Header: React.FC<HeaderProps> = ({
  title,
  userName,
  userRole,
  onLogout,
  extraActions,
}) => {
  return (
    <header className="bg-canvas border-b border-surface-container-highest px-6 py-4 flex justify-between items-center sticky top-0 z-30">
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-2xl">waves</span>
          <h1 className="font-headline text-lg font-bold text-on-surface">{title}</h1>
        </Link>
        {userRole && (
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-surface-container-high text-secondary">
            {userRole}
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        {extraActions}
        {userName && (
          <span className="text-xs text-secondary font-label hidden sm:inline">
            {userName}
          </span>
        )}
        {onLogout && (
          <button
            onClick={onLogout}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-surface border border-outline-variant hover:bg-surface-container text-secondary hover:text-error transition-colors flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-sm">logout</span>
            <span>Sign Out</span>
          </button>
        )}
      </div>
    </header>
  );
};
