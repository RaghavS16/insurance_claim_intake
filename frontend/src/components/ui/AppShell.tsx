'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  FileText,
  ShieldCheck,
  FolderOpen,
  MessageSquare,
  Users,
  Settings,
  Bell,
  Search,
  ChevronRight,
  LogOut,
  PanelLeftClose,
  PanelLeft,
  PanelRightClose,
  PanelRight,
  Star,
  Activity,
  UserCheck,
  BookOpen,
  Menu,
  X,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { Button } from './Button';
import { Tooltip } from './Tooltip';

export interface AppShellProps {
  children: React.ReactNode;
  breadcrumbs?: string[];
  activeTitle?: string;
  rightDrawerContent?: React.ReactNode;
  hideRightDrawer?: boolean;
}

export const AppShell: React.FC<AppShellProps> = ({
  children,
  breadcrumbs = ['Dashboards', 'Default'],
  activeTitle,
  rightDrawerContent,
  hideRightDrawer = true,
}) => {
  const pathname = usePathname();
  const router = useRouter();
  const { user, role, logout, isLoading } = useAuth();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [rightDrawerOpen, setRightDrawerOpen] = useState(Boolean(rightDrawerContent && !hideRightDrawer));

  useEffect(() => {
    if (isLoading) return;
    if (!user) {
      router.replace('/signin');
      return;
    }
    if (role === 'CLAIMANT') {
      if (pathname.startsWith('/adjuster') || pathname.startsWith('/admin')) {
        router.replace('/claimant/dashboard');
      }
    } else if (role === 'ADJUSTER') {
      if (pathname.startsWith('/admin')) {
        router.replace('/adjuster/dashboard');
      }
    }
  }, [user, role, isLoading, pathname, router]);

  if (isLoading || !user) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#F7F9FB' }}>
        <div className="snow-caption" style={{ color: '#71717A' }}>Authenticating session...</div>
      </div>
    );
  }

  const getNavLinks = () => {
    if (role === 'CLAIMANT') {
      return [
        { label: 'Overview', href: '/claimant/dashboard', icon: LayoutDashboard },
        { label: 'File Claim (AI & Voice)', href: '/claimant/file-claim', icon: MessageSquare },
        { label: 'Track Claims', href: '/claimant/claims', icon: FolderOpen },
        { label: 'My Policies', href: '/claimant/policies', icon: ShieldCheck },
      ];
    } else if (role === 'ADJUSTER') {
      return [
        { label: 'Overview', href: '/adjuster/dashboard', icon: LayoutDashboard },
        { label: 'Claims Queue', href: '/adjuster/queue', icon: FolderOpen },
        { label: 'Policy Directory', href: '/adjuster/policies', icon: ShieldCheck },
        { label: 'Knowledge Base (RAG)', href: '/adjuster/knowledge', icon: BookOpen },
      ];
    } else {
      return [
        { label: 'Claims Oversight', href: '/admin/claims', icon: FolderOpen },
        { label: 'Adjusters Management', href: '/admin/adjusters', icon: Users },
        { label: 'Policies Management', href: '/admin/policies', icon: ShieldCheck },
        { label: 'Knowledge Base', href: '/admin/knowledge', icon: BookOpen },
        { label: 'System Audit Trail', href: '/admin/audit', icon: Activity },
      ];
    }
  };

  const navLinks = getNavLinks();

  return (
    <div className="snow-shell">
      {/* Left Sidebar */}
      <aside className={`snow-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        {/* User profile header */}
        <div className="snow-flex snow-items-center snow-gap-3" style={{ marginBottom: 24 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              backgroundColor: '#1C1C1C',
              color: '#FFFFFF',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 600,
              fontSize: 13,
              flexShrink: 0,
            }}
          >
            {user?.full_name ? user.full_name[0] : (role ? role[0] : 'U')}
          </div>
          {!sidebarCollapsed && (
            <div className="snow-flex-col" style={{ overflow: 'hidden' }}>
              <span className="snow-body" style={{ fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user?.full_name || user?.email || 'User'}
              </span>
              <span className="snow-caption" style={{ textTransform: 'capitalize' }}>
                {role ? role.toLowerCase() : ''}
              </span>
            </div>
          )}
        </div>

        {/* Section title */}
        {!sidebarCollapsed && (
          <div className="snow-caption" style={{ color: '#A1A1AA', marginBottom: 8, paddingLeft: 8 }}>
            Dashboards
          </div>
        )}

        {/* Nav Items */}
        <nav className="snow-flex-col snow-gap-1" style={{ flex: 1 }}>
          {navLinks.map((link) => {
            const Icon = link.icon;
            const isActive = pathname === link.href || pathname.startsWith(link.href + '/');

            return (
              <Link
                key={link.href}
                href={link.href}
                className="snow-flex snow-items-center snow-gap-3"
                style={{
                  padding: '8px 10px',
                  borderRadius: 8,
                  backgroundColor: isActive ? '#F4F5F7' : 'transparent',
                  color: isActive ? '#1C1C1C' : '#71717A',
                  fontWeight: isActive ? 600 : 500,
                  fontSize: 13,
                  transition: 'background-color 0.15s ease',
                }}
                title={link.label}
              >
                <Icon size={16} />
                {!sidebarCollapsed && <span>{link.label}</span>}
              </Link>
            );
          })}

          <div style={{ height: 1, backgroundColor: '#EBECEF', margin: '16px 0' }} />

          {!sidebarCollapsed && (
            <div className="snow-caption" style={{ color: '#A1A1AA', marginBottom: 8, paddingLeft: 8 }}>
              Account & System
            </div>
          )}

          <Link
            href="/settings"
            className="snow-flex snow-items-center snow-gap-3"
            style={{
              padding: '8px 10px',
              borderRadius: 8,
              backgroundColor: pathname === '/settings' ? '#F4F5F7' : 'transparent',
              color: pathname === '/settings' ? '#1C1C1C' : '#71717A',
              fontWeight: pathname === '/settings' ? 600 : 500,
              fontSize: 13,
            }}
          >
            <Settings size={16} />
            {!sidebarCollapsed && <span>Settings & Security</span>}
          </Link>
        </nav>

        {/* Fixed Sign Out Action */}
        <div style={{ marginTop: 'auto', paddingTop: 16, borderTop: '1px solid #EBECEF', flexShrink: 0 }}>
          {sidebarCollapsed ? (
            <Tooltip content="Sign Out">
              <button
                onClick={async () => {
                  await logout();
                  router.push('/signin');
                }}
                className="snow-flex snow-items-center snow-justify-center"
                style={{
                  width: '100%',
                  background: 'none',
                  border: 'none',
                  color: '#EF4444',
                  cursor: 'pointer',
                  padding: '8px 0',
                  borderRadius: 8,
                }}
                aria-label="Sign Out"
              >
                <LogOut size={16} />
              </button>
            </Tooltip>
          ) : (
            <button
              onClick={async () => {
                await logout();
                router.push('/signin');
              }}
              className="snow-flex snow-items-center snow-gap-2"
              style={{
                width: '100%',
                background: 'none',
                border: 'none',
                color: '#EF4444',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
                padding: '8px 10px',
                borderRadius: 8,
                transition: 'background-color 0.15s ease',
              }}
            >
              <LogOut size={16} />
              <span>Sign Out</span>
            </button>
          )}
        </div>
      </aside>

      {/* Main Area */}
      <div className="snow-main-wrap">
        {/* Topbar */}
        <header className="snow-topbar">
          <div className="snow-flex snow-items-center snow-gap-3">
            {/* Mobile Hamburger Menu Toggle */}
            <button
              className="snow-mobile-menu-btn"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Open Navigation Menu"
            >
              <Menu size={20} />
            </button>

            {/* Desktop Sidebar Toggle */}
            <Tooltip content={sidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}>
              <button
                className="snow-desktop-sidebar-btn"
                onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#71717A' }}
                aria-label="Toggle Sidebar"
              >
                {sidebarCollapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
              </button>
            </Tooltip>

            <Tooltip content="Favorite Shortcuts">
              <span style={{ display: 'inline-flex', cursor: 'pointer' }}>
                <Star size={16} color="#A1A1AA" />
              </span>
            </Tooltip>

            <div className="snow-flex snow-items-center snow-gap-2">
              {breadcrumbs.map((crumb, idx) => (
                <React.Fragment key={idx}>
                  <span className={idx === breadcrumbs.length - 1 ? 'snow-body' : 'snow-caption'} style={{ fontWeight: idx === breadcrumbs.length - 1 ? 600 : 400 }}>
                    {crumb}
                  </span>
                  {idx < breadcrumbs.length - 1 && <span style={{ color: '#D1D5DB' }}>/</span>}
                </React.Fragment>
              ))}
            </div>
          </div>

          <div className="snow-flex snow-items-center snow-gap-3">
            <div className="snow-topbar-search" style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: 10, top: 11, color: '#A1A1AA' }} />
              <input
                type="text"
                className="snow-input"
                style={{ height: 34, paddingLeft: 30, paddingRight: 40, width: 180, fontSize: 13 }}
                placeholder="Search..."
              />
              <span
                className="snow-micro"
                style={{
                  position: 'absolute',
                  right: 8,
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

            <Tooltip content="Notifications">
              <button
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#71717A' }}
                aria-label="Notifications"
              >
                <Bell size={18} />
              </button>
            </Tooltip>

            {Boolean(rightDrawerContent && !hideRightDrawer) && (
              <Tooltip content={rightDrawerOpen ? 'Close Side Panel' : 'Open Side Panel'}>
                <button
                  onClick={() => setRightDrawerOpen(!rightDrawerOpen)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#71717A' }}
                  aria-label="Toggle Side Panel"
                >
                  {rightDrawerOpen ? <PanelRightClose size={18} /> : <PanelRight size={18} />}
                </button>
              </Tooltip>
            )}
          </div>
        </header>

        {/* Content View */}
        <main className="snow-content">
          {activeTitle && <h1 className="snow-h1" style={{ marginBottom: 20 }}>{activeTitle}</h1>}
          {children}

          {/* Footer */}
          <footer
            className="snow-flex snow-justify-between snow-items-center"
            style={{ marginTop: 40, paddingTop: 20, borderTop: '1px solid #EBECEF', color: '#A1A1AA', fontSize: 12 }}
          >
            <div>© 2026 ApexCare Claims Platform</div>
            <div className="snow-flex snow-gap-4">
              <a href="#">About</a>
              <a href="#">Support</a>
              <a href="#">Contact Us</a>
            </div>
          </footer>
        </main>
      </div>

      {/* Right Drawer (Only when explicit content is supplied by the active screen) */}
      {!hideRightDrawer && rightDrawerOpen && rightDrawerContent && (
        <aside className="snow-right-drawer">
          {rightDrawerContent}
        </aside>
      )}

      {/* Mobile Navigation Drawer */}
      {mobileMenuOpen && (
        <div className="snow-mobile-drawer-overlay" onClick={() => setMobileMenuOpen(false)}>
          <div className="snow-mobile-drawer" onClick={(e) => e.stopPropagation()}>
            {/* Header with Close Button */}
            <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 20 }}>
              <div className="snow-flex snow-items-center snow-gap-2">
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    backgroundColor: '#1C1C1C',
                    color: '#FFFFFF',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 600,
                    fontSize: 13,
                  }}
                >
                  {user?.full_name ? user.full_name[0] : (role ? role[0] : 'U')}
                </div>
                <div>
                  <div className="snow-body" style={{ fontWeight: 600, fontSize: 14 }}>
                    {user?.full_name || user?.email || 'User'}
                  </div>
                  <div className="snow-caption" style={{ textTransform: 'capitalize', fontSize: 11 }}>
                    {role ? role.toLowerCase() : ''}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#71717A',
                  cursor: 'pointer',
                  padding: 4,
                }}
              >
                <X size={20} />
              </button>
            </div>

            <div className="snow-caption" style={{ color: '#A1A1AA', marginBottom: 8, paddingLeft: 8 }}>
              Dashboards
            </div>

            {/* Mobile Nav Links */}
            <nav className="snow-flex-col snow-gap-1" style={{ flex: 1 }}>
              {navLinks.map((link) => {
                const Icon = link.icon;
                const isActive = pathname === link.href || pathname.startsWith(link.href + '/');

                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className="snow-flex snow-items-center snow-gap-3"
                    style={{
                      padding: '10px 12px',
                      borderRadius: 8,
                      backgroundColor: isActive ? '#F4F5F7' : 'transparent',
                      color: isActive ? '#1C1C1C' : '#71717A',
                      fontWeight: isActive ? 600 : 500,
                      fontSize: 14,
                    }}
                  >
                    <Icon size={18} />
                    <span>{link.label}</span>
                  </Link>
                );
              })}

              <div style={{ height: 1, backgroundColor: '#EBECEF', margin: '16px 0' }} />

              <div className="snow-caption" style={{ color: '#A1A1AA', marginBottom: 8, paddingLeft: 8 }}>
                Account & System
              </div>

              <Link
                href="/settings"
                onClick={() => setMobileMenuOpen(false)}
                className="snow-flex snow-items-center snow-gap-3"
                style={{
                  padding: '10px 12px',
                  borderRadius: 8,
                  backgroundColor: pathname === '/settings' ? '#F4F5F7' : 'transparent',
                  color: pathname === '/settings' ? '#1C1C1C' : '#71717A',
                  fontWeight: pathname === '/settings' ? 600 : 500,
                  fontSize: 14,
                }}
              >
                <Settings size={18} />
                <span>Settings & Security</span>
              </Link>
            </nav>

            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid #EBECEF' }}>
              <button
                type="button"
                onClick={async () => {
                  await logout();
                  setMobileMenuOpen(false);
                  router.push('/signin');
                }}
                className="snow-flex snow-items-center snow-gap-2"
                style={{
                  width: '100%',
                  background: 'none',
                  border: 'none',
                  color: '#EF4444',
                  fontSize: 14,
                  fontWeight: 500,
                  cursor: 'pointer',
                  padding: '10px 12px',
                  borderRadius: 8,
                }}
              >
                <LogOut size={18} />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
