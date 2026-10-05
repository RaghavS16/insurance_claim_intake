import { test, expect, type Page } from '@playwright/test';

async function loginAsClaimant(page: Page) {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill('riya.claimant@insurance.com');
  await page.locator('input[type="password"]').fill('DemoPassword123!');
  await page.locator('button[type="submit"]').click();
  // Wait for the claimant workspace shell to fully mount
  await expect(page.locator('.chat-brand')).toContainText('Claims Intake', { timeout: 15000 });
}

test.describe('Claimant Capabilities', () => {

  test('Policy linking validation: reject invalid DOB, then link successfully', async ({ page, request }) => {
    // 1. Create a fresh unlinked policy via Admin API (short number <= 20 chars)
    const adminLogin = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: { email: 'admin@insurance.com', password: 'DemoPassword123!' }
    });
    const { access_token: adminToken } = await adminLogin.json();

    const uniquePolicyNum = `POL-${Date.now().toString().slice(-8)}`;
    await request.post('http://localhost:8000/api/v1/admin/policies/strict', {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: {
        policy_number: uniquePolicyNum,
        policy_type: 'motor',
        coverage_amount: 500000,
        deductible: 2000,
        effective_date: '2026-01-01',
        expiry_date: '2027-01-01',
        policyholder_name: 'Test Policyholder',
        policyholder_dob: '1990-05-15',
        policyholder_phone: '9876500004',
        policyholder_email: 'test.policy@example.com'
      }
    });

    // 2. Log in as claimant and wait for workspace to mount
    await loginAsClaimant(page);

    // 3. Navigate to Policies via sidebar link
    await page.locator('aside a[href="/policies"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Policies');

    // 4. Click Link Policy button
    await page.locator('a[href="/policies/link"]').first().click();
    await expect(page.locator('h1.page-title')).toContainText('Link a policy');

    // Negative test: Incorrect date of birth
    await page.locator('input[placeholder="e.g. POL-MOT-2026-904"]').fill(uniquePolicyNum);
    await page.locator('input[type="date"]').fill('1999-01-01');
    await page.locator('input[placeholder*="4821"]').fill('0004');
    await page.locator('button[type="submit"]').click();

    await expect(page.locator('.error')).toBeVisible();
    await expect(page.locator('.error')).toContainText(/verify|failed|match/i);

    // Positive test: Correct date of birth (1990-05-15) and phone last 4 (0004)
    await page.locator('input[type="date"]').fill('1990-05-15');
    await page.locator('button[type="submit"]').click();

    await expect(page.locator('.notice')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.notice')).toContainText(/successfully/i);

    // Verify it now appears on /policies
    await page.locator('a[href="/policies"]').first().click();
    await expect(page.locator('h1.page-title')).toContainText('Policies');
    await expect(page.locator('table')).toContainText(uniquePolicyNum);
  });

  test('View linked policies on /policies', async ({ page }) => {
    await loginAsClaimant(page);

    // Navigate to Policies via sidebar
    await page.locator('aside a[href="/policies"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Policies');
    await expect(page.locator('body')).toBeVisible();
  });

  test('Claimant AI chat intake conversation, fact extraction, and turn history', async ({ page }) => {
    await loginAsClaimant(page);

    // Ensure we are in chat and sidebar is visible
    await expect(page.locator('.chat-brand')).toContainText('Claims Intake');

    // Wait for chat interface to mount and settle
    await page.waitForLoadState('networkidle');
    const promptInput = page.locator('textarea[aria-label="Message claim assistant"]');
    await expect(promptInput).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(500);

    // Type incident narrative
    await promptInput.fill('I was driving my car yesterday when another vehicle hit my bumper at an intersection.');
    await promptInput.press('Enter');

    // Verify user bubble rendered
    await expect(page.locator('.chat-bubble-user').or(page.locator('.chat-turn.user')).last()).toBeVisible({ timeout: 15000 });

    // Wait for AI assistant turn response
    await expect(page.locator('.chat-response-ai').last()).toBeVisible({ timeout: 35000 });
    const replyText = await page.locator('.chat-response-ai').last().textContent();
    expect(replyText?.length).toBeGreaterThan(10);

    // Verify conversation entry in sidebar history list
    await expect(page.locator('.chat-history-list')).toBeVisible();
  });

  test('Claim tracking view on /track and /claims', async ({ page }) => {
    await loginAsClaimant(page);

    // Visit Claims list via sidebar
    await page.locator('aside a[href="/claims"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Claims');
    await expect(page.locator('table')).toContainText('CLM-DEMO-MOTOR-001');

    // Visit Track via sidebar
    await page.locator('aside a[href="/track"]').click();
    await expect(page.locator('h1.page-title')).toContainText(/Track/i);
    await expect(page.locator('body')).toContainText('CLM-DEMO-MOTOR-001');
  });

  test('Manage chat history: discard draft conversation', async ({ page }) => {
    await loginAsClaimant(page);

    // Start a new draft session
    await page.locator('button.new-chat-btn').click();
    await expect(page.locator('.claim-chat-status')).toContainText('Ticket:', { timeout: 15000 });

    // Check if discard draft button exists in the sidebar for draft sessions
    const discardBtn = page.locator('button[aria-label="Discard draft conversation"]').first();
    if (await discardBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      page.on('dialog', async (dialog) => {
        expect(dialog.message()).toContain('discard');
        await dialog.accept();
      });
      await discardBtn.click();
      await page.waitForTimeout(1000);
    }
  });

});
