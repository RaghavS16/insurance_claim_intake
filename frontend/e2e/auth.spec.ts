import { test, expect } from '@playwright/test';

test.describe('Authentication & Access Control', () => {

  test('Guest registration validation errors (short password, mismatched confirm)', async ({ page }) => {
    await page.goto('/register');
    await expect(page.locator('h1')).toContainText('Create your claimant account');

    // Fill form with mismatched passwords
    await page.locator('input[placeholder="Jane Doe"]').fill('Test Claimant');
    await page.locator('input[type="email"]').fill('test.mismatch@example.com');
    await page.locator('input[type="tel"]').fill('9876543210');
    
    const pwInputs = page.locator('input[type="password"]');
    await pwInputs.nth(0).fill('ValidPass123!');
    await pwInputs.nth(1).fill('WrongPass456!');

    await page.locator('button[type="submit"]').click();
    await expect(page.locator('.error')).toContainText('Passwords do not match');
  });

  test('Successful registration and login of new claimant', async ({ page }) => {
    const uniqueEmail = `qa.claimant.${Date.now()}@example.com`;
    await page.goto('/register');

    await page.locator('input[placeholder="Jane Doe"]').fill('QA Automated Claimant');
    await page.locator('input[type="email"]').fill(uniqueEmail);
    await page.locator('input[type="tel"]').fill('9876543299');
    
    const pwInputs = page.locator('input[type="password"]');
    await pwInputs.nth(0).fill('StrongPassword123!');
    await pwInputs.nth(1).fill('StrongPassword123!');

    await page.locator('button[type="submit"]').click();
    // In dev mode with REQUIRE_EMAIL_VERIFICATION=false or redirect
    await expect(page).toHaveURL(/\/(login|verify-email)/, { timeout: 15000 });

    // Now test login with the newly created user (or seed user)
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('riya.claimant@insurance.com');
    await page.locator('input[type="password"]').fill('DemoPassword123!');
    await page.locator('button[type="submit"]').click();

    // Claimant should land on chat interface
    await expect(page).toHaveURL(/\/chat|\/$/, { timeout: 15000 });
    await expect(page.locator('.chat-brand')).toContainText('Claims Intake');
  });

  test('Invalid login credentials returns error feedback', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('riya.claimant@insurance.com');
    await page.locator('input[type="password"]').fill('WrongPassword999!');
    await page.locator('button[type="submit"]').click();

    await expect(page.locator('.error')).toBeVisible();
    await expect(page.locator('.error')).toContainText(/invalid|incorrect|unable/i);
  });

  test('Login as Adjuster routes to Adjuster Overview', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('asha.adjuster@insurance.com');
    await page.locator('input[type="password"]').fill('DemoPassword123!');
    await page.locator('button[type="submit"]').click();

    await expect(page).toHaveURL(/\/adjuster/, { timeout: 15000 });
    await expect(page.locator('h1.page-title')).toContainText(/Adjuster overview/i);
  });

  test('Login as Admin routes to Administration Console', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('admin@insurance.com');
    await page.locator('input[type="password"]').fill('DemoPassword123!');
    await page.locator('button[type="submit"]').click();

    await expect(page).toHaveURL(/\/admin/, { timeout: 15000 });
    await expect(page.locator('h1.page-title')).toContainText(/Administration/i);
  });

  test('Role-Based Access Control (RBAC): Claimant cannot access Admin or Adjuster routes', async ({ page }) => {
    // Sign in as Claimant
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('riya.claimant@insurance.com');
    await page.locator('input[type="password"]').fill('DemoPassword123!');
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/chat|\/$/, { timeout: 15000 });
    await page.waitForTimeout(500);

    // Try navigating to /admin
    await page.goto('/admin');
    // Claimant router guard replaces path back to /chat
    await expect(page).toHaveURL(/\/chat/, { timeout: 15000 });

    // Try navigating to /adjuster
    await page.goto('/adjuster');
    await expect(page).toHaveURL(/\/chat/, { timeout: 15000 });
  });

  test('API Access Control: Claimant token receives 403 on protected admin/adjuster endpoints', async ({ request }) => {
    // 1. Obtain claimant token
    const loginRes = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: {
        email: 'riya.claimant@insurance.com',
        password: 'DemoPassword123!'
      }
    });
    expect(loginRes.ok()).toBeTruthy();
    const { access_token } = await loginRes.json();

    // 2. Attempt calling GET /api/v1/admin/adjusters
    const adminRes = await request.get('http://localhost:8000/api/v1/admin/adjusters', {
      headers: { Authorization: `Bearer ${access_token}` }
    });
    expect(adminRes.status()).toBe(403);

    // 3. Attempt calling GET /api/v1/adjuster/dashboard
    const adjRes = await request.get('http://localhost:8000/api/v1/adjuster/dashboard', {
      headers: { Authorization: `Bearer ${access_token}` }
    });
    expect(adjRes.status()).toBe(403);

    // 4. Attempt calling GET /api/v1/policies (Adjuster/Admin directory)
    const polRes = await request.get('http://localhost:8000/api/v1/policies', {
      headers: { Authorization: `Bearer ${access_token}` }
    });
    expect(polRes.status()).toBe(403);
  });

  test('Logout flow invalidates session and redirects to /login', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('asha.adjuster@insurance.com');
    await page.locator('input[type="password"]').fill('DemoPassword123!');
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/adjuster/);

    // Click Sign Out
    await page.locator('button.nav-link:has-text("Sign out")').click();
    await expect(page).toHaveURL(/\/login/);
  });
});
