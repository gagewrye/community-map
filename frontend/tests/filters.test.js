import { describe, expect, it } from 'vitest';
import { toQueryString } from '../src/api.js';
import {
  EMPTY_FILTERS, buildEventQuery, coordsOf, groupByDay, haversineKm, isUpdated, sortByDistance, toggleTag,
} from '../src/filters.js';

describe('buildEventQuery', () => {
  it('drops empty values and never sends nearMe', () => {
    expect(buildEventQuery({ ...EMPTY_FILTERS, nearMe: true })).toEqual({ limit: 20 });
  });

  it('includes tags (repeatable), group, trimmed q and cursor', () => {
    const p = buildEventQuery({ tags: ['food', 'music'], group: 'ACM', q: '  tacos ', nearMe: false }, { cursor: 'c1', limit: 5 });
    expect(p).toEqual({ limit: 5, tag: ['food', 'music'], group: 'ACM', q: 'tacos', cursor: 'c1' });
    expect(toQueryString(p)).toBe('?limit=5&tag=food&tag=music&group=ACM&q=tacos&cursor=c1');
  });

  it('toggleTag adds and removes', () => {
    expect(toggleTag(['a'], 'b')).toEqual(['a', 'b']);
    expect(toggleTag(['a', 'b'], 'a')).toEqual(['b']);
  });
});

describe('distance', () => {
  it('haversine is ~0 for same point and right order of magnitude', () => {
    const geisel = { lat: 32.8811, lng: -117.2376 };
    expect(haversineKm(geisel, geisel)).toBe(0);
    // UCSD -> downtown San Diego is ~ 18 km
    const d = haversineKm(geisel, { lat: 32.7157, lng: -117.1611 });
    expect(d).toBeGreaterThan(17);
    expect(d).toBeLessThan(21);
  });

  it('coordsOf parses strings and rejects junk', () => {
    expect(coordsOf({ location: { lat: '32.1', lng: '-117' } })).toEqual({ lat: 32.1, lng: -117 });
    expect(coordsOf({ location: { lat: 'x', lng: '1' } })).toBeNull();
    expect(coordsOf({ location: { lat: '95', lng: '1' } })).toBeNull();
    expect(coordsOf({ location: { name: 'n' } })).toBeNull();
  });

  it('sorts nearest first; no-coords last, stable, annotated', () => {
    const me = { lat: 32.88, lng: -117.23 };
    const far = { uri: 'far', location: { lat: '32.70', lng: '-117.16' } };
    const near = { uri: 'near', location: { lat: '32.881', lng: '-117.231' } };
    const none1 = { uri: 'none1', location: { name: 'x' } };
    const none2 = { uri: 'none2', location: { name: 'y' } };
    const out = sortByDistance([none1, far, none2, near], me);
    expect(out.map((e) => e.uri)).toEqual(['near', 'far', 'none1', 'none2']);
    expect(out[0].distanceKm).toBeLessThan(1);
    expect(out[2].distanceKm).toBeNull();
  });
});

describe('groupByDay', () => {
  const now = new Date(2026, 10, 11, 12, 0); // Wed Nov 11 2026 local
  const at = (d, h) => ({ startsAt: new Date(2026, 10, d, h).toISOString(), uri: `${d}-${h}` });

  it('labels Today, Tomorrow, weekday, then date; chronological groups', () => {
    const groups = groupByDay([at(20, 9), at(13, 9), at(12, 9), at(11, 18)], { now, locale: 'en-US' });
    expect(groups.map((g) => g.label)).toEqual(['Today', 'Tomorrow', 'Friday', 'Fri, Nov 20']);
  });

  it('puts in-progress events (started earlier) under Today, keeps order within a group', () => {
    const groups = groupByDay([at(11, 15), at(10, 20), at(11, 13)], { now, locale: 'en-US' });
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe('Today');
    expect(groups[0].events.map((e) => e.uri)).toEqual(['11-15', '10-20', '11-13']);
  });
});

describe('isUpdated', () => {
  it('is true only when updatedAt > indexedAt', () => {
    expect(isUpdated({ indexedAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-02T00:00:00Z' })).toBe(true);
    expect(isUpdated({ indexedAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z' })).toBe(false);
    expect(isUpdated({})).toBe(false);
  });
});
