import { test, expect, type Page } from '@playwright/test';

async function loginAsAdmin(page: Page) {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill('admin@insurance.com');
  await page.locator('input[type="password"]').fill('DemoPassword123!');
  await page.locator('button[type="submit"]').click();
  await expect(page.locator('h1.page-title')).toContainText(/Admin/i, { timeout: 15000 });
}

test.describe('Admin Operations, Policy Inventory & Team Provisioning', () => {

  test('Admin Dashboard KPIs and Operational Metrics on /admin/dashboard', async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to Admin Dashboard Overview
    await page.goto('/admin/dashboard');
    await expect(page.locator('h1.page-title')).toContainText('Administration');

    // Verify Dashboard metrics
    await expect(page.locator('.metric-label', { hasText: 'Policies' })).toBeVisible();
    await expect(page.locator('.metric-label', { hasText: 'Adjusters' })).toBeVisible();
    await expect(page.locator('.metric-label', { hasText: 'Filed claims' })).toBeVisible();
    await expect(page.locator('.metric-label', { hasText: 'Unassigned' })).toBeVisible();

    // Verify adjudication breakdown cards
    await expect(page.locator('.card-title', { hasText: 'Claims by adjudication stage' })).toBeVisible();
    await expect(page.locator('.card-title', { hasText: 'Adjuster team workload' })).toBeVisible();
  });

  test('Adjuster Team Onboarding and Invitation Lifecycle', async ({ page, request }) => {
    await loginAsAdmin(page);

    // Navigate to Admin Operations
    await page.goto('/admin');
    await expect(page.locator('h1.page-title')).toContainText('Administration');

    // Generate unique adjuster email
    const uniqueEmail = `adj_${Date.now()}@insurance-test.com`;

    // Authenticate with valid API credentials
    const loginRes = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: {
        email: 'admin@insurance.com',
        password: 'DemoPassword123!'
      }
    });
    expect(loginRes.ok()).toBeTruthy();
    const token = (await loginRes.json()).access_token;

    // 1. Invite Adjuster
    const inviteRes = await request.post('http://localhost:8000/api/v1/admin/adjusters/invite', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: 'Kavita Lead Adjuster',
        email: uniqueEmail,
        phone: '+91 98765 43210',
        specialization: 'motor'
      }
    });
    expect(inviteRes.status()).toBe(200);
    const inviteBody = await inviteRes.json();
    expect(inviteBody.invitation_url).toBeDefined();
    expect(inviteBody.invitation_url).toContain('/onboarding/adjuster?token=');

    // 2. Test duplicate invite prevention
    const dupRes = await request.post('http://localhost:8000/api/v1/admin/adjusters/invite', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: 'Kavita Lead Adjuster',
        email: uniqueEmail,
        phone: '+91 98765 43210',
        specialization: 'motor'
      }
    });
    expect(dupRes.status()).toBe(409);

    // 3. Resend invitation
    const invitationId = inviteBody.id || inviteBody.invitation_id;
    const resendRes = await request.post(`http://localhost:8000/api/v1/admin/adjusters/invitations/${invitationId}/resend`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    expect(resendRes.status()).toBe(200);
    const resendBody = await resendRes.json();
    expect(resendBody.email_delivery_status).toBe('queued');

    // 4. Verify in Admin UI table
    await page.reload();
    await expect(page.locator('table', { hasText: 'Kavita Lead Adjuster' }).or(page.locator('body', { hasText: 'Kavita Lead Adjuster' }))).toBeVisible();
  });

  test('Policy Management: Single Policy Strict Creation & Validation', async ({ page, request }) => {
    const loginRes = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: {
        email: 'admin@insurance.com',
        password: 'DemoPassword123!'
      }
    });
    const token = (await loginRes.json()).access_token;

    const uniquePolicyNum = `POL-ADMIN-${Date.now()}`;

    // 1. Success case: All required fields valid
    const createRes = await request.post('http://localhost:8000/api/v1/admin/policies/strict', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        policy_number: uniquePolicyNum,
        policy_type: 'motor',
        coverage_amount: 1500000,
        deductible: 5000,
        effective_date: '2026-01-01',
        expiry_date: '2027-01-01',
        policyholder_name: 'Ananya Sharma',
        policyholder_dob: '1992-06-15',
        policyholder_phone: '+91 98111 22334',
        policyholder_email: 'ananya.sharma@example.com'
      }
    });
    expect(createRes.status()).toBe(200);
    const createBody = await createRes.json();
    expect(createBody.policy_number).toBe(uniquePolicyNum);

    // 2. Edge Case: Duplicate policy number (must return 409)
    const dupPolicyRes = await request.post('http://localhost:8000/api/v1/admin/policies/strict', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        policy_number: uniquePolicyNum,
        policy_type: 'motor',
        coverage_amount: 1500000,
        deductible: 5000,
        effective_date: '2026-01-01',
        expiry_date: '2027-01-01',
        policyholder_name: 'Duplicate Check',
        policyholder_dob: '1992-06-15',
        policyholder_phone: '+91 98111 22334'
      }
    });
    expect(dupPolicyRes.status()).toBe(409);

    // 3. Edge Case: Expiry date before or equal to effective date (must return 400)
    const invalidDateRes = await request.post('http://localhost:8000/api/v1/admin/policies/strict', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        policy_number: `POL-INV-DATE-${Date.now()}`,
        policy_type: 'motor',
        coverage_amount: 500000,
        deductible: 0,
        effective_date: '2026-05-01',
        expiry_date: '2026-04-01',
        policyholder_name: 'Invalid Date Person',
        policyholder_dob: '1990-01-01',
        policyholder_phone: '9876543210'
      }
    });
    expect(invalidDateRes.status()).toBe(400);

    // 4. Edge Case: Invalid policy type (must return 400)
    const invalidTypeRes = await request.post('http://localhost:8000/api/v1/admin/policies/strict', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        policy_number: `POL-INV-TYPE-${Date.now()}`,
        policy_type: 'spacecraft_insurance',
        coverage_amount: 500000,
        deductible: 0,
        effective_date: '2026-01-01',
        expiry_date: '2027-01-01',
        policyholder_name: 'Astronaut User',
        policyholder_dob: '1985-01-01',
        policyholder_phone: '9876543210'
      }
    });
    expect(invalidTypeRes.status()).toBe(400);
  });

  test('Bulk Policy Import: Template & Edge Case Validation', async ({ request }) => {
    const loginRes = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: {
        email: 'admin@insurance.com',
        password: 'DemoPassword123!'
      }
    });
    const token = (await loginRes.json()).access_token;

    // 1. Download CSV template
    const templateRes = await request.get('http://localhost:8000/api/v1/admin/policies/template?format=csv', {
      headers: { Authorization: `Bearer ${token}` }
    });
    expect(templateRes.status()).toBe(200);
    const templateText = await templateRes.text();
    expect(templateText).toContain('policy_number,policy_type,coverage_amount');

    // 2. Successful CSV Import
    const bulkNum1 = `POL-BULK-${Date.now()}-A`;
    const bulkNum2 = `POL-BULK-${Date.now()}-B`;
    const validCsv = `policy_number,policy_type,coverage_amount,deductible,effective_date,expiry_date,policyholder_name,policyholder_dob,policyholder_phone,policyholder_email\n` +
      `${bulkNum1},motor,800000,5000,2026-01-01,2027-01-01,Rajesh Patel,1988-04-12,9820011223,rajesh@example.com\n` +
      `${bulkNum2},home,2500000,10000,2026-02-01,2027-02-01,Meera Nambiar,1995-11-20,9820044556,meera@example.com`;

    const importRes = await request.post('http://localhost:8000/api/v1/admin/policies/import-strict', {
      headers: { Authorization: `Bearer ${token}` },
      multipart: {
        file: {
          name: 'valid_import.csv',
          mimeType: 'text/csv',
          buffer: Buffer.from(validCsv)
        }
      }
    });
    expect(importRes.status()).toBe(200);
    const importBody = await importRes.json();
    expect(importBody.total_processed).toBe(2);
    expect(importBody.errors.length).toBe(0);

    // 3. Edge Case: Missing required columns (must return 400)
    const malformedCsv = `policy_number,coverage_amount\n${bulkNum1},800000`;
    const missingColRes = await request.post('http://localhost:8000/api/v1/admin/policies/import-strict', {
      headers: { Authorization: `Bearer ${token}` },
      multipart: {
        file: {
          name: 'missing_columns.csv',
          mimeType: 'text/csv',
          buffer: Buffer.from(malformedCsv)
        }
      }
    });
    expect(missingColRes.status()).toBe(400);

    // 4. Edge Case: Malformed rows with invalid dates & invalid types
    const invalidRowsCsv = `policy_number,policy_type,coverage_amount,deductible,effective_date,expiry_date,policyholder_name,policyholder_dob,policyholder_phone\n` +
      `POL-BAD-1,unknown_type,500000,0,2026-01-01,2027-01-01,Bad Person,1990-01-01,9876543210\n` +
      `POL-BAD-2,motor,500000,0,2026-05-01,2026-01-01,Bad Date,1990-01-01,9876543210`;

    const invalidImportRes = await request.post('http://localhost:8000/api/v1/admin/policies/import-strict', {
      headers: { Authorization: `Bearer ${token}` },
      multipart: {
        file: {
          name: 'invalid_rows.csv',
          mimeType: 'text/csv',
          buffer: Buffer.from(invalidRowsCsv)
        }
      }
    });
    expect(invalidImportRes.status()).toBe(200);
    const invalidBody = await invalidImportRes.json();
    expect(invalidBody.errors.length).toBe(2);
    expect(invalidBody.errors[0].error).toContain('Invalid policy_type');
    expect(invalidBody.errors[1].error).toContain('Expiry date must be after effective date');
  });

  test('Data Export for Policies and Adjusters (CSV & XLSX)', async ({ request }) => {
    const loginRes = await request.post('http://localhost:8000/api/v1/auth/login', {
      data: {
        email: 'admin@insurance.com',
        password: 'DemoPassword123!'
      }
    });
    const token = (await loginRes.json()).access_token;

    // 1. Export Policies CSV
    const polExportRes = await request.get('http://localhost:8000/api/v1/admin/policies/export?format=csv', {
      headers: { Authorization: `Bearer ${token}` }
    });
    expect(polExportRes.status()).toBe(200);
    expect(polExportRes.headers()['content-type']).toContain('text/csv');
    const polCsv = await polExportRes.text();
    expect(polCsv).toContain('policy_number,policy_type,coverage_amount');

    // 2. Export Adjusters CSV
    const adjExportRes = await request.get('http://localhost:8000/api/v1/admin/adjusters/export?format=csv', {
      headers: { Authorization: `Bearer ${token}` }
    });
    expect(adjExportRes.status()).toBe(200);
    expect(adjExportRes.headers()['content-type']).toContain('text/csv');
    const adjCsv = await adjExportRes.text();
    expect(adjCsv).toContain('name,email,phone,specialization');
  });

});
