'use client';

import React, { useState, useEffect } from 'react';
import { LogOut, Check } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

export default function SettingsPage() {
  const { user, role, logout, updateUser } = useAuth();
  const { showToast } = useToast();

  const [activeTab, setActiveTab] = useState<'settings' | 'notifications'>('settings');

  // Profile fields
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [email, setEmail] = useState('');
  const [statusActive, setStatusActive] = useState(true);

  useEffect(() => {
    if (user) {
      const parts = (user.full_name || '').split(' ');
      setFirstName(parts[0] || '');
      setLastName(parts.slice(1).join(' ') || '');
      setContactPhone(user.phone || '');
      setEmail(user.email || '');
      setStatusActive(user.status === 'active');
    }
  }, [user]);

  // Log out of all devices modal
  const [logoutModalOpen, setLogoutModalOpen] = useState(false);

  // Email notifications
  const [claimUpdates, setClaimUpdates] = useState(true);
  const [exceptionAlerts, setExceptionAlerts] = useState(true);
  const [payoutReceipts, setPayoutReceipts] = useState(true);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const fullName = `${firstName} ${lastName}`.trim();
      const updated = await api.patch<any>('/api/v1/auth/me', {
        full_name: fullName || undefined,
        phone: contactPhone.trim(),
      });
      if (updated) {
        updateUser(updated);
      }
      showToast('Profile updated successfully', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to update profile.', 'error');
    }
  };

  const handleLogoutAll = async () => {
    try {
      await api.post('/api/v1/auth/logout');
    } catch {
      // Ignore network errors during remote session invalidation
    }
    logout();
    setLogoutModalOpen(false);
    window.location.href = '/signin';
  };

  return (
    <AppShell breadcrumbs={['Account', 'Settings']} activeTitle="Account Settings">
      {/* Top Navigation Tabs */}
      <div
        className="snow-flex snow-gap-4"
        style={{
          borderBottom: '1px solid #EBECEF',
          marginBottom: 24,
          paddingBottom: 4,
        }}
      >
        <button
          onClick={() => setActiveTab('settings')}
          style={{
            background: 'none',
            border: 'none',
            padding: '8px 12px',
            cursor: 'pointer',
            fontSize: 14,
            fontWeight: activeTab === 'settings' ? 600 : 500,
            color: activeTab === 'settings' ? '#1C1C1C' : '#71717A',
            borderBottom: activeTab === 'settings' ? '2px solid #1C1C1C' : 'none',
          }}
        >
          Profile Details
        </button>

        <button
          onClick={() => setActiveTab('notifications')}
          style={{
            background: 'none',
            border: 'none',
            padding: '8px 12px',
            cursor: 'pointer',
            fontSize: 14,
            fontWeight: activeTab === 'notifications' ? 600 : 500,
            color: activeTab === 'notifications' ? '#1C1C1C' : '#71717A',
            borderBottom: activeTab === 'notifications' ? '2px solid #1C1C1C' : 'none',
          }}
        >
          Preferences
        </button>
      </div>

      {/* Profile Details Tab */}
      {activeTab === 'settings' && (
        <div className="snow-flex-col snow-gap-6" style={{ maxWidth: 760 }}>
          <Card title="Profile Details">
            <form onSubmit={handleSaveProfile}>
              <div className="snow-flex snow-gap-4">
                <div style={{ flex: 1 }}>
                  <Input
                    label="First Name"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <Input
                    label="Last Name"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                  />
                </div>
              </div>

              <div className="snow-flex snow-gap-4">
                <div style={{ flex: 1 }}>
                  <Input
                    label="Contact Phone"
                    value={contactPhone}
                    onChange={(e) => setContactPhone(e.target.value)}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <Input
                    label="Assigned Role"
                    value={role || ''}
                    disabled
                  />
                </div>
              </div>

              <Input
                label="Email Address"
                value={email}
                disabled
              />

              <div className="snow-flex snow-items-center snow-justify-between" style={{ marginTop: 8, marginBottom: 20 }}>
                <div>
                  <div className="snow-body" style={{ fontWeight: 600 }}>Active Status</div>
                  <div className="snow-caption" style={{ color: '#71717A' }}>Allow account to receive notifications and claim actions</div>
                </div>
                <label className="snow-switch">
                  <input
                    type="checkbox"
                    checked={statusActive}
                    onChange={(e) => setStatusActive(e.target.checked)}
                  />
                  <span className="snow-switch-slider" />
                </label>
              </div>

              <Button type="submit" variant="primary">
                Save Changes
              </Button>
            </form>
          </Card>

          <Card title="Session Management">
            <div className="snow-flex snow-items-center snow-justify-between">
              <div>
                <div className="snow-body" style={{ fontWeight: 600 }}>Log Out of All Devices</div>
                <div className="snow-caption" style={{ color: '#71717A' }}>
                  Revokes all active JWT sessions across browsers and mobile clients.
                </div>
              </div>
              <Button
                variant="secondary"
                icon={<LogOut size={14} />}
                onClick={() => setLogoutModalOpen(true)}
              >
                Log Out All
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Notifications Tab */}
      {activeTab === 'notifications' && (
        <div className="snow-flex-col snow-gap-6" style={{ maxWidth: 760 }}>
          <Card title="Email Preferences">
            <div className="snow-flex-col snow-gap-4">
              <label className="snow-flex snow-items-center snow-gap-3" style={{ cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={claimUpdates}
                  onChange={(e) => setClaimUpdates(e.target.checked)}
                />
                <div>
                  <div className="snow-body" style={{ fontWeight: 600 }}>Claim Status Transitions</div>
                  <div className="snow-caption">Instant notification when claim is reviewed, approved, or escalated.</div>
                </div>
              </label>

              <label className="snow-flex snow-items-center snow-gap-3" style={{ cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={exceptionAlerts}
                  onChange={(e) => setExceptionAlerts(e.target.checked)}
                />
                <div>
                  <div className="snow-body" style={{ fontWeight: 600 }}>Adjudication Exception Inquiries</div>
                  <div className="snow-caption">Receive notification when adjuster requests additional receipts or police reports.</div>
                </div>
              </label>

              <label className="snow-flex snow-items-center snow-gap-3" style={{ cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={payoutReceipts}
                  onChange={(e) => setPayoutReceipts(e.target.checked)}
                />
                <div>
                  <div className="snow-body" style={{ fontWeight: 600 }}>Payout & Settlement Dispatches</div>
                  <div className="snow-caption">Delivery notices for approved claims payouts and direct deposit settlements.</div>
                </div>
              </label>
            </div>

            <Button
              variant="primary"
              style={{ marginTop: 20 }}
              onClick={() => showToast('Preferences updated', 'success')}
            >
              Save Preferences
            </Button>
          </Card>
        </div>
      )}

      {/* Log out all devices modal */}
      <Modal
        isOpen={logoutModalOpen}
        onClose={() => setLogoutModalOpen(false)}
        title="Log out of all devices"
      >
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <p className="snow-body" style={{ marginBottom: 24 }}>
            You will be logged out from other active sessions for{' '}
            <strong>{user?.email || 'user@example.com'}</strong>.
          </p>
          <div className="snow-flex snow-gap-3 snow-justify-center">
            <Button variant="secondary" onClick={() => setLogoutModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleLogoutAll}>
              OK
            </Button>
          </div>
        </div>
      </Modal>
    </AppShell>
  );
}
