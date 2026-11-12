// Story: a student on bad campus WiFi can still see events they loaded earlier.
import { test, expect } from '@playwright/test';
import { openFeed } from './helpers.js';

test.use({ serviceWorkers: 'allow' });

test('feed still loads from cache when the network drops', async ({ page, context }) => {
  await openFeed(page);
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload(); // let the service worker control the page and cache /api responses
  await page.locator('article.card').first().waitFor();

  await context.setOffline(true);
  await page.reload();
  await expect(page.locator('article.card', { hasText: 'Late Night Study Jam' })).toBeVisible();
  await expect(page.locator('.notice--stale')).toBeVisible();
});
