// Story: a new/transfer student browses what's happening on campus and filters by interest.
import { test, expect } from '@playwright/test';
import { card, openFeed } from './helpers.js';

test.describe('Student discovers events', () => {
  test('feed is grouped by day, soonest first', async ({ page }) => {
    await openFeed(page);
    await expect(page.getByRole('heading', { name: 'Today', level: 2 })).toBeVisible();
    await expect(page.locator('article.card').first()).toContainText('Late Night Study Jam');
  });

  test('filter by tag shows only matching events', async ({ page }) => {
    await openFeed(page);
    await page.getByRole('search').getByRole('button', { name: '#music' }).click();
    const cards = page.locator('article.card');
    await expect(cards.first()).toBeVisible();
    for (const tags of await cards.locator('ul.chips').allInnerTexts()) {
      expect(tags).toContain('#music');
    }
  });

  test('text search narrows the feed', async ({ page }) => {
    await openFeed(page);
    await page.getByPlaceholder('Search events').fill('rust');
    await expect(page.locator('article.card')).toHaveCount(1);
    await expect(card(page, 'Intro to Rust Workshop')).toBeVisible();
  });

  test('opening an event shows its details', async ({ page }) => {
    await openFeed(page);
    await page.getByRole('button', { name: 'Engineering Career Fair' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: 'Engineering Career Fair' })).toBeVisible();
    await expect(dialog.getByText('Updates')).toBeVisible();
  });

  test('layout fits the screen without horizontal scrolling', async ({ page }) => {
    await openFeed(page);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
