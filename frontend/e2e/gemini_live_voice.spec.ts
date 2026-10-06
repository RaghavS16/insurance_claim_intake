import { test, expect } from "@playwright/test";
import path from "path";

const DEMO_PASSWORD = "DemoPassword123!";

test.describe("In-Chat Voice Transcription & Speaker Interaction", () => {
  test("Claimant clicks mic, transcribes speech to right side, receives reply on left side, gets audio from speaker with pause/resume", async ({ page }) => {
    // 1. Login as claimant
    await page.goto("/login");
    await page.locator('input[type="email"]').fill("riya.claimant@insurance.com");
    await page.locator('input[type="password"]').fill(DEMO_PASSWORD);
    await page.locator('button[type="submit"]').click();

    // Wait for claimant workspace to mount
    await expect(page.locator(".chat-brand")).toContainText("Claims Intake", { timeout: 15000 });

    // Open existing claim or start new chat
    const firstConv = page.locator(".chat-history-item").first();
    if (await firstConv.isVisible({ timeout: 2000 })) {
      await firstConv.click();
    }

    // Instrument speech synthesis to track speaker audio output
    await page.evaluate(() => {
      (window as any).__speechHistory = [];
      if (typeof window !== "undefined" && window.speechSynthesis) {
        const origSpeak = window.speechSynthesis.speak.bind(window.speechSynthesis);
        window.speechSynthesis.speak = (utterance: SpeechSynthesisUtterance) => {
          (window as any).__speechHistory.push(utterance.text);
          try {
            origSpeak(utterance);
          } catch {}
        };
      }
    });

    // 2. Click the mic button in composer
    const voiceBtn = page.locator(".voice-primary");
    await expect(voiceBtn).toBeVisible({ timeout: 5000 });
    await voiceBtn.click();

    // 3. Verify in-chat Gemini Live bar appears directly in the chat view
    const liveBar = page.locator(".gemini-live-bar");
    await expect(liveBar).toBeVisible({ timeout: 5000 });

    // Verify visualizer elements: mini orb, soundwaves, and timer
    const orb = page.locator(".gemini-live-orb-mini");
    await expect(orb).toBeVisible();

    const waves = page.locator(".gemini-wave-bar");
    await expect(waves).toHaveCount(5);

    const timer = page.locator(".gemini-live-timer");
    await expect(timer).toBeVisible();

    // Verify initial Pause button exists
    const pauseBtn = page.locator(".gemini-live-btn-pause");
    await expect(pauseBtn).toBeVisible();
    await expect(pauseBtn).toContainText("Pause");

    // Take screenshot of in-chat active voice bar
    const screenshotDir = path.resolve(__dirname, "../../artifacts/screenshots");
    await page.screenshot({ path: path.join(screenshotDir, "in_chat_voice_listening.png") });

    // 4. Test Pause interaction
    await pauseBtn.click();

    // Verify paused status and Resume button
    const statusText = page.locator(".gemini-live-bar-status");
    await expect(statusText).toHaveText("Live Paused");

    const resumeBtn = page.locator(".gemini-live-btn-resume");
    await expect(resumeBtn).toBeVisible();
    await expect(resumeBtn).toContainText("Resume");

    // Take screenshot of in-chat paused state
    await page.screenshot({ path: path.join(screenshotDir, "in_chat_voice_paused.png") });

    // 5. Test Resume interaction
    await resumeBtn.click();
    await expect(page.locator(".gemini-live-btn-pause")).toBeVisible();
    await expect(statusText).not.toHaveText("Live Paused");

    // 6. Test voice turn transcription:
    // When claimant speaks into mic, speech is transcribed and sent to the chat
    await page.evaluate(async () => {
      if ((window as any).__sendVoiceTurn) {
        await (window as any).__sendVoiceTurn("I had a minor bumper collision in the parking lot today.");
      }
    });

    // Verify user transcribed message appears on the RIGHT side of the chat thread
    const userBubble = page.locator(".chat-bubble-user").last();
    await expect(userBubble).toBeVisible({ timeout: 10000 });
    await expect(userBubble).toContainText("parking lot");

    // Verify AI reply appears on the LEFT side of the chat thread
    const aiResponse = page.locator(".chat-response-ai").last();
    await expect(aiResponse).toBeVisible({ timeout: 15000 });

    // Verify that the assistant reply was passed to the SPEAKER via window.speechSynthesis
    await page.waitForFunction(() => {
      const history = (window as any).__speechHistory || [];
      return history.length > 0;
    }, { timeout: 10000 });

    const spokenText = await page.evaluate(() => ((window as any).__speechHistory || []).pop() || "");
    expect(spokenText.length).toBeGreaterThan(5);

    // Verify Speaker utility button on the assistant response card
    const speakBtn = page.locator(".chat-response-ai").last().locator(".chat-util-btn").filter({ hasText: /Speak/i });
    await expect(speakBtn).toBeVisible();

    // Take screenshot of the complete chat with right-side user bubble, left-side reply, and live speaker bar
    await page.screenshot({ path: path.join(screenshotDir, "in_chat_voice_transcribed_turn.png") });

    // 7. Test stopping voice intake
    const stopBtn = page.locator(".gemini-live-btn-stop");
    await stopBtn.click();
    await expect(liveBar).not.toBeVisible();
  });
});
