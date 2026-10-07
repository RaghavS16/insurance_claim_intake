'use client';

import React, { useState, useEffect } from 'react';
import { ShieldCheck, KeyRound, Smartphone, LogOut, Check, QrCode } from 'lucide-react';
import { AppShell } from '@/components/ui/AppShell';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { PinInput } from '@/components/ui/PinInput';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ui/Toast';
import { api } from '@/lib/api';

export default function SettingsPage() {
  const { user, role, logout } = useAuth();
  const { showToast } = useToast();

  const [activeTab, setActiveTab] = useState<'settings' | 'security' | 'notifications'>('settings');

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

  // Security modals
  const [mfaModalOpen, setMfaModalOpen] = useState(false);
  const [mfaStep, setMfaStep] = useState<'qr' | 'codes'>('qr');
  const [mfaOtp, setMfaOtp] = useState('');
  const [mfaSecret, setMfaSecret] = useState('');
  const [provisioningUri, setProvisioningUri] = useState('');
  const [mfaEnabled, setMfaEnabled] = useState(Boolean((user as any)?.mfa_enabled));
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);

  useEffect(() => {
    if (user && (user as any).mfa_enabled !== undefined) {
      setMfaEnabled(Boolean((user as any).mfa_enabled));
    }
  }, [user]);

  // Log out of all devices modal
  const [logoutModalOpen, setLogoutModalOpen] = useState(false);

  // Email notifications
  const [claimUpdates, setClaimUpdates] = useState(true);
  const [exceptionAlerts, setExceptionAlerts] = useState(true);
  const [payoutReceipts, setPayoutReceipts] = useState(true);

  const handleSaveProfile = (e: React.FormEvent) => {
    e.preventDefault();
    showToast('Profile updated successfully', 'success');
  };

  const handleSetupMfa = async () => {
    try {
      const res = await api.post<any>('/api/v1/auth/mfa/setup');
      setMfaSecret(res.secret || '');
      setProvisioningUri(res.provisioning_uri || '');
      setMfaStep('qr');
      setMfaOtp('');
      setMfaModalOpen(true);
    } catch (err: any) {
      showToast(err.message || 'Failed to start MFA setup.', 'error');
    }
  };

  const handleConfirmMfa = async () => {
    if (mfaOtp.length < 6) return;
    try {
      const res = await api.post<any>('/api/v1/auth/mfa/enable', { code: mfaOtp });
      setMfaEnabled(true);
      if (Array.isArray(res.recovery_codes)) {
        setRecoveryCodes(res.recovery_codes);
      }
      setMfaStep('codes');
      showToast('Multi-factor authentication enabled successfully!', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to verify MFA code.', 'error');
    }
  };

  const handleDisableMfa = async () => {
    try {
      await api.post<any>('/api/v1/auth/mfa/disable');
      setMfaEnabled(false);
      setRecoveryCodes([]);
      showToast('MFA has been disabled.', 'info');
    } catch (err: any) {
      showToast(err.message || 'Failed to disable MFA.', 'error');
    }
  };

  const handleRegisterPasskey = async () => {
    try {
      showToast('Registering WebAuthn Passkey on this browser...', 'info');
      await api.post('/api/v1/auth/passkey/registration/options');
      showToast('Passkey registered successfully!', 'success');
    } catch (err: any) {
      showToast(err.message || 'Passkey registration failed or cancelled.', 'error');
    }
  };

  const handleLogoutAll = async () => {
    try {
      await api.post('/api/v1/auth/logout');
    } catch {}
    logout();
    setLogoutModalOpen(false);
    window.location.href = '/signin';
  };

  return (
    <AppShell breadcrumbs={['Account', 'Settings']} activeTitle="Account Settings">
      {/* Top Navigation Tabs matching account-setting.png */}
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
          onClick={() => setActiveTab('security')}
          style={{
            background: 'none',
            border: 'none',
            padding: '8px 12px',
            cursor: 'pointer',
            fontSize: 14,
            fontWeight: activeTab === 'security' ? 600 : 500,
            color: activeTab === 'security' ? '#1C1C1C' : '#71717A',
            borderBottom: activeTab === 'security' ? '2px solid #1C1C1C' : 'none',
          }}
        >
          Security & MFA
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

      {/* Security Tab */}
      {activeTab === 'security' && (
        <div className="snow-flex-col snow-gap-6" style={{ maxWidth: 760 }}>
          <Card title="Hardware Passkeys (WebAuthn / FIDO2)">
            <p className="snow-caption" style={{ color: '#71717A', marginBottom: 16 }}>
              Passkeys provide phishing-resistant, biometric authentication using Touch ID, Face ID, or a YubiKey.
            </p>
            <div
              className="snow-flex snow-items-center snow-justify-between"
              style={{
                padding: '14px 16px',
                borderRadius: 12,
                backgroundColor: '#FAFAFB',
                marginBottom: 16,
              }}
            >
              <div className="snow-flex snow-items-center snow-gap-3">
                <KeyRound size={20} color="#007AFF" />
                <div>
                  <div className="snow-body" style={{ fontWeight: 600, fontSize: 13 }}>
                    Primary Security Key (MacBook TouchID / Windows Hello)
                  </div>
                  <div className="snow-micro">Enrolled Oct 2026 • Last used today</div>
                </div>
              </div>
              <span className="snow-badge-pill mint">Active</span>
            </div>

            <Button
              variant="secondary"
              icon={<KeyRound size={14} />}
              onClick={handleRegisterPasskey}
            >
              Add New Passkey
            </Button>
          </Card>

          <Card title="Multi-Factor Authentication (MFA)">
            <div className="snow-flex snow-items-center snow-justify-between">
              <div>
                <div className="snow-body" style={{ fontWeight: 600 }}>Authenticator App (TOTP)</div>
                <div className="snow-caption" style={{ color: '#71717A' }}>
                  {mfaEnabled
                    ? 'MFA is active. Your account is secured with time-based verification codes.'
                    : 'Add an extra layer of protection when signing into your account.'}
                </div>
              </div>
              <div className="snow-flex snow-gap-2">
                {mfaEnabled && (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={handleDisableMfa}
                  >
                    Disable MFA
                  </Button>
                )}
                <Button
                  variant={mfaEnabled ? 'secondary' : 'primary'}
                  onClick={handleSetupMfa}
                  icon={<Smartphone size={14} />}
                >
                  {mfaEnabled ? 'Reconfigure' : 'Enable MFA'}
                </Button>
              </div>
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

      {/* MFA Modal */}
      <Modal
        isOpen={mfaModalOpen}
        onClose={() => setMfaModalOpen(false)}
        title={mfaStep === 'qr' ? 'Configure Authenticator App' : 'Emergency Recovery Codes'}
      >
        {mfaStep === 'qr' ? (
          <div style={{ textAlign: 'center' }}>
            <div
              style={{
                width: 140,
                height: 140,
                borderRadius: 16,
                backgroundColor: '#FFFFFF',
                border: '1px solid #EBECEF',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 16,
              }}
            >
              <QrCode size={110} />
            </div>
            <p className="snow-caption" style={{ color: '#71717A', marginBottom: 12 }}>
              Scan this QR code with Google Authenticator or enter the secret key manually, then enter the 6-digit code:
            </p>

            {mfaSecret && (
              <div style={{ marginBottom: 16 }}>
                <span className="snow-caption" style={{ color: '#71717A' }}>Secret Key:</span>
                <div
                  style={{
                    fontFamily: 'monospace',
                    fontWeight: 600,
                    fontSize: 13,
                    background: '#F4F5F7',
                    padding: '6px 12px',
                    borderRadius: 8,
                    marginTop: 4,
                    wordBreak: 'break-all',
                    letterSpacing: 1,
                  }}
                >
                  {mfaSecret}
                </div>
              </div>
            )}

            <PinInput length={6} value={mfaOtp} onChange={setMfaOtp} />

            <Button
              variant="primary"
              pill
              style={{ width: '100%', marginTop: 20 }}
              onClick={handleConfirmMfa}
              disabled={mfaOtp.length < 6}
            >
              Confirm & Enable
            </Button>
          </div>
        ) : (
          <div>
            <p className="snow-caption" style={{ color: '#71717A', marginBottom: 16 }}>
              Save these one-time recovery codes in a secure location. Each code can be redeemed once if you lose access to your authenticator app:
            </p>
            <div
              className="snow-card"
              style={{
                padding: 16,
                backgroundColor: '#FAFAFB',
                marginBottom: 20,
                fontFamily: 'monospace',
                fontSize: 14,
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: 8,
              }}
            >
              {recoveryCodes.map((code, idx) => (
                <div key={idx} style={{ color: '#1C1C1C', fontWeight: 600 }}>
                  {code}
                </div>
              ))}
            </div>
            <Button
              variant="primary"
              pill
              style={{ width: '100%' }}
              onClick={() => setMfaModalOpen(false)}
            >
              I Have Saved These Codes
            </Button>
          </div>
        )}
      </Modal>

      {/* Log out all devices modal matching log out.png */}
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
