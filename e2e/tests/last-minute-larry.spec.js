// Story (Last-minute Larry): he moves his party to a new spot; subscribed attendees hear about it fast.
import { test, expect } from '@playwright/test';
import { card, createEvent, openFeed } from './helpers.js';

test('attendee gets a live notice when Larry changes the location', async ({ browser }) => {
  const larry = await (await browser.newContext()).newPage();
  const attendee = await (await browser.newContext()).newPage();
  const name = `Larry's Picnic ${Date.now()}`;

  await openFeed(larry);
  await createEvent(larry, { name, location: 'Mission Bay Park', tags: 'social, food' });

  await openFeed(attendee);
  await attendee.getByPlaceholder('Search events').fill(name);
  await card(attendee, name).getByRole('button', { name: 'Subscribe' }).click();
  await expect(card(attendee, name).getByRole('button', { name: 'Subscribed' })).toBeVisible();

  // Larry edits the event: the tables were taken, moving to Kellogg Park.
  await larry.getByRole('button', { name }).click();
  await larry.getByRole('dialog').getByRole('button', { name: 'Edit' }).click();
  const form = larry.getByRole('dialog').filter({ has: larry.getByLabel('Location name') });
  await form.getByLabel('Location name').fill('Kellogg Park');
  await form.getByRole('button', { name: 'Save changes' }).click();

  await expect(attendee.locator('#toasts')).toContainText('Kellogg Park', { timeout: 10_000 });

  // The feed reflects the change after a refresh, flagged as updated.
  await attendee.reload();
  await attendee.getByPlaceholder('Search events').fill(name);
  await expect(card(attendee, name)).toContainText('Kellogg Park');
  await expect(card(attendee, name).getByText('Updated')).toBeVisible();
});
