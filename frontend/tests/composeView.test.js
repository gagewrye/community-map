import { describe, expect, it, vi } from 'vitest';
import { buildEventRecord, parseTags, validateEventRecord } from '../src/records.js';
import { buildForm, createComposeView, isoToLocalInput, localInputToIso, readForm, showErrors, validateForm } from '../src/views/composeView.js';
import { sampleEvent } from './helpers.js';

const valid = {
  name: 'Study jam', description: '', startsAt: '2026-11-12T18:00', endsAt: '2026-11-12T20:00',
  locationName: 'Geisel', address: '', lat: '', lng: '', tags: '#Study, quiet, study', group: '', hashtag: '',
};

describe('records', () => {
  it('normalizes tags like the backend', () => {
    expect(parseTags(' #Food, music ,food,, ')).toEqual(['food', 'music']);
  });

  it('builds a lexicon-shaped record: strings for lat/lng, omits empties, ISO createdAt', () => {
    const r = buildEventRecord({ name: ' X ', startsAt: 's', endsAt: 'e', locationName: 'L', lat: 32.5, lng: '-117', tags: '', group: '' });
    expect(r).toEqual({ $type: 'app.communitymap.event', name: 'X', startsAt: 's', endsAt: 'e', location: { name: 'L', lat: '32.5', lng: '-117' }, createdAt: r.createdAt });
    expect(new Date(r.createdAt).toISOString()).toBe(r.createdAt);
  });
});

describe('compose validation', () => {
  it('accepts a valid form and converts datetime-local to ISO', () => {
    const { record, errors } = validateForm(valid);
    expect(errors).toEqual({});
    expect(record.startsAt).toBe(new Date('2026-11-12T18:00').toISOString());
    expect(record.tags).toEqual(['study', 'quiet']);
  });

  it('requires name, times and location name', () => {
    const { errors } = validateForm({ ...valid, name: ' ', startsAt: '', endsAt: '', locationName: '' });
    expect(Object.keys(errors).sort()).toEqual(['endsAt', 'locationName', 'name', 'startsAt']);
  });

  it('rejects endsAt before startsAt (equal is allowed)', () => {
    expect(validateForm({ ...valid, endsAt: '2026-11-12T17:59' }).errors.endsAt).toMatch(/after start/);
    expect(validateForm({ ...valid, endsAt: valid.startsAt }).errors).toEqual({});
  });

  it('enforces lexicon lengths and the 10-tag limit', () => {
    const tags = Array.from({ length: 11 }, (_, i) => `t${i}`).join(',');
    const { errors } = validateForm({ ...valid, name: 'x'.repeat(201), description: 'd'.repeat(3001), tags, group: 'g'.repeat(101), address: 'a'.repeat(301) });
    expect(Object.keys(errors).sort()).toEqual(['address', 'description', 'group', 'name', 'tags']);
    expect(validateForm({ ...valid, tags: 'x'.repeat(33) }).errors.tags).toMatch(/32/);
    // byte length, not code units: 67 x 3-byte chars > 200 bytes
    expect(validateEventRecord(buildEventRecord({ ...valid, name: '€'.repeat(67), startsAt: 'x', endsAt: 'x' })).name).toBeDefined();
  });

  it('validates coordinates (both or neither, in range)', () => {
    expect(validateForm({ ...valid, lat: '32.88' }).errors.lat).toMatch(/both/);
    expect(validateForm({ ...valid, lat: '91', lng: '0' }).errors.lat).toMatch(/Latitude/);
    expect(validateForm({ ...valid, lat: 'abc', lng: '0' }).errors.lat).toBeDefined();
    expect(validateForm({ ...valid, lat: '32.88', lng: '-117.23' }).errors).toEqual({});
  });

  it('validates the hashtag', () => {
    expect(validateForm({ ...valid, hashtag: 'two words' }).errors.hashtag).toBeDefined();
    expect(validateForm({ ...valid, hashtag: '#ok' }).errors).toEqual({});
  });

  it('round-trips ISO <-> datetime-local', () => {
    const iso = new Date(2026, 10, 12, 18, 30).toISOString();
    expect(localInputToIso(isoToLocalInput(iso))).toBe(iso);
    expect(localInputToIso('')).toBe('');
  });

  it('marks invalid fields accessibly and focuses the first', () => {
    const form = buildForm(null);
    document.body.replaceChildren(form);
    const { errors } = validateForm(readForm(form));
    showErrors(form, errors);
    expect(form.elements.name.getAttribute('aria-invalid')).toBe('true');
    expect(form.elements.name.getAttribute('aria-describedby')).toBe('c-name-err');
    expect(form.querySelector('#c-name-err').textContent).toMatch(/required/);
    expect(document.activeElement).toBe(form.elements.name);
  });

  it('prefills when editing', () => {
    const form = buildForm(sampleEvent());
    expect(readForm(form)).toMatchObject({ name: 'Taco Tuesday', locationName: 'Price Center', lat: '32.8797', tags: 'food, free', group: 'Triton Eats' });
  });
});

describe('compose submit', () => {
  const fill = (form, values) => Object.entries(values).forEach(([k, v]) => { form.elements[k].value = v; });
  const flush = () => new Promise((r) => setTimeout(r, 0));

  it('creates the event, then a listener for the hashtag', async () => {
    const writer = { createEvent: vi.fn(async () => ({ uri: 'at://d/app.communitymap.event/r1' })), createListener: vi.fn(async () => ({})) };
    const onSaved = vi.fn();
    const view = createComposeView({ getWriter: () => writer, onSaved });
    view.open();
    const form = view.element.querySelector('form');
    fill(form, { ...valid, hashtag: '#StudyJam' });
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    expect(writer.createEvent.mock.calls[0][0]).toMatchObject({ name: 'Study jam', location: { name: 'Geisel' } });
    expect(writer.createListener).toHaveBeenCalledWith('at://d/app.communitymap.event/r1', '#StudyJam');
    expect(onSaved).toHaveBeenCalled();
  });

  it('edits with putRecord rkey and preserves createdAt', async () => {
    const writer = { updateEvent: vi.fn(async () => ({ uri: 'u' })), createListener: vi.fn() };
    const view = createComposeView({ getWriter: () => writer });
    const ev = sampleEvent({ createdAt: '2026-11-01T00:00:00.000Z' });
    view.open(ev);
    view.element.querySelector('form').dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    const [rkey, record] = writer.updateEvent.mock.calls[0];
    expect(rkey).toBe('3kabc');
    expect(record.createdAt).toBe('2026-11-01T00:00:00.000Z');
    expect(writer.createListener).not.toHaveBeenCalled();
  });

  it('does not submit invalid forms', async () => {
    const writer = { createEvent: vi.fn() };
    const view = createComposeView({ getWriter: () => writer });
    view.open();
    view.element.querySelector('form').dispatchEvent(new Event('submit', { cancelable: true }));
    await flush();
    expect(writer.createEvent).not.toHaveBeenCalled();
  });

  it('deletes after confirmation', async () => {
    const writer = { deleteEvent: vi.fn(async () => ({})) };
    const onDeleted = vi.fn();
    const view = createComposeView({ getWriter: () => writer, onDeleted, confirmImpl: () => true });
    await view.remove(sampleEvent());
    expect(writer.deleteEvent).toHaveBeenCalledWith('3kabc');
    expect(onDeleted).toHaveBeenCalledWith(sampleEvent().uri);
  });
});
