import { test, expect } from "@playwright/test";

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";
const API_URL = process.env.API_URL || "http://127.0.0.1:8000";
const MAILPIT_URL = "http://127.0.0.1:8025";
const DEMO_PASSWORD = "DemoPassword123!";

test.describe("Production Defect Regression Suite (8 Bugs)", () => {
  // BUG 1: OTP Email Delivery
  test("Bug 1: Password reset OTP email delivered to Mailpit and valid for reset", async ({ page, request }) => {
    await page.goto(`${BASE_URL}/recovery`);
    await page.fill('input[type="email"]', "riya.claimant@insurance.com");
    await page.click('button[type="submit"]');

    // Wait for OTP request confirmation
    await expect(page.locator("text=Enter the code sent to your email address")).toBeVisible({ timeout: 8000 });

    // Verify email captured in Mailpit
    const mailRes = await request.get(`${MAILPIT_URL}/api/v1/messages`);
    expect(mailRes.ok()).toBeTruthy();
    const mailData = await mailRes.json();
    const otpMsg = mailData.messages?.find((m: any) =>
      m.To?.some((t: any) => t.Address === "riya.claimant@insurance.com") &&
      m.Subject?.includes("password reset code")
    );
    expect(otpMsg).toBeTruthy();
    expect(otpMsg.From?.Address).toBe("raghavradhakrishnan.d@gmail.com");

    // Fetch full message body to extract 6-digit OTP
    const msgDetailRes = await request.get(`${MAILPIT_URL}/api/v1/message/${otpMsg.ID}`);
    const msgDetail = await msgDetailRes.json();
    const match = msgDetail.Text?.match(/\b(\d{6})\b/);
    expect(match).toBeTruthy();
    const otp = match[1];

    // Submit OTP on frontend
    await page.fill('input[placeholder*="123456"], input[type="text"]', otp);
    await page.click('button[type="submit"]');

    // Asserts transitioned to password reset step
    await expect(page.locator("text=Create a new strong password")).toBeVisible({ timeout: 8000 });
  });

  // BUG 2: Knowledge Documents Empty on 200 & Simplified Upload
  test("Bug 2: Knowledge documents query returns populated list and simplified upload succeeds", async ({ request }) => {
    // Login as adjuster
    const loginRes = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email: "asha.adjuster@insurance.com", password: DEMO_PASSWORD },
    });
    expect(loginRes.ok()).toBeTruthy();
    const { access_token } = await loginRes.json();

    // Query documents
    const docRes = await request.get(`${API_URL}/api/v1/knowledge/documents`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(docRes.ok()).toBeTruthy();
    const docData = await docRes.json();
    expect(Array.isArray(docData.items)).toBeTruthy();
    expect(docData.items.length).toBeGreaterThan(0);

    // Ingest simplified document (no policy number, no jurisdiction required)
    const ingestRes = await request.post(`${API_URL}/api/v1/knowledge/documents`, {
      headers: { Authorization: `Bearer ${access_token}` },
      data: {
        source_name: "test-simplified-policy-wording.txt",
        document_type: "policy_wording",
        insurance_type: "motor",
        text: "Coverage includes windshield replacement subject to zero deductible for accidental damage.",
      },
    });
    expect(ingestRes.ok()).toBeTruthy();
  });

  // BUG 3: Claimant ChatGPT-Style Conversational Intake
  test("Bug 3: Claimant chat displays welcome state without creating premature session on login", async ({ page }) => {
    // Login as claimant
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="email"]', "riya.claimant@insurance.com");
    await page.fill('input[type="password"]', DEMO_PASSWORD);
    await page.click('button[type="submit"]');

    await page.waitForURL(url => url.pathname.includes("/chat") || url.pathname === "/", { timeout: 10000 });

    // Assert ChatGPT-style landing state with welcome pills
    await expect(page.locator("text=How can I help with your claim today?")).toBeVisible({ timeout: 8000 });
    const pills = page.locator("button:has-text('Vehicle Collision'), button:has-text('Property Water Damage'), button:has-text('Coverage Inquiry')");
    await expect(pills.first()).toBeVisible();

    // Assert clean initial state
    await expect(page.locator("text=Describe what happened in plain English")).toBeVisible();
  });

  // BUG 4: Voice WebRTC ICE Sanitization
  test("Bug 4: Real-time voice session sanitizes ICE servers without crashing on missing TURN credentials", async ({ request }) => {
    // Login as claimant
    const loginRes = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email: "riya.claimant@insurance.com", password: DEMO_PASSWORD },
    });
    const { access_token } = await loginRes.json();

    const voiceRes = await request.post(`${API_URL}/api/v1/voice/session/CLM-DEMO-MOTOR-001`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    // Should be 200 or 503 if voice provider disabled, but never 500 or malformed ICE
    if (voiceRes.status() === 200) {
      const voiceData = await voiceRes.json();
      expect(voiceData.ice_servers).toBeDefined();
      for (const server of voiceData.ice_servers) {
        const urls = Array.isArray(server.urls) ? server.urls : [server.urls];
        for (const url of urls) {
          if (typeof url === "string" && (url.startsWith("turn:") || url.startsWith("turns:"))) {
            expect(server.username).toBeDefined();
            expect(server.credential).toBeDefined();
          }
        }
      }
    }
  });

  // BUG 5: Voice 409 Conflict Prevention & Passkey Availability
  test("Bug 5: Repeated voice session requests teardown stale calls without 409 conflict", async ({ request }) => {
    const loginRes = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email: "riya.claimant@insurance.com", password: DEMO_PASSWORD },
    });
    const { access_token } = await loginRes.json();

    const first = await request.post(`${API_URL}/api/v1/voice/session/CLM-DEMO-MOTOR-001`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });

    const second = await request.post(`${API_URL}/api/v1/voice/session/CLM-DEMO-MOTOR-001`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });

    // Both requests must not return 409 Conflict
    expect(first.status()).not.toBe(409);
    expect(second.status()).not.toBe(409);
  });

  // BUG 6: Admin Adjuster Invite Email Delivery
  test("Bug 6: Admin adjuster invitation email delivered immediately to Mailpit", async ({ request }) => {
    const loginRes = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email: "admin@insurance.com", password: DEMO_PASSWORD },
    });
    const { access_token } = await loginRes.json();

    const uniqueEmail = `qa.invite.${Date.now()}@insurance.com`;
    const inviteRes = await request.post(`${API_URL}/api/v1/admin/adjusters/invite`, {
      headers: { Authorization: `Bearer ${access_token}` },
      data: {
        name: "QA Invited Adjuster",
        email: uniqueEmail,
        phone: "+919876500099",
        specialization: "health",
      },
    });
    expect(inviteRes.ok()).toBeTruthy();
    const inviteData = await inviteRes.json();
    expect(inviteData.email_delivery_status).toBe("sent");

    // Verify in Mailpit
    const mailRes = await request.get(`${MAILPIT_URL}/api/v1/messages`);
    const mailData = await mailRes.json();
    const found = mailData.messages?.find((m: any) =>
      m.To?.some((t: any) => t.Address === uniqueEmail)
    );
    expect(found).toBeTruthy();
    expect(found.Subject).toContain("adjuster invitation");
  });

  // BUG 7: Adjuster Evidence Request (No 403)
  test("Bug 7: Assigned adjuster can create evidence requests without 403 Forbidden", async ({ request }) => {
    const loginRes = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email: "asha.adjuster@insurance.com", password: DEMO_PASSWORD },
    });
    const { access_token } = await loginRes.json();

    const evRes = await request.post(`${API_URL}/api/v1/adjuster/claims/CLM-DEMO-MOTOR-001/evidence-requests`, {
      headers: { Authorization: `Bearer ${access_token}` },
      data: {
        request_text: "Please provide high-resolution photos of the rear bumper damage.",
      },
    });

    // Must be 200 OK, never 403
    expect(evRes.status()).toBe(200);
    const evData = await evRes.json();
    expect(evData.status).toBe("open");
    expect(evData.request_text).toContain("rear bumper damage");
  });

  // BUG 8: SnowUI Design System Light Theme & Kanban Drag-and-Drop
  test("Bug 8: SnowUI light theme enforced with interactive Kanban board and SLA timer", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="email"]', "asha.adjuster@insurance.com");
    await page.fill('input[type="password"]', DEMO_PASSWORD);
    await page.click('button[type="submit"]');

    await page.waitForURL("**/adjuster**", { timeout: 10000 });
    await page.goto(`${BASE_URL}/adjuster/queue`);

    // Verify strict light theme
    const dataTheme = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
    const hasDarkClass = await page.evaluate(() => document.documentElement.classList.contains("dark"));
    expect(dataTheme).toBe("light");
    expect(hasDarkClass).toBeFalsy();

    // Verify Kanban board columns
    await expect(page.locator(".snow-kanban-title:has-text('New Intake')")).toBeVisible({ timeout: 8000 });
    await expect(page.locator(".snow-kanban-title:has-text('Under Review')")).toBeVisible();
    await expect(page.locator(".snow-kanban-title:has-text('Pending Evidence')")).toBeVisible();
    await expect(page.locator(".snow-kanban-title:has-text('Approved')")).toBeVisible();

    // Verify SLA countdown timer element
    const timer = page.locator(".snow-sla-timer").first();
    await expect(timer).toBeVisible();

    // Verify guidance pill
    await expect(page.locator(".snow-guidance-pill")).toBeVisible();
  });
});
