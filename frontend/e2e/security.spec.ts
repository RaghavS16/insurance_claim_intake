import { test, expect } from '@playwright/test';

test.describe('Security & Access Controls (Real Backend)', () => {
  test('Unauthenticated user is redirected to signin when accessing protected routes', async ({ page }) => {
    // Clear any leftover tokens
    await page.goto('/signin');
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });

    // Try claimant dashboard without credentials
    await page.goto('/claimant/dashboard');
    await expect(page).toHaveURL(/.*\/signin/, { timeout: 15000 });

    // Try adjuster dashboard without credentials
    await page.goto('/adjuster/dashboard');
    await expect(page).toHaveURL(/.*\/signin/, { timeout: 15000 });

    // Try admin oversight without credentials
    await page.goto('/admin/claims');
    await expect(page).toHaveURL(/.*\/signin/, { timeout: 15000 });
  });

  test('Forgot-password request handles real submission gracefully', async ({ page }) => {
    await page.goto('/forgot-password');
    await expect(page.locator('h1')).toContainText('Forgot Password');

    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.click('button[type="submit"]');

    // Should navigate to verify-otp or display code sent toast
    await expect(page).toHaveURL(/.*\/verify-otp.*email=riya/, { timeout: 15000 });
  });
});
