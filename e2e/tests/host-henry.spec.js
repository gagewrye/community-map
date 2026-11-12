// Story (Host Henry): he announces on Bluesky and the event listing stays in sync automatically.
import { test, expect } from '@playwright/test';
import { card, commit, createEvent, demoDid, openFeed } from './helpers.js';

test("Henry's Bluesky post with the event hashtag appears as an update", async ({ page, browser, request }) => {
  const name = `Henry's Hack Night ${Date.now()}`;
  const hashtag = `hack${Date.now()}`;

  await openFeed(page);
  await createEvent(page, { name, location: 'CSE Building', tags: 'tech', hashtag });
  const did = await demoDid(page);
  expect(did).toMatch(/^did:plc:demo-/);

  // A student subscribes to Henry's event.
  const student = await (await browser.newContext()).newPage();
  await openFeed(student);
  await student.getByPlaceholder('Search events').fill(name);
  await card(student, name).getByRole('button', { name: 'Subscribe' }).click();
  await expect(card(student, name).getByRole('button', { name: 'Subscribed' })).toBeVisible();

  // Henry posts on Bluesky (delivered via the firehose; simulated here).
  const text = `Pizza just arrived, come by room 1202! #${hashtag}`;
  await commit(request, did, 'app.bsky.feed.post', 'create', `post${Date.now()}`, {
    $type: 'app.bsky.feed.post', text, createdAt: new Date().toISOString(),
  });

  await expect(student.locator('#toasts')).toContainText('Pizza just arrived', { timeout: 10_000 });

  await student.getByRole('button', { name }).click();
  await expect(student.getByRole('dialog').getByText(text)).toBeVisible();
});

test("posts from someone else using Henry's hashtag are ignored", async ({ page, request }) => {
  const name = `Henry's Board Games ${Date.now()}`;
  const hashtag = `games${Date.now()}`;
  await openFeed(page);
  await createEvent(page, { name, location: 'Price Center', hashtag });

  await commit(request, 'did:plc:stranger', 'app.bsky.feed.post', 'create', 'p1', {
    text: `Event cancelled lol #${hashtag}`, createdAt: new Date().toISOString(),
  });

  await page.getByRole('button', { name }).click();
  await expect(page.getByRole('dialog').getByText('No announcements yet.')).toBeVisible();
});
