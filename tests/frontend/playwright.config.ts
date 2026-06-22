import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  retries: 1,
  workers: 2,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report' }]],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:8003',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    // AGENTS.md 6b: perfil limpio, sin extensiones, headless
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {},
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // AGENTS.md 6b: Chromium empaquetado por Playwright, NO Chrome del sistema
        // (sin `channel: 'chrome'` → usa el chromium de @playwright/test)
        launchOptions: {
          args: [
            '--disable-extensions',
            '--disable-default-apps',
            '--no-first-run',
          ],
        },
      },
    },
  ],
});
