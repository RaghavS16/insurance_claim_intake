'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  ShieldCheck,
  FolderOpen,
  MessageSquare,
  Users,
  Settings,
  Bell,
  Search,
  LogOut,
  PanelLeftClose,
  PanelLeft,
  PanelRightClose,
  PanelRight,
  Star,
  Activity,
  BookOpen,
  Menu,
  X,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { usePolling } from '@/lib/use-polling';
import { api } from '@/lib/api';

export interface AppShellProps {
  children: React.ReactNode;
  breadcrumbs?: string[];
  activeTitle?: string;
  rightDrawerContent?: React.ReactNode;
  hideRightDrawer?: boolean;
  noScroll?: boolean;
  contentStyle?: React.CSSProperties;
}

export const AppShell: React.FC<AppShellProps> = ({
  children,
  breadcrumbs = ['Dashboards', 'Default'],
  activeTitle,
  rightDrawerContent,
  hideRightDrawer = true,
  noScroll = false,
  contentStyle,
}) => {
  const pathname = usePathname();
  const router = useRouter();
  const { user, role, logout, isLoading } = useAuth();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [rightDrawerOpen, setRightDrawerOpen] = useState(Boolean(rightDrawerContent && !hideRightDrawer));

  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [topbarQuery, setTopbarQuery] = useState('');
  const { data: notificationsData, setData: setNotificationsData } = usePolling<any[]>(
    async () => {
      const res = await api.get<any>('/api/v1/notifications');
      const items = Array.isArray(res?.items) ? res.items : [];
      if (typeof window !== 'undefined' && user?.id) {
        const clearedKey = `intelliclaim_cleared_notifs_${user.id}`;
        const readKey = `intelliclaim_read_notifs_${user.id}`;
        try {
          const clearedIds: string[] = JSON.parse(sessionStorage.getItem(clearedKey) || '[]');
          const readIds: string[] = JSON.parse(sessionStorage.getItem(readKey) || '[]');
          return items
            .filter((it: any) => !clearedIds.includes(it.id))
            .map((it: any) => ({
              ...it,
              unread: readIds.includes(it.id) ? false : it.unread,
            }));
        } catch {
          return items;
        }
      }
      return items;
    },
    {
      intervalMs: 30000,
      enabled: Boolean(user),
      initialData: [],
    }
  );
  const notifications = notificationsData || [];
  const setNotifications = (updater: any) => {
    setNotificationsData(updater);
  };
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

  const isUnauthorized = Boolean(
    user &&
    ((role === 'CLAIMANT' && (pathname.startsWith('/adjuster') || pathname.startsWith('/admin'))) ||
      (role === 'ADJUSTER' && pathname.startsWith('/admin')))
  );

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

  if (isLoading || !user || isUnauthorized) {
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
        { label: 'System Audit Trail', href: '/admin/audit', icon: Activity },
      ];
    }
  };

  const handleTopbarSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const q = topbarQuery.trim();
      if (!q) return;
      if (q.toUpperCase().startsWith('CLM-') || q.toUpperCase().startsWith('CLAIM-')) {
        if (role === 'ADJUSTER' || role === 'ADMIN') {
          router.push(`/adjuster/claims/${encodeURIComponent(q)}`);
        } else {
          router.push(`/claimant/claims/${encodeURIComponent(q)}`);
        }
      } else if (q.toLowerCase().includes('polic')) {
        router.push(role === 'ADMIN' ? '/admin/policies' : (role === 'ADJUSTER' ? '/adjuster/policies' : '/claimant/policies'));
      } else if (q.toLowerCase().includes('know') || q.toLowerCase().includes('rag') || q.toLowerCase().includes('doc')) {
        router.push('/adjuster/knowledge');
      } else if (q.toLowerCase().includes('audit')) {
        router.push('/admin/audit');
      } else if (q.toLowerCase().includes('queue') || q.toLowerCase().includes('claim')) {
        router.push(role === 'ADJUSTER' ? '/adjuster/queue' : (role === 'ADMIN' ? '/admin/claims' : '/claimant/claims'));
      } else {
        router.push(role === 'ADJUSTER' ? `/adjuster/queue` : `/claimant/claims`);
      }
    }
  };

  const navLinks = getNavLinks();

  return (
    <div className="snow-shell">
      {/* Left Sidebar */}
      <aside className={`snow-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        {/* Brand Logo Header */}
        <div style={{ marginBottom: 18, padding: sidebarCollapsed ? '4px 0' : '2px 4px' }}>
          {sidebarCollapsed ? (
            <img
              src="/icon.png"
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
            <button
              className="snow-desktop-sidebar-btn"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#71717A' }}
              aria-label="Toggle Sidebar"
            >
              {sidebarCollapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
            </button>

            <span style={{ display: 'inline-flex', cursor: 'pointer' }} aria-label="Favorite Shortcuts">
              <Star size={16} color="#A1A1AA" />
            </span>

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
                value={topbarQuery}
                onChange={(e) => setTopbarQuery(e.target.value)}
                onKeyDown={handleTopbarSearch}
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
                aria-label="Search shortcut"
              >
                ⌘K
              </button>
            </div>

            {/* Notification Bell with Dropdown Popover */}
            <div style={{ position: 'relative' }} ref={notificationsRef}>
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
                        onClick={async () => {
                          setNotifications((prev: any[]) => prev.map((n: any) => ({ ...n, unread: false })));
                          if (typeof window !== 'undefined' && user?.id) {
                            const readKey = `intelliclaim_read_notifs_${user.id}`;
                            const allIds = notifications.map((n: any) => n.id);
                            sessionStorage.setItem(readKey, JSON.stringify(allIds));
                          }
                          try {
                            await api.post('/api/v1/notifications/mark-read', {});
                          } catch (err) {
                            console.error('Failed to persist mark-read notification state', err);
                          }
                        }}
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
                          onClick={() => {
                            setNotificationsOpen(false);
                            if (n.href) router.push(n.href);
                          }}
                          style={{
                            padding: '12px 16px',
                            borderBottom: '1px solid #F4F5F7',
                            backgroundColor: n.unread ? '#FBFBFC' : '#FFFFFF',
                            cursor: n.href ? 'pointer' : 'default',
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
                        onClick={async () => {
                          if (typeof window !== 'undefined' && user?.id) {
                            const clearedKey = `intelliclaim_cleared_notifs_${user.id}`;
                            const allIds = notifications.map((n: any) => n.id);
                            sessionStorage.setItem(clearedKey, JSON.stringify(allIds));
                          }
                          setNotifications([]);
                          try {
                            await api.post('/api/v1/notifications/clear', {});
                          } catch (err) {
                            console.error('Failed to persist clear notification state', err);
                          }
                        }}
                      >
                        Clear notifications
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {Boolean(rightDrawerContent && !hideRightDrawer) && (
              <button
                onClick={() => setRightDrawerOpen(!rightDrawerOpen)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#71717A' }}
                aria-label="Toggle Side Panel"
              >
                {rightDrawerOpen ? <PanelRightClose size={18} /> : <PanelRight size={18} />}
              </button>
            )}
          </div>
        </header>

        {/* Content View */}
        <main
          className={`snow-content ${noScroll ? 'snow-no-scroll' : ''}`}
          style={contentStyle}
        >
          {activeTitle && (
            <h1 className="snow-h1" style={{ marginBottom: 16, flexShrink: 0 }}>
              {activeTitle}
            </h1>
          )}
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
                const basePath = link.href.split('?')[0];
                const isActive = pathname === basePath || pathname.startsWith(basePath + '/');
                const Icon = link.icon;

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
