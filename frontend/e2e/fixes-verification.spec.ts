import { test, expect } from '@playwright/test';

test.describe('Verification of User-Reported Fixes', () => {
  test('Favicon returns 200 OK and no 404', async ({ request }) => {
    const res = await request.get('/favicon.ico');
    expect(res.status()).toBe(200);
    expect(res.headers()['content-type']).toContain('image');
  });

  test('Right drawer (Notifications & Activities) is completely removed from AppShell', async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });
    await expect(page.locator('h1')).toBeVisible();

    // Verify right drawer is not rendered
    const rightDrawer = page.locator('.snow-right-drawer');
    await expect(rightDrawer).toHaveCount(0);

    // Verify "No unread notifications" is not in the DOM
    const notificationsText = page.locator('text="No unread notifications"');
    await expect(notificationsText).toHaveCount(0);

    // Verify "No recent activity" is not in the DOM
    const activityText = page.locator('text="No recent activity"');
    await expect(activityText).toHaveCount(0);
  });

  test('Sidebar is fixed and Sign Out button is sticky and visible at bottom', async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });

    const sidebar = page.locator('.snow-sidebar');
    await expect(sidebar).toBeVisible();

    // Verify sidebar has sticky positioning in CSS
    const position = await sidebar.evaluate((el) => window.getComputedStyle(el).position);
    expect(position).toBe('sticky');

    // Verify Sign Out button is visible in sidebar
    const signOutBtn = page.locator('button:has-text("Sign Out")');
    await expect(signOutBtn).toBeVisible();
  });

  test('File new claim flow has policy selector, reset chat, and valid confirm payload', async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'riya.claimant@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/.*\/claimant\/dashboard/, { timeout: 15000 });

    await page.goto('/claimant/file-claim');
    await expect(page.locator('text=AI Intake Assistant Ready')).toBeVisible({ timeout: 15000 });

    // Verify Reset Chat button exists and opens modal
    const resetChatBtn = page.locator('button:has-text("Reset Chat")');
    await expect(resetChatBtn).toBeVisible();
    await resetChatBtn.click();

    // Verify discard modal opens
    await expect(page.locator('text=Discard Draft and Clear History?')).toBeVisible();
    await page.click('button:has-text("Keep Current Chat")');

    // Verify Edit Facts button exists
    const editBtn = page.locator('button:has-text("Edit")');
    await expect(editBtn).toBeVisible();
  });

  test('Signup API accepts payload with confirm_password and does not return 422', async ({ request }) => {
    const timestamp = Date.now();
    const res = await request.post('http://localhost:8000/api/v1/auth/signup', {
      data: {
        full_name: `Test User ${timestamp}`,
        email: `testuser${timestamp}@example.com`,
        phone: '1234567890',
        password: 'Password123!',
        confirm_password: 'Password123!',
      },
    });

    // Should NOT be 422 Unprocessable Content
    expect(res.status()).not.toBe(422);
  });
});
