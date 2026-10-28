import { chromium } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';

const BASE_URL = 'http://localhost:3000';
const DEMO_PASSWORD = process.env.DEMO_PASSWORD || 'DemoPass123!';
const VIDEO_DIR = path.resolve('recordings');

if (!fs.existsSync(VIDEO_DIR)) {
  fs.mkdirSync(VIDEO_DIR, { recursive: true });
}

async function recordWalkthrough() {
  console.log('[RECORD] Launching Playwright browser in Full HD (1920x1080)...');
  const browser = await chromium.launch({
    headless: true,
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: {
      dir: VIDEO_DIR,
      size: { width: 1920, height: 1080 },
    },
  });

  const page = await context.newPage();

  const pause = (ms) => page.waitForTimeout(ms);
  const nav = async (url) => {
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    await pause(1400);
  };

  const loginAs = async (email, expectedPath) => {
    await context.clearCookies();
    await page.goto(`${BASE_URL}/signin`, { waitUntil: 'domcontentloaded' });
    await pause(800);
    try {
      await page.evaluate(() => {
        localStorage.clear();
        sessionStorage.clear();
      });
    } catch {}
    await page.fill('input[placeholder="Email"]', email);
    await page.fill('input[placeholder="Password"]', DEMO_PASSWORD);
    await pause(600);
    await page.click('button[type="submit"]');
    await page.waitForURL((url) => url.pathname.includes(expectedPath), { timeout: 15000 });
    await pause(1800);
  };

  try {
    // =========================================================================
    // 1. PUBLIC & AUTHENTICATION SUITE
    // =========================================================================
    console.log('[1/5] Public & Authentication Suite...');
    await nav(`${BASE_URL}/`);
    await pause(1500);

    // Smooth scroll down to showcase hero, features, and trust badges
    await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }));
    await pause(1400);
    await page.evaluate(() => window.scrollBy({ top: 600, behavior: 'smooth' }));
    await pause(1400);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
    await pause(1000);

    // Sign In view
    await nav(`${BASE_URL}/signin`);
    await pause(1500);

    // Sign Up view
    await nav(`${BASE_URL}/signup`);
    await pause(1500);

    // Forgot Password view
    await nav(`${BASE_URL}/forgot-password`);
    await pause(1500);

    // =========================================================================
    // 2. ADMIN PERSONA (admin@insurance.com)
    // Order: Admin -> Adjuster -> Claimant
    // =========================================================================
    console.log('[2/5] Persona 1: Admin Operations (admin@insurance.com)...');
    await loginAs('admin@insurance.com', '/admin');

    // Admin Claims Registry
    console.log('  -> Admin Claims Registry & SLA Dashboard');
    await nav(`${BASE_URL}/admin/claims`);
    await pause(2200);
    await page.evaluate(() => window.scrollBy({ top: 350, behavior: 'smooth' }));
    await pause(1400);

    // Admin Adjusters Management
    console.log('  -> Admin Adjusters Capacity Management');
    await nav(`${BASE_URL}/admin/adjusters`);
    await pause(2200);

    // Admin Policy Master Templates & + New Policy Ingestion Modal
    console.log('  -> Admin Policy Master Registry & Templates');
    await nav(`${BASE_URL}/admin/policies`);
    await pause(2000);

    console.log('  -> Opening + New Policy Ingestion Modal');
    const newPolicyBtn = page.locator('button:has-text("New Policy"), button:has-text("+ New Policy")').first();
    if (await newPolicyBtn.isVisible()) {
      await newPolicyBtn.click();
      await pause(3500); // Highlight modal form fields & document uploader
      const cancelBtn = page.locator('button:has-text("Cancel")').first();
      if (await cancelBtn.isVisible()) {
        await cancelBtn.click();
        await pause(1000);
      }
    }

    // =========================================================================
    // 3. ADJUSTER PERSONA (asha.adjuster@insurance.com)
    // Order: Admin -> Adjuster -> Claimant
    // =========================================================================
    console.log('[3/5] Persona 2: Adjuster Workflow (asha.adjuster@insurance.com)...');
    await loginAs('asha.adjuster@insurance.com', '/adjuster');

    // Adjuster Dashboard
    console.log('  -> Adjuster Dashboard & Metrics');
    await nav(`${BASE_URL}/adjuster/dashboard`);
    await pause(2200);

    // Adjuster Claim Workspace for CLM-DEMO-MOTOR-001
    console.log('  -> Adjuster Claim Case Workspace');
    await nav(`${BASE_URL}/adjuster/claims/CLM-DEMO-MOTOR-001`);
    await pause(3000);

    // Switch to Evidence Tab
    console.log('  -> Claim Evidence & Documents Tab');
    try {
      const evidenceTab = page.locator('button:has-text("Evidence"), [role="tab"]:has-text("Evidence")').first();
      if (await evidenceTab.isVisible()) {
        await evidenceTab.click({ force: true });
        await pause(2200);
      }
    } catch {}

    // Switch to Exceptions & Notes Tab
    console.log('  -> Claim Exceptions & Adjudication Notes Tab');
    try {
      const notesTab = page.locator('button:has-text("Notes"), button:has-text("Exceptions"), [role="tab"]:has-text("Notes")').first();
      if (await notesTab.isVisible()) {
        await notesTab.click({ force: true });
        await pause(2200);
      }
    } catch {}

    // Adjuster Policy Directory (Clean, Zero Errors)
    console.log('  -> Adjuster Policy Directory (Clean Table, No Error Banner)');
    await nav(`${BASE_URL}/adjuster/policies`);
    await pause(2500);

    // Adjuster Knowledge Base RAG (Clean, Zero Errors)
    console.log('  -> Adjuster Knowledge Base RAG (Clean Table, No Error Banner)');
    await nav(`${BASE_URL}/adjuster/knowledge`);
    await pause(2500);

    // =========================================================================
    // 4. CLAIMANT PERSONA (riya.claimant@insurance.com)
    // Order: Admin -> Adjuster -> Claimant
    // =========================================================================
    console.log('[4/5] Persona 3: Claimant Experience (riya.claimant@insurance.com)...');
    await loginAs('riya.claimant@insurance.com', '/claimant');

    // Claimant Dashboard
    console.log('  -> Claimant Self-Service Dashboard');
    await nav(`${BASE_URL}/claimant/dashboard`);
    await pause(2200);

    // Claimant Policies & Linking Modal
    console.log('  -> Claimant Policies & Link Policy Modal');
    await nav(`${BASE_URL}/claimant/policies`);
    await pause(1800);
    const linkPolicyBtn = page.locator('button:has-text("Link"), button:has-text("Add Policy")').first();
    if (await linkPolicyBtn.isVisible()) {
      await linkPolicyBtn.click();
      await pause(2500);
      const closeBtn = page.locator('button:has-text("Cancel"), button[aria-label="Close"]').first();
      if (await closeBtn.isVisible()) {
        await closeBtn.click();
        await pause(1000);
      }
    }

    // Conversational Intake Chat & Live Dossier
    console.log('  -> Conversational Intake Chat & Real-Time Dossier');
    await nav(`${BASE_URL}/claimant/file-claim?fresh=true`);
    await pause(2000);
    const chatInput = page.locator('input[placeholder*="Type"], textarea[placeholder*="Type"], input[type="text"]').last();
    if (await chatInput.isVisible()) {
      await chatInput.fill('Hello, my car front bumper got damaged in a parking collision yesterday in Bangalore.');
      await pause(800);
      const sendBtn = page.locator('button:has-text("Send"), button[aria-label*="Send"], button[type="submit"]').last();
      if (await sendBtn.isVisible()) {
        await sendBtn.click();
        await pause(4500); // Live AI streaming response + dossier card update
      }
    }

    // Claimant Claim Tracking Timeline
    console.log('  -> Claimant Claim Tracking & Status');
    await nav(`${BASE_URL}/claimant/claims/CLM-DEMO-MOTOR-001`);
    await pause(3000);

    // =========================================================================
    // 5. SIGN OUT FINALE
    // As requested: "and i need endswith signout"
    // =========================================================================
    console.log('[5/5] Finale: Signing Out to Return to Sign In Page...');
    const signOutBtn = page.locator('button:has-text("Sign Out")').first();
    if (await signOutBtn.isVisible()) {
      await signOutBtn.click();
      console.log('  -> Clicked Sign Out button');
      await page.waitForURL((url) => url.pathname.includes('/signin'), { timeout: 10000 });
      await pause(3000); // Graceful pause on the clean Sign In screen to end video
      console.log('  -> Successfully returned to Sign In page!');
    } else {
      console.log('  -> Sign Out button not directly visible, navigating to signout');
      await nav(`${BASE_URL}/signin`);
      await pause(2500);
    }

    console.log('[SUCCESS] All end-to-end walkthrough steps completed seamlessly!');
  } catch (err) {
    console.error('[ERROR] Error during walkthrough:', err);
  } finally {
    const videoObj = page.video();
    await page.close();
    await context.close();
    await browser.close();

    if (videoObj) {
      const videoPath = await videoObj.path();
      console.log(`[VIDEO_RECORDED] ${videoPath}`);
      fs.writeFileSync(path.resolve('recordings', 'latest_video.txt'), videoPath, 'utf8');
    }
  }
}

recordWalkthrough();
