/** Shared helpers for user-story specs. */

/** Card <article> for an event by name. */
export const card = (page, name) => page.locator('article.card', { hasText: name });

/** Wait until the feed has rendered at least one card. */
export async function openFeed(page) {
  await page.goto('/');
  await page.locator('article.card').first().waitFor();
}

/** ISO string `hours` from now. */
export const inHours = (hours) => new Date(Date.now() + hours * 3_600_000).toISOString();

/** datetime-local value (local time, minutes precision) `hours` from now. */
export function localInput(hours) {
  const d = new Date(Date.now() + hours * 3_600_000);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Fill and submit the "New event" dialog in demo mode. */
export async function createEvent(page, { name, location, tags = '', hashtag = '' }) {
  await page.getByRole('button', { name: 'New event' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Event name').fill(name);
  await dialog.getByLabel('Starts').fill(localInput(1));
  await dialog.getByLabel('Ends').fill(localInput(3));
  await dialog.getByLabel('Location name').fill(location);
  if (tags) await dialog.getByLabel('Tags').fill(tags);
  if (hashtag) await dialog.getByLabel(/Bluesky hashtag/).fill(hashtag);
  await dialog.getByRole('button', { name: 'Create event' }).click();
  await card(page, name).waitFor();
}

/** Simulate a Jetstream commit (what the real firehose would deliver). */
export async function commit(request, did, collection, operation, rkey, record) {
  const res = await request.post('/api/dev/records', {
    data: { did, time_us: Date.now() * 1000, kind: 'commit',
      commit: { operation, collection, rkey, cid: `cid-${Date.now()}`, record } },
  });
  if (!res.ok()) throw new Error(`commit failed: ${res.status()}`);
}

/** Read the demo DID the browser is posting as. */
export const demoDid = (page) => page.evaluate(() => localStorage.getItem('cm:demo-did'));
