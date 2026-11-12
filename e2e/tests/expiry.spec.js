// Story: posted events expire gracefully instead of cluttering the feed.
import { test, expect } from '@playwright/test';
import { card, commit, inHours, openFeed } from './helpers.js';

test('an event ending within the hour is flagged "Ending soon"', async ({ page }) => {
  await openFeed(page);
  await expect(card(page, 'Late Night Study Jam').getByText('Ending soon')).toBeVisible();
});

test('an ended event disappears from the feed', async ({ page, request }) => {
  const name = `Flash Sale ${Date.now()}`;
  const record = (endsAt) => ({
    $type: 'app.communitymap.event', name, startsAt: inHours(-2), endsAt,
    location: { name: 'Library Walk' }, createdAt: inHours(-3),
  });
  await commit(request, 'did:plc:shop', 'app.communitymap.event', 'create', 'sale1', record(inHours(1)));
  await openFeed(page);
  await expect(card(page, name)).toBeVisible();

  // The host moves the end time into the past; the sweeper removes it.
  await commit(request, 'did:plc:shop', 'app.communitymap.event', 'update', 'sale1', record(inHours(-0.01)));
  await expect(async () => {
    await page.reload();
    await page.locator('article.card').first().waitFor();
    await expect(card(page, name)).toHaveCount(0);
  }).toPass({ timeout: 10_000 });
});
