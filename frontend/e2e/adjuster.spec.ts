import { test, expect, type Page } from '@playwright/test';

async function loginAsAdjuster(page: Page) {
  page.on('console', msg => console.log('BROWSER LOG:', msg.type(), msg.text()));
  page.on('response', res => {
    if (res.url().includes('/api/')) console.log('LOGIN API RESP:', res.status(), res.url());
  });
  await page.goto('/login');
  await page.locator('input[type="email"]').fill('asha.adjuster@insurance.com');
  await page.locator('input[type="password"]').fill('DemoPassword123!');
  await page.locator('button[type="submit"]').click();
  // Wait for adjuster overview page
  await expect(page).toHaveURL(/\/adjuster/, { timeout: 20000 });
  await expect(page.locator('h1.page-title')).toContainText('Adjuster overview', { timeout: 20000 });
}

test.describe('Adjuster Capabilities & Copilot Adjudication', () => {

  test('Adjuster Dashboard KPIs and workload metrics on /adjuster', async ({ page }) => {
    await loginAsAdjuster(page);

    // Verify key operational KPI metric cards
    await expect(page.locator('.metric-label', { hasText: 'Filed claims' })).toBeVisible();
    await expect(page.locator('.metric-label', { hasText: 'Assigned to me' })).toBeVisible();
    await expect(page.locator('.metric-label', { hasText: 'SLA breaches' })).toBeVisible();

    // Verify operational workload breakdown card
    await expect(page.locator('.card-title', { hasText: 'Operational workload breakdown' })).toBeVisible();
  });

  test('Adjuster Claims Queue on /adjuster/queue and status filters', async ({ page }) => {
    await loginAsAdjuster(page);

    // Navigate to Claims Queue via sidebar
    await page.locator('aside a[href="/adjuster/queue"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Claims Queue');

    // Verify tabs
    await expect(page.locator('.tab', { hasText: 'All' })).toBeVisible();
    await expect(page.locator('.tab', { hasText: 'Under Review' })).toBeVisible();

    // Verify table lists seeded claim
    await expect(page.locator('table')).toContainText('CLM-DEMO-MOTOR-001');
  });

  test('Adjuster Workbench dossier, AI Copilot, evidence request, and decision recording', async ({ page }) => {
    page.on('console', msg => console.log('BROWSER CONSOLE:', msg.type(), msg.text()));
    page.on('response', res => {
      if (res.url().includes('/api/')) {
        console.log('API RESPONSE:', res.status(), res.url());
      }
    });
    page.on('requestfailed', req => console.log('REQ FAILED:', req.url(), req.failure()?.errorText));

    await loginAsAdjuster(page);

    // Navigate to Claims Queue first, then click Review link (client-side transition)
    await page.locator('aside a[href="/adjuster/queue"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Claims Queue');
    await page.locator('a[href*="/adjuster/claims/"]').first().click();

    await expect(page.locator('.card-title', { hasText: 'Claim overview' })).toBeVisible({ timeout: 20000 });

    // Verify Claim Dossier details rendered immediately without blocking
    await expect(page.locator('body')).toContainText('POL-DEMO-MOTOR-001');
    await expect(page.locator('body')).toContainText('Rear-end collision');

    // Verify AI Copilot Intelligence card
    await expect(page.locator('.card-title', { hasText: 'AI Copilot Intelligence' })).toBeVisible();

    // Request information from claimant
    const requestTextarea = page.locator('textarea[placeholder*="repair estimate"]');
    await requestTextarea.fill('Please provide an official garage repair quotation.');
    const sendBtn = page.locator('button:has-text("Send formal request")');
    await expect(sendBtn).toBeEnabled();
    await sendBtn.click();
    await expect(page.locator('.list-row', { hasText: 'official garage repair quotation' })).toBeVisible({ timeout: 15000 });

    // Add private internal note
    const noteTextarea = page.locator('textarea[placeholder*="internal observation"]');
    await noteTextarea.fill('Adjuster verified loss location against driver narrative.');
    const noteBtn = page.locator('button:has-text("Add internal note")');
    await expect(noteBtn).toBeEnabled();
    await noteBtn.click();

    // Record adjudication decision (Approve claim)
    await page.locator('select').first().selectOption('approve');
    await page.locator('textarea[placeholder*="statutory coverage determination"]').fill('Claim approved per policy Clause 4.1 accidental collision terms.');
    const decisionBtn = page.locator('button:has-text("Record decision")');
    await expect(decisionBtn).toBeEnabled();
    await decisionBtn.click();

    // Verify decision recorded
    await expect(page.locator('body')).toContainText(/approve/i, { timeout: 10000 });
  });

  test('Policy Verification Directory on /policies for Adjuster role', async ({ page }) => {
    await loginAsAdjuster(page);

    // Navigate to Policies via sidebar
    await page.locator('aside a[href="/policies"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Policy Verification Directory');

    // Verify comprehensive audit columns
    await expect(page.locator('table')).toContainText('Policy Number');
    await expect(page.locator('table')).toContainText('Policyholder Name');
    await expect(page.locator('table')).toContainText('Coverage / Deductible');
    await expect(page.locator('table')).toContainText('POL-DEMO-MOTOR-001');

    // Test search filter
    await page.locator('input[placeholder*="Search by policy number"]').fill('MOTOR-001');
    await page.locator('button:has-text("Search")').click();
    await expect(page.locator('table')).toContainText('POL-DEMO-MOTOR-001');
  });

  test('Knowledge Search and Management on /knowledge and /knowledge/manage', async ({ page }) => {
    await loginAsAdjuster(page);

    // Navigate to Knowledge Search via sidebar
    await page.locator('aside a[href="/knowledge"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Policy & Regulations');

    // Query policy knowledge
    await page.locator('input[placeholder*="Search policy terms"]').fill('collision damage');
    await page.locator('button:has-text("Search")').click();
    await expect(page.locator('body')).toBeVisible();

    // Navigate to Knowledge Management via sidebar
    await page.locator('aside a[href="/knowledge/manage"]').click();
    await expect(page.locator('h1.page-title')).toContainText('Knowledge management');

    // Verify indexed knowledge document list
    await expect(page.locator('table')).toContainText(/demo-motor-policy|wording|guidance/i);
  });

});
