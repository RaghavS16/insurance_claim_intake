import { test, expect } from '@playwright/test';

test.describe('Authentication & Session Lifecycle (Real Backend)', () => {
  test('Claimant real login, role verification, and logout', async ({ page }) => {
    await page.goto('/signin');
    await expect(page.locator('h1')).toContainText('Sign In');

    // Fill real seeded credentials
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');

    // Should redirect to claimant dashboard
    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });
    await expect(page.getByText('Riya Claimant')).toBeVisible({ timeout: 10000 });

    // Verify localStorage has real token
    const token = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(token).toBeTruthy();

    // Perform real logout
    await page.click('button:has-text("Sign Out")');
    await expect(page).toHaveURL(/.*\/signin/, { timeout: 10000 });

    // Token should be removed
    const tokenAfter = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(tokenAfter).toBeFalsy();
  });

  test('Adjuster real login and role-based redirect', async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'asha.adjuster@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/.*\/adjuster\/dashboard/, { timeout: 15000 });
    await expect(page.getByText('Asha Adjuster')).toBeVisible({ timeout: 10000 });
  });

  test('Admin real login and oversight access', async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'admin@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/.*\/admin\/claims/, { timeout: 15000 });
    await expect(page.getByText('Ops Admin')).toBeVisible({ timeout: 10000 });
  });

  test('Invalid login credentials returns honest backend error', async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'WrongPassword999!');
    await page.click('button[type="submit"]');

    // Should show error notification and remain on /signin
    await expect(page.locator('.snow-toast').filter({ hasText: /invalid|incorrect|credential/i })).toBeVisible({ timeout: 10000 });
    await expect(page).toHaveURL(/.*\/signin/);
  });

  test('Role-based route protection: Claimant blocked from Admin and Adjuster areas', async ({ page }) => {
    // Log in as Claimant
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });

    // Attempt direct navigation to Adjuster Queue
    await page.goto('/adjuster/queue');
    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 10000 });

    // Attempt direct navigation to Admin Policies
    await page.goto('/admin/policies');
    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 10000 });
  });
});
