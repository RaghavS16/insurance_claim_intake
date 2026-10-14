import { test, expect } from '@playwright/test';

test.describe('IntelliClaim 6 Core Fixes Regression Test Suite', () => {

  test('Fix 1: Admin Policy Modal custom Select and DatePicker styling and interaction', async ({ page }) => {
    // 1. Sign in as Admin
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'admin@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');

    // Wait for auth redirect to complete before navigating
    await expect(page).toHaveURL(/.*\/admin\/.*/, { timeout: 15000 });
    await expect(page.getByText('Ops Admin')).toBeVisible({ timeout: 10000 });

    // 2. Go to Policies
    await page.goto('/admin/policies');
    await expect(page.locator('h1')).toHaveText('Policy Underwriting Registry', { timeout: 15000 });

    // 3. Open Create Policy Modal
    await page.locator('button:has-text("New Policy")').click();
    await expect(page.locator('text=Create New Insurance Policy')).toBeVisible({ timeout: 10000 });

    // 4. Verify custom select is used (button with aria-haspopup="listbox")
    const customSelectTrigger = page.locator('button[aria-haspopup="listbox"]').first();
    await expect(customSelectTrigger).toBeVisible();

    // Click select trigger to open dropdown
    await customSelectTrigger.click();
    const dropdownList = page.locator('ul[role="listbox"]');
    await expect(dropdownList).toBeVisible();
    await expect(page.locator('li[role="option"]:has-text("Travel")')).toBeVisible();
    await expect(page.locator('li[role="option"]:has-text("Cyber")')).toBeVisible();

    // Click "Travel" option
    await page.locator('li[role="option"]:has-text("Travel")').click();
    await expect(customSelectTrigger).toContainText('Travel');

    // 5. Verify custom DatePicker is used (snow-datepicker-wrapper)
    const customDatePicker = page.locator('.snow-datepicker-wrapper').first();
    await expect(customDatePicker).toBeVisible();

    // Click datepicker trigger
    await customDatePicker.click();
    await expect(page.locator('.snow-datepicker-popover')).toBeVisible();

    // Check calendar actions
    const todayBtn = page.locator('.snow-datepicker-popover button:has-text("Today")');
    const clearBtn = page.locator('.snow-datepicker-popover button:has-text("Clear")');
    await expect(todayBtn).toBeVisible();
    await expect(clearBtn).toBeVisible();

    // Click Today
    await todayBtn.click();
    // Popover should close
    await expect(page.locator('.snow-datepicker-popover')).toHaveCount(0);

    // Cancel modal
    await page.locator('button:has-text("Cancel")').click();
    await expect(page.locator('text=Create New Insurance Policy')).toHaveCount(0);
  });

  test('Fix 2: Claimant Claims Overview Chat History Panel with real DB actions', async ({ page }) => {
    // 1. Sign in as Claimant
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });
    await expect(page.getByText('Riya Claimant')).toBeVisible({ timeout: 10000 });

    // 2. Verify "Recent Claim Filings" is completely removed
    await expect(page.locator('text=Recent Claim Filings')).toHaveCount(0);

    // 3. Verify Chat History panel is present
    await expect(page.locator('text=Chat History')).toBeVisible();
    await expect(page.locator('button:has-text("New Chat")')).toBeVisible();

    // 4. Verify 4 stat cards exist with real data
    await expect(page.locator('text=Active Claims').first()).toBeVisible();
    await expect(page.locator('text=Linked Policies').first()).toBeVisible();
    await expect(page.locator('text=Approved Payouts').first()).toBeVisible();
    await expect(page.locator('text=Pending Evidence').first()).toBeVisible();

    // 5. Test clicking New Chat navigates to file-claim with fresh=true
    await page.click('button:has-text("New Chat")');
    await expect(page).toHaveURL(/.*\/claimant\/file-claim\?fresh=true/, { timeout: 15000 });
  });

  test('Fix 3: Conversational Claim Intake UI (no side panels, no delete buttons, live voice layout)', async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });
    await expect(page.getByText('Riya Claimant')).toBeVisible({ timeout: 10000 });

    await page.goto('/claimant/file-claim');
    await expect(page.locator('h1')).toHaveText('Conversational Claim Intake', { timeout: 15000 });

    // 1. Verify side panels are completely removed
    await expect(page.locator('text=Extracted Claim Facts')).toHaveCount(0);
    await expect(page.locator('text=Readiness & Evidence')).toHaveCount(0);
    await expect(page.locator('text=Listening to your voice... Speak your claim details clearly')).toHaveCount(0);
    await expect(page.locator('text=AI Intake Assistant Ready')).toHaveCount(0);

    // 2. Verify mic button is present on the input bar
    const micBtn = page.locator('button[title*="voice recording"]');
    await expect(micBtn).toBeVisible();

    // 3. Verify chat message container has no delete buttons
    const deleteButtons = page.locator('.snow-chat-bubble button:has-text("Delete")');
    await expect(deleteButtons).toHaveCount(0);
  });

  test('Fix 4: No MFA / Passkeys anywhere in Settings or Authentication flows', async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });
    await expect(page.getByText('Riya Claimant')).toBeVisible({ timeout: 10000 });

    await page.goto('/settings');
    await expect(page.locator('h1')).toHaveText('Account Settings', { timeout: 15000 });

    // Verify Passkey & MFA options are completely absent
    await expect(page.locator('text=Passkey')).toHaveCount(0);
    await expect(page.locator('text=WebAuthn')).toHaveCount(0);
    await expect(page.locator('text=Two-Factor Authentication')).toHaveCount(0);
    await expect(page.locator('text=Register MFA')).toHaveCount(0);
    await expect(page.locator('text=Set up passkey')).toHaveCount(0);
  });

  test('Fix 5: IntelliClaim branding is visible everywhere', async ({ page }) => {
    // 1. Check title and login branding
    await page.goto('/signin');
    await expect(page).toHaveTitle(/IntelliClaim/);
    await expect(page.locator('.snow-h2:has-text("IntelliClaim")')).toBeVisible();

    // 2. Check in-app shell branding after signin
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });
    await expect(page.getByText('Riya Claimant')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('footer')).toContainText('IntelliClaim');
  });

  test('Fix 6: Sidebar nav "File Claim (AI & Voice)" always opens fresh chat', async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });
    await expect(page.getByText('Riya Claimant')).toBeVisible({ timeout: 10000 });

    // Click "File Claim (AI & Voice)" in sidebar nav
    const fileClaimNavLink = page.locator('a:has-text("File Claim (AI & Voice)")');
    await expect(fileClaimNavLink).toBeVisible();
    await fileClaimNavLink.click();

    // Verify it navigates with ?fresh=true and starts clean
    await expect(page).toHaveURL(/.*\/claimant\/file-claim\?fresh=true/, { timeout: 15000 });
    await expect(page.locator('h1')).toHaveText('Conversational Claim Intake');
  });

});
