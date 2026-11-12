import { defineConfig, devices } from '@playwright/test';

const PORT = 8100;

export default defineConfig({
  testDir: './tests',
  fullyParallel: false, // stories share one seeded backend
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${PORT}`,
    serviceWorkers: 'block', // the offline story opts back in
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] }, testMatch: /discover|mobile/ },
  ],
  webServer: {
    command: './serve.sh',
    url: `http://localhost:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    env: { PORT: String(PORT) },
  },
});
