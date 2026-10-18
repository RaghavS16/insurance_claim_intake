import { defineConfig, devices } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const rootDir = path.resolve(__dirname, '..');
const backendDir = path.resolve(rootDir, 'backend');
const pythonCandidates = [
  path.resolve(rootDir, 'venv', 'Scripts', 'python.exe'),
  path.resolve(rootDir, '.venv', 'Scripts', 'python.exe'),
  path.resolve(backendDir, 'venv', 'Scripts', 'python.exe'),
  path.resolve(rootDir, 'venv', 'bin', 'python'),
  path.resolve(rootDir, '.venv', 'bin', 'python'),
  path.resolve(backendDir, 'venv', 'bin', 'python'),
];
const pythonCmd = pythonCandidates.find((p) => fs.existsSync(p)) || 'python';

export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  expect: {
    timeout: 15000,
  },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ['html', { outputFolder: '../qa-report/playwright-report', open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'on',
    video: 'on',
    headless: true,
  },
  webServer: [
    {
      command: `"${pythonCmd}" run_e2e_server.py`,
      cwd: backendDir,
      url: 'http://127.0.0.1:8000/health',
      timeout: 120 * 1000,
      reuseExistingServer: true,
      env: {
        ...process.env,
        DEMO_PASSWORD: process.env.DEMO_PASSWORD || '',
      },
    },
    {
      command: 'npm run dev',
      cwd: __dirname,
      url: 'http://localhost:3000',
      timeout: 120 * 1000,
      reuseExistingServer: true,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
