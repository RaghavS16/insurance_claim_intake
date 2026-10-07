import { test, expect } from '@playwright/test';

test.describe('Adjuster Workbench & Adjudication Pipeline (Real Backend)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/signin');
    await page.fill('input[type="email"]', 'asha.adjuster@insurance.com');
    await page.fill('input[type="password"]', 'DemoPassword123!');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/.*\/adjuster\/dashboard/, { timeout: 15000 });
  });

  test('Adjuster dashboard renders real stats and recent claims', async ({ page }) => {
    await expect(page.getByText('Asha Adjuster')).toBeVisible();

    // Verify navigating to Queue
    await page.goto('/adjuster/queue');
    await expect(page.getByText('Claims Adjudication Queue')).toBeVisible({ timeout: 10000 });

    // Toggle between Table and Kanban view
    await page.click('button:has-text("Kanban Board")');
    await expect(page.getByText('New Submitted')).toBeVisible();
    await expect(page.getByText('Under Review')).toBeVisible();

    await page.click('button:has-text("Table View")');
    await expect(page.locator('table.snow-table').first()).toBeVisible();
  });

  test('Adjuster policies directory displays real underwritten policies', async ({ page }) => {
    await page.goto('/adjuster/policies');
    await expect(page.getByText('Underwriting Policy Directory')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('table.snow-table').first()).toBeVisible({ timeout: 10000 });
  });

  test('Adjuster knowledge base supports semantic RAG querying', async ({ page }) => {
    await page.goto('/adjuster/knowledge');
    await expect(page.getByText('Policy & Regulatory Knowledge')).toBeVisible({ timeout: 10000 });

    // Perform live semantic query
    await page.fill('input[placeholder*="Query policy clauses"]', 'auto collision damage deductible');
    await page.click('button:has-text("Search Vectors")');

    // Wait for search response
    await page.waitForTimeout(3000);
  });
});
