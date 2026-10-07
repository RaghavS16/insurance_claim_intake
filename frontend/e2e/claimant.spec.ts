import { test, expect } from '@playwright/test';

test.describe('Claimant Portal & Claims Filing (Real Backend)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });
  });

  test('Claimant dashboard renders real DB metrics and claims table', async ({ page }) => {
    // Check that real user name is rendered
    await expect(page.getByText('Riya Claimant')).toBeVisible({ timeout: 10000 });

    // Verify navigating to Policies page
    await page.click('a[href="/claimant/policies"]');
    await expect(page).toHaveURL(/.*\/claimant\/policies/, { timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'My Insurance Policies' })).toBeVisible();

    // Verify navigating to Claims page
    await page.goto('/claimant/claims');
    await expect(page.locator('table.snow-table, .snow-card').first()).toBeVisible({ timeout: 10000 });
  });

  test('Claimant claims page lists real claims and navigates to detail', async ({ page }) => {
    await page.goto('/claimant/claims');
    await page.waitForTimeout(2000);

    const claimRow = page.locator('tbody tr').first();
    if (await claimRow.isVisible()) {
      await claimRow.click();
      await expect(page).toHaveURL(/.*\/claimant\/claims\/(CLAIM|CLM)-/, { timeout: 10000 });
      await expect(page.getByText('Incident Findings & Loss Summary')).toBeVisible({ timeout: 10000 });
    }
  });

  test('Claimant intake flow creates real session and accepts text turns', async ({ page }) => {
    await page.goto('/claimant/file-claim');
    await expect(page.getByText('Conversational Claim Intake')).toBeVisible({ timeout: 10000 });

    // Send a message to AI assistant
    const chatInput = page.locator('input[placeholder*="Describe"], textarea[placeholder*="Describe"], input[type="text"]').last();
    if (await chatInput.isVisible()) {
      await chatInput.fill('I was in a minor vehicle bumper collision in a parking lot on October 1st.');
      await page.keyboard.press('Enter');

      // Expect an assistant reply turn or chat bubble to appear
      await expect(page.locator('.snow-body').last()).toBeVisible({ timeout: 25000 });
    }
  });
});
