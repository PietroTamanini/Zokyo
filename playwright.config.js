const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:8000',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'compact', use: { viewport: { width: 320, height: 568 }, isMobile: true, hasTouch: true } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
    { name: 'tablet', use: { viewport: { width: 768, height: 1024 }, hasTouch: true } },
    { name: 'desktop', use: { viewport: { width: 1366, height: 768 } } },
    { name: 'wide', use: { viewport: { width: 1920, height: 1080 } } },
  ],
  reporter: [['list'], ['html', { open: 'never' }]],
});
