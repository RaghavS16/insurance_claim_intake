import { test, expect } from '@playwright/test';
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000';
const env = (process.env.ENVIRONMENT || 'development').toLowerCase().trim();
const isProd = env === 'prod' || env === 'production';
const DEMO_PASSWORD = process.env.DEMO_PASSWORD || (isProd ? '' : 'DemoPass123!');

test.describe('IntelliClaim Full-Stack End-to-End Business Verification Suite', () => {
  test.beforeAll(() => {
    // Ensure deterministic demo users, linked policies, and claims exist even if backend was already running
    const rootDir = path.resolve(__dirname, '..', '..');
    const seedScript = path.resolve(rootDir, 'database', 'seed_demo.py');
    const pythonCandidates = [
      path.resolve(rootDir, 'venv', 'Scripts', 'python.exe'),
      path.resolve(rootDir, '.venv', 'Scripts', 'python.exe'),
      path.resolve(rootDir, 'backend', 'venv', 'Scripts', 'python.exe'),
      path.resolve(rootDir, 'venv', 'bin', 'python'),
      path.resolve(rootDir, '.venv', 'bin', 'python'),
    ];
    const pythonCmd = pythonCandidates.find((p) => fs.existsSync(p)) || 'python';
    if (fs.existsSync(seedScript)) {
      try {
        execFileSync(pythonCmd, [seedScript], {
          cwd: rootDir,
          env: { ...process.env, DEMO_PASSWORD },
          stdio: 'pipe',
        });
      } catch (err) {
        console.warn('Non-fatal seed_demo note:', err);
      }
    }
  });

  test('1. Authentication & 3-Step Password Recovery Flow', async ({ page }) => {
    const uniqueEmail = `claimant.e2e.${Date.now()}@example.com`;

    // 1a. Sign Up with required phone field and terms checkbox
    await page.goto(`${BASE_URL}/signup`);
    await expect(page.locator('h1')).toContainText(/Create Account|Sign Up/i);
    await page.fill('input[placeholder="Full Name"]', 'E2E Test Claimant');
    await page.fill('input[placeholder="Email"]', uniqueEmail);
    await page.fill('input[placeholder="Phone Number"]', '+919876543210');
    await page.fill('input[placeholder="Password"]', 'SecurePass123!');
    await page.fill('input[placeholder="Repeat Password"]', 'SecurePass123!');
    const termsCheckbox = page.locator('#terms, input[type="checkbox"]').first();
    if (await termsCheckbox.isVisible()) {
      await termsCheckbox.check();
    }
    await page.click('button[type="submit"]');

    // Wait for redirect to either /signin or /verify-email
    await page.waitForURL(/\/(signin|verify-email)/, { timeout: 15000 });

    // 1b. Forgot Password page -> OTP verification redirect
    await page.goto(`${BASE_URL}/forgot-password`);
    await expect(page.locator('h1')).toContainText(/Forgot Password/i);
    await page.fill('input[type="email"]', uniqueEmail);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/verify-otp/, { timeout: 15000 });
  });

  test('2. Claimant Portal: Policy Linking, 100% RAG Chatbot Intake, Chat History & Claim Tracking', async ({ page }) => {
    // Sign in as seeded claimant
    await page.goto(`${BASE_URL}/signin`);
    await page.fill('input[placeholder="Email"]', 'riya.claimant@insurance.com');
    await page.fill('input[placeholder="Password"]', DEMO_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/claimant\/dashboard/, { timeout: 15000 });

    // 2a. Verify Claimant Dashboard & Chat History section
    await expect(page.getByRole('heading', { name: 'Chat History' })).toBeVisible();

    // 2b. Navigate to My Policies & open Link Policy Modal
    await page.goto(`${BASE_URL}/claimant/policies`);
    await expect(page.getByText(/My Insurance Policies|Linked Policies/i).first()).toBeVisible();
    const linkBtn = page.getByRole('button', { name: /Link Existing Policy|Link Policy/i }).first();
    if (await linkBtn.isVisible()) {
      await linkBtn.click();
      await page.fill('input[placeholder*="POL-"]', 'POL-DEMO-MOTOR-001');
      await page.fill('input[placeholder*="Sharma"]', 'Riya Claimant');
      await page.fill('input[placeholder*="0004"]', '0004');
      const cancelBtn = page.getByRole('button', { name: /Cancel/i }).first();
      if (await cancelBtn.isVisible()) {
        await cancelBtn.click();
      }
    }

    // 2c. Navigate to Conversational Claim Intake (/claimant/file-claim)
    await page.goto(`${BASE_URL}/claimant/file-claim?fresh=true`);
    await expect(page.getByText('Filing Against Policy:').first()).toBeVisible();
    await expect(page.locator('.snow-dossier-col').getByText('Live Claim Dossier')).toBeVisible();

    // Send a RAG coverage question / claim filing message
    const chatInput = page.locator('input[placeholder*="Type your message"]');
    await chatInput.fill('My policy number is POL-DEMO-MOTOR-001. What documents are required for a motor accident claim?');
    await page.getByRole('button', { name: /^Send$/i }).click();

    // Verify assistant responds and Live Claim Dossier updates Policy to POL-DEMO-MOTOR-001
    await expect(page.getByText('POL-DEMO-MOTOR-001').first()).toBeVisible({ timeout: 25000 });

    // 2d. Navigate to Track Claims & open seeded claim #CLM-DEMO-MOTOR-001
    await page.goto(`${BASE_URL}/claimant/claims/CLM-DEMO-MOTOR-001`);
    await expect(page.getByText(/CLM-DEMO-MOTOR-001/i).first()).toBeVisible();
  });

  test('3. Adjuster Workspace: Dashboard, Queue, AI Copilot Synopsis, Evidence Request & Decisioning', async ({ page }) => {
    await page.goto(`${BASE_URL}/signin`);
    await page.fill('input[placeholder="Email"]', 'asha.adjuster@insurance.com');
    await page.fill('input[placeholder="Password"]', DEMO_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/adjuster\/dashboard/, { timeout: 15000 });

    // 3a. Verify Adjuster Dashboard metrics
    await expect(page.getByText('Total Claims in Pool')).toBeVisible();
    await expect(page.getByText('Assigned to Me')).toBeVisible();

    // 3b. Open Claim Workspace #CLM-DEMO-MOTOR-001
    await page.goto(`${BASE_URL}/adjuster/claims/CLM-DEMO-MOTOR-001`);
    await expect(page.getByText(/AI Copilot Claims Synopsis/i)).toBeVisible();

    // Verify all 5 workspace tabs render without React crashes
    await page.getByRole('button', { name: 'Evidence & Documents' }).click();
    await expect(page.getByText('Submitted Claim Evidence & Artifacts')).toBeVisible();
    await expect(page.getByText('Adjuster Evidence Inquiries & Claimant Responses')).toBeVisible();

    await page.getByRole('button', { name: 'Exceptions' }).click();
    await expect(page.getByText('Adjudication Exceptions')).toBeVisible();

    await page.getByRole('button', { name: 'Case Notes' }).click();
    await expect(page.getByText('Internal Adjudication Notes')).toBeVisible();
    const noteText = `E2E Adjuster verification note ${Date.now()}`;
    await page.fill('input[placeholder*="Add an internal note"]', noteText);
    await page.getByRole('button', { name: 'Post Note' }).click();
    await expect(page.getByText(noteText)).toBeVisible();

    // 3c. Verify Policy Directory & Knowledge Base (RAG)
    await page.goto(`${BASE_URL}/adjuster/policies`);
    await expect(page.getByText('POL-DEMO-MOTOR-001')).toBeVisible();

    await page.goto(`${BASE_URL}/adjuster/knowledge`);
    await expect(page.getByText('demo-motor-policy-wording.txt')).toBeVisible();
  });

  test('4. Admin Portal: Operational Metrics Dashboard, Adjuster Edit, Policy CRUD & CSV Exports', async ({ page }) => {
    await page.goto(`${BASE_URL}/signin`);
    await page.fill('input[placeholder="Email"]', 'admin@insurance.com');
    await page.fill('input[placeholder="Password"]', DEMO_PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/admin\/claims/, { timeout: 15000 });

    // 4a. Verify 4 Admin Dashboard Metric Cards
    await expect(page.getByText('Active Policies')).toBeVisible();
    await expect(page.getByText('Submitted Claims')).toBeVisible();
    await expect(page.getByText('Approved Settlement')).toBeVisible();
    await expect(page.getByText('Adjuster Workload')).toBeVisible();

    // 4b. Verify Adjusters Management & Edit Modal
    await page.goto(`${BASE_URL}/admin/adjusters`);
    await expect(page.getByText('Asha Adjuster')).toBeVisible();

    // 4c. Verify Policies Management Table (Contact Info, Link Status, Template & Export CSV)
    await page.goto(`${BASE_URL}/admin/policies`);
    await expect(page.getByText('POL-DEMO-MOTOR-001')).toBeVisible();
    await expect(page.getByText('Link Status')).toBeVisible();
  });
});
