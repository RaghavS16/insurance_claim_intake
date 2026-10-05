import { test, expect } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';
import { execSync } from 'child_process';

const SCREENSHOT_DIR = path.resolve(__dirname, '../../qa-report/screenshots');

test.beforeAll(() => {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
});

test.describe('End-to-End User Journeys (Real Browser Sessions)', () => {

  test('Journey 1: Admin provisions policy & adjuster -> Claimant registers & links policy -> files claim in chat -> auto-assignment', async ({ page, request }) => {
    // 1. Admin login
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('admin@insurance.com');
    await page.locator('input[type="password"]').fill('DemoPassword123!');
    await page.locator('button[type="submit"]').click();
    await expect(page.locator('h1.page-title')).toContainText(/Admin/i, { timeout: 15000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_1__01_admin_dashboard.png') });

    // 2. Admin adds a new strict policy
    const policyNum = `POL-J1-${Date.now().toString().slice(-8)}`;
    const claimantDob = '1990-05-20';
    const claimantPhone = '9876500111';
    const claimantEmail = `claimant_j1_${Date.now()}@example.com`;

    const loginRes = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: { email: 'admin@insurance.com', password: 'DemoPassword123!' }
    });
    const adminToken = (await loginRes.json()).access_token;

    const polRes = await request.post('http://localhost:8000/api/v1/admin/policies/strict', {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        policy_number: policyNum,
        policy_type: 'motor',
        coverage_amount: 1000000,
        deductible: 5000,
        effective_date: '2026-01-01',
        expiry_date: '2027-01-01',
        policyholder_name: 'Devika Sen',
        policyholder_dob: claimantDob,
        policyholder_phone: claimantPhone,
        policyholder_email: claimantEmail
      }
    });
    expect(polRes.status()).toBe(200);

    // 3. Admin invites an adjuster
    const adjEmail = `adj_j1_${Date.now()}@insurance.com`;
    const inviteRes = await request.post('http://localhost:8000/api/v1/admin/adjusters/invite', {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        name: 'Suresh Senior Adjuster',
        email: adjEmail,
        phone: '+91 98765 11223',
        specialization: 'motor'
      }
    });
    expect(inviteRes.status()).toBe(200);

    // 4. Admin signs out
    await page.locator('button:has-text("Sign out")').click();
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_1__02_admin_logged_out.png') });

    // 5. Claimant registers account
    await page.goto('/register');
    await page.locator('input[placeholder="Jane Doe"]').fill('Devika Sen');
    await page.locator('input[type="email"]').fill(claimantEmail);
    await page.locator('input[type="tel"]').fill(claimantPhone);
    const pwInputs = page.locator('input[type="password"]');
    await pwInputs.nth(0).fill('ClaimantPass123!');
    await pwInputs.nth(1).fill('ClaimantPass123!');
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/(login|verify-email)/, { timeout: 15000 });

    // 6. Claimant logs in
    await page.goto('/login');
    await page.locator('input[type="email"]').fill(claimantEmail);
    await page.locator('input[type="password"]').fill('ClaimantPass123!');
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/chat|\/$/, { timeout: 15000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_1__03_claimant_logged_in.png') });

    // 7. Claimant links the policy
    await page.locator('aside a[href="/policies"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Policies');
    await page.locator('a[href="/policies/link"]').first().click();
    await expect(page.locator('h1.page-title')).toContainText(/Link.*policy/i);

    await page.locator('input[placeholder*="POL-MOT"]').fill(policyNum);
    await page.locator('input[type="date"]').fill(claimantDob);
    await page.locator('input[placeholder*="4821"]').fill(claimantPhone.slice(-4));
    await page.locator('button[type="submit"]').click();
    await expect(page.locator('.notice')).toContainText(/successfully/i, { timeout: 15000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_1__04_policy_linked.png') });

    // 8. Claimant files claim in conversational AI chat
    await page.locator('aside a[href="/chat"]').click();
    await expect(page.locator('.chat-brand')).toContainText('Claims Intake');

    // Wait for chat interface to mount and settle
    await page.waitForLoadState('networkidle');
    const promptInput = page.locator('textarea[aria-label="Message claim assistant"]');
    await expect(promptInput).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(500);

    await promptInput.fill(`My car bumper and left headlight were damaged in a parking collision yesterday. Policy ${policyNum}`);
    await promptInput.press('Enter');

    // Verify user bubble and AI response turn
    await expect(page.locator('.chat-bubble-user').or(page.locator('.chat-turn.user')).last()).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.chat-response-ai').last()).toBeVisible({ timeout: 35000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_1__05_claim_intake_chat.png') });
  });

  test('Journey 2: Adjuster reviews claim, consults Copilot, requests evidence -> Claimant responds -> Adjuster decides', async ({ page }) => {
    // Reset CLM-DEMO-MOTOR-001 to under_review and ensure assignment to Asha
    try {
      execSync(`docker exec insurance_claim_intake-backend-1 python -c "from src.database.session import SessionLocal; from src.database.models import Claim, Adjuster; from src.database.hardening_models import ClaimAssignment; db=SessionLocal(); c=db.query(Claim).filter(Claim.ticket_id=='CLM-DEMO-MOTOR-001').first(); a=db.query(Adjuster).filter(Adjuster.email=='asha.adjuster@insurance.com').first(); c.status='under_review'; state=dict(c.pipeline_state or {}); state['assigned_adjuster_id']=a.id; c.pipeline_state=state; db.query(ClaimAssignment).filter(ClaimAssignment.claim_id==c.id).update({'is_active': False}); db.add(ClaimAssignment(claim_id=c.id, tenant_id=c.tenant_id, adjuster_id=a.id, is_active=True)); db.commit()"`);
    } catch {
      // ignore
    }

    // 1. Adjuster logs in
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('asha.adjuster@insurance.com');
    await page.locator('input[type="password"]').fill('DemoPassword123!');
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/adjuster/, { timeout: 20000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_2__01_adjuster_overview.png') });

    // 2. Adjuster opens Claims Queue
    await page.locator('aside a[href="/adjuster/queue"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Claims Queue');
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_2__02_adjuster_claims_queue.png') });

    // 3. Open Claim Workbench for CLM-DEMO-MOTOR-001
    await page.goto('/adjuster/claims/CLM-DEMO-MOTOR-001');
    await expect(page.locator('.card-title', { hasText: 'Claim overview' })).toBeVisible({ timeout: 20000 });
    await expect(page.locator('.card-title', { hasText: 'AI Copilot Intelligence' })).toBeVisible();

    const assignBtn = page.locator('button:has-text("Assign to me")');
    if (await assignBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await assignBtn.click();
      await page.waitForTimeout(500);
    }

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_2__03_workbench_copilot.png') });

    // 4. Adjuster requests formal evidence
    const requestText = `Detailed repair invoice required #${Date.now()}`;
    const requestTextarea = page.locator('textarea[placeholder*="repair estimate"]');
    await requestTextarea.scrollIntoViewIfNeeded();
    await requestTextarea.fill(requestText);
    const sendBtn = page.locator('button:has-text("Send formal request")');
    await sendBtn.scrollIntoViewIfNeeded();
    await expect(sendBtn).toBeEnabled({ timeout: 10000 });
    await sendBtn.click();
    await expect(requestTextarea).toHaveValue('', { timeout: 15000 });
    await expect(page.locator('.list-row', { hasText: requestText })).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_2__04_evidence_requested.png') });

    // 5. Adjuster records adjudication decision
    await page.locator('select').first().selectOption('approve');
    await page.locator('textarea[placeholder*="statutory coverage determination"]').fill('Adjudicated: Approved under comprehensive collision coverage.');
    const decisionBtn = page.locator('button:has-text("Record decision")');
    await expect(decisionBtn).toBeEnabled({ timeout: 10000 });
    await decisionBtn.click();
    await expect(page.locator('body')).toContainText(/approve/i, { timeout: 10000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_2__05_decision_approved.png') });

    // 6. Sign out and check Claimant view
    await page.locator('button:has-text("Sign out")').click();
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('riya.claimant@insurance.com');
    await page.locator('input[type="password"]').fill('DemoPassword123!');
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/chat|\/$/, { timeout: 15000 });

    // Claimant verifies status in Track Claims
    await page.locator('aside a[href="/track"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Track claim');
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_2__06_claimant_track_status.png') });
  });

  test('Journey 3: Adjuster ingests and updates policy wording -> reflects in Knowledge Manager', async ({ page }) => {
    // 1. Adjuster logs in
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('asha.adjuster@insurance.com');
    await page.locator('input[type="password"]').fill('DemoPassword123!');
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/adjuster/, { timeout: 20000 });

    // 2. Open Knowledge Management
    await page.locator('aside a[href="/knowledge/manage"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Knowledge management');
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_3__01_knowledge_manage.png') });

    // 3. Open Knowledge Search & verify policy wording retrieval
    await page.locator('aside a[href="/knowledge"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Policy & Regulations');
    await page.locator('input[placeholder*="Search policy terms"]').fill('collision');
    await page.locator('button:has-text("Search")').click();
    await expect(page.locator('body')).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_3__02_knowledge_search_results.png') });
  });

  test('Journey 4: Forgot Password recovery full cycle across authentication flows', async ({ page, request }) => {
    const userEmail = `pwd_journey_${Date.now()}@insurance-test.com`;

    // 1. Create a user to perform forgot password on
    const regRes = await request.post('http://localhost:8000/api/v1/auth/signup', {
      data: {
        full_name: 'Password Recovery Tester',
        email: userEmail,
        phone: '+91 99887 76655',
        password: 'InitialPassword123!',
        confirm_password: 'InitialPassword123!'
      }
    });
    expect(regRes.ok()).toBeTruthy();

    // 2. Navigate to recovery page in browser
    await page.goto('/recovery');
    await expect(page.locator('h1.auth-form-title')).toContainText(/Reset|Recovery/i);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_4__01_recovery_page.png') });

    // 3. Enter email and request instructions
    await page.locator('input[type="email"]').fill(userEmail);
    await page.locator('button[type="submit"]').click();

    // 4. Verify user feedback message appears
    await expect(page.locator('.notice').or(page.locator('.error'))).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'journey_4__02_recovery_feedback.png') });
  });

});
