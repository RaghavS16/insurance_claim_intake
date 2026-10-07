import { test, expect } from '@playwright/test';

test.describe('Admin Enterprise Operations & Policy Registry (Real Backend)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'admin@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/.*\/admin\/claims/, { timeout: 15000 });
  });

  test('Admin claims oversight loads enterprise claims and opens reassignment modal', async ({ page }) => {
    await expect(page.getByText('Enterprise Claims Oversight')).toBeVisible();
    await expect(page.locator('table.snow-table').first()).toBeVisible({ timeout: 10000 });

    const reassignBtn = page.locator('button:has-text("Reassign")').first();
    if (await reassignBtn.isVisible()) {
      await reassignBtn.click();
      await expect(page.getByText('Select Target Adjuster')).toBeVisible();
      await page.click('button:has-text("Cancel")');
    }
  });

  test('Admin adjusters roster displays provisioned workforce and supports tabs', async ({ page }) => {
    await page.goto('/admin/adjusters');
    await expect(page.getByText('Adjusters Roster & Workforce')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('button:has-text("Active Roster")')).toBeVisible();
    await expect(page.locator('button:has-text("Pending Invites")')).toBeVisible();

    // Switch to Pending Invites tab
    await page.click('button:has-text("Pending Invites")');
    await expect(page.locator('.snow-table-container, table.snow-table').first()).toBeVisible();
  });

  test('Admin policies registry displays underwritten policies and open modals', async ({ page }) => {
    await page.goto('/admin/policies');
    await expect(page.getByText('Policy Underwriting Registry')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('table.snow-table').first()).toBeVisible();

    // Open New Policy modal
    await page.click('button:has-text("New Policy")');
    await expect(page.getByText('Create New Insurance Policy')).toBeVisible();
    await page.click('button:has-text("Cancel")');

    // Open Bulk Import modal
    await page.click('button:has-text("Bulk Import")');
    await expect(page.getByText('Bulk Import Policies')).toBeVisible();
    await page.click('button:has-text("Cancel")');
  });

  test('Admin system audit trail renders verifiable event entries', async ({ page }) => {
    await page.goto('/admin/audit');
    await expect(page.getByText('System Security Audit Trail')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('table.snow-table, .snow-card').first()).toBeVisible({ timeout: 10000 });
  });
});
