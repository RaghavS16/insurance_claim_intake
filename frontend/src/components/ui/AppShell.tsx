'use client';

import React, { useState, useEffect, useRef } from 'react';
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

  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<any[]>([
    { id: '1', title: 'IntelliClaim Engine Active', message: 'Claims intake and policy verification pipeline operational.', time: 'Just now', unread: true },
  ]);

  useEffect(() => {
    if (!user) return;
    import('@/lib/api').then(({ api }) => {
      api.get<any>('/api/v1/notifications')
        .then((res) => {
          if (Array.isArray(res?.items) && res.items.length > 0) {
            setNotifications(res.items);
          }
        })
        .catch(() => {});
    });
  }, [user, pathname]);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const notificationsRef = useRef<HTMLDivElement>(null);

  // Close notifications on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (notificationsRef.current && !notificationsRef.current.contains(e.target as Node)) {
        setNotificationsOpen(false);
      }
    };
    if (notificationsOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [notificationsOpen]);

  // Global Cmd+K / Ctrl+K shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

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
        { label: 'File Claim (AI & Voice)', href: '/claimant/file-claim?fresh=true', icon: MessageSquare },
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
        { label: 'Knowledge Base (RAG)', href: '/adjuster/knowledge', icon: BookOpen },
        { label: 'System Audit Trail', href: '/admin/audit', icon: Activity },
      ];
    }
  };

  const navLinks = getNavLinks();

  return (
    <div className="snow-shell">
      {/* Left Sidebar */}
      <aside className={`snow-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        {/* Brand Logo Header */}
        <div style={{ marginBottom: 18, padding: sidebarCollapsed ? '4px 0' : '2px 4px' }}>
          <Link href={role === 'CLAIMANT' ? '/claimant/dashboard' : role === 'ADJUSTER' ? '/adjuster/dashboard' : '/admin/claims'}>
            {sidebarCollapsed ? (
              <img
                src="/secondary-logo.png"
                alt="IntelliClaim"
                style={{ width: 36, height: 36, objectFit: 'contain', display: 'block', margin: '0 auto', borderRadius: 8 }}
              />
            ) : (
              <img
                src="/primary-logo.png"
                alt="IntelliClaim"
                style={{ width: 175, height: 'auto', maxHeight: 56, objectFit: 'contain', display: 'block' }}
              />
            )}
          </Link>
        </div>

        {/* User profile header */}
        <div className="snow-flex snow-items-center snow-gap-3" style={{ marginBottom: 20 }}>
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
            const basePath = link.href.split('?')[0];
            const isActive = pathname === basePath || pathname.startsWith(basePath + '/');

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
            {!sidebarCollapsed && <span>Settings</span>}
          </Link>
        </nav>

        {/* Fixed Sign Out Action */}
        <div style={{ marginTop: 'auto', paddingTop: 16, borderTop: '1px solid #EBECEF', flexShrink: 0 }}>
          {sidebarCollapsed ? (
            <Tooltip content="Sign Out" position="right">
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
            <Tooltip content={sidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'} position="bottom">
              <button
                className="snow-desktop-sidebar-btn"
                onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#71717A' }}
                aria-label="Toggle Sidebar"
              >
                {sidebarCollapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
              </button>
            </Tooltip>

            <Tooltip content="Favorite Shortcuts" position="bottom">
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
                ref={searchInputRef}
                type="text"
                className="snow-input"
                style={{ height: 34, paddingLeft: 30, paddingRight: 40, width: 180, fontSize: 13 }}
                placeholder="Search..."
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
                  padding: '2px 5px',
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

            {/* Notification Bell with Dropdown Popover */}
            <div style={{ position: 'relative' }} ref={notificationsRef}>
              <Tooltip content="Notifications" position="bottom">
                <button
                  type="button"
                  style={{
                    background: notificationsOpen ? '#E4E4E7' : 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: '#71717A',
                    position: 'relative',
                    padding: '6px',
                    borderRadius: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                  aria-label="Notifications"
                  onClick={() => setNotificationsOpen(!notificationsOpen)}
                >
                  <Bell size={18} />
                  {notifications.some((n) => n.unread) && (
                    <span
                      style={{
                        position: 'absolute',
                        top: 4,
                        right: 4,
                        width: 7,
                        height: 7,
                        borderRadius: '50%',
                        backgroundColor: '#10B981',
                      }}
                    />
                  )}
                </button>
              </Tooltip>

              {notificationsOpen && (
                <div
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: 'calc(100% + 8px)',
                    zIndex: 1300,
                    backgroundColor: '#FFFFFF',
                    border: '1px solid #EBECEF',
                    borderRadius: 14,
                    width: 320,
                    boxShadow: '0 12px 32px rgba(0,0,0,0.08), 0 2px 6px rgba(0,0,0,0.04)',
                    overflow: 'hidden',
                    animation: 'snowFadeIn 0.12s ease-out',
                  }}
                >
                  <div
                    style={{
                      padding: '12px 16px',
                      borderBottom: '1px solid #F4F4F5',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
                      Notifications ({notifications.filter((n) => n.unread).length} unread)
                    </div>
                    {notifications.length > 0 && (
                      <button
                        type="button"
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#007AFF',
                          fontSize: 12,
                          cursor: 'pointer',
                          fontWeight: 500,
                        }}
                        onClick={() =>
                          setNotifications((prev) => prev.map((n) => ({ ...n, unread: false })))
                        }
                      >
                        Mark all read
                      </button>
                    )}
                  </div>

                  <div style={{ maxHeight: 260, overflowY: 'auto' }}>
                    {notifications.length === 0 ? (
                      <div style={{ padding: '24px 16px', textAlign: 'center', color: '#A1A1AA', fontSize: 13 }}>
                        No new notifications
                      </div>
                    ) : (
                      notifications.map((n) => (
                        <div
                          key={n.id}
                          style={{
                            padding: '12px 16px',
                            borderBottom: '1px solid #F4F5F7',
                            backgroundColor: n.unread ? '#FBFBFC' : '#FFFFFF',
                            transition: 'background-color 0.1s ease',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
                            <div className="snow-body" style={{ fontWeight: 600, fontSize: 12 }}>
                              {n.title}
                            </div>
                            <span className="snow-caption" style={{ fontSize: 11, color: '#A1A1AA' }}>
                              {n.time}
                            </span>
                          </div>
                          <div className="snow-caption" style={{ color: '#71717A', fontSize: 12 }}>
                            {n.message}
                          </div>
                        </div>
                      ))
                    )}
                  </div>

                  {notifications.length > 0 && (
                    <div style={{ padding: '8px 16px', textAlign: 'center', backgroundColor: '#FAFAFA', borderTop: '1px solid #F4F5F7' }}>
                      <button
                        type="button"
                        style={{ background: 'none', border: 'none', color: '#EF4444', fontSize: 12, cursor: 'pointer' }}
                        onClick={() => setNotifications([])}
                      >
                        Clear notifications
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {Boolean(rightDrawerContent && !hideRightDrawer) && (
              <Tooltip content={rightDrawerOpen ? 'Close Side Panel' : 'Open Side Panel'} position="bottom">
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
            {/* Header with Brand Logo & Close Button */}
            <div className="snow-flex snow-justify-between snow-items-center" style={{ marginBottom: 16 }}>
              <img
                src="/primary-logo.png"
                alt="IntelliClaim"
                style={{ width: 155, height: 'auto', objectFit: 'contain' }}
              />
              <button
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#71717A',
                  cursor: 'pointer',
                  padding: 4,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                aria-label="Close navigation"
              >
                <X size={20} />
              </button>
            </div>

            {/* User profile row */}
            <div className="snow-flex snow-items-center snow-gap-2" style={{ marginBottom: 20 }}>
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
