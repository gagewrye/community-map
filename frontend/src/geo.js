/**
 * Opt-in geolocation. The position lives only in memory and is never sent anywhere.
 * @module geo
 */

/**
 * @param {{geolocation?: Geolocation|null, timeoutMs?: number}} [opts]
 */
export function createGeo({ geolocation = globalThis.navigator?.geolocation ?? null, timeoutMs = 10000 } = {}) {
  /** @type {{lat: number, lng: number}|null} */
  let position = null;

  return {
    /** @returns {boolean} whether the browser supports geolocation */
    get supported() {
      return Boolean(geolocation);
    },
    /** @returns {{lat: number, lng: number}|null} last known position (memory only) */
    get position() {
      return position;
    },
    /**
     * Ask the browser for the current position. Call only from a user gesture.
     * @returns {Promise<{lat: number, lng: number}>}
     */
    request() {
      if (!geolocation) return Promise.reject(new Error('Location is not available on this device'));
      return new Promise((resolve, reject) => {
        geolocation.getCurrentPosition(
          (p) => {
            position = { lat: p.coords.latitude, lng: p.coords.longitude };
            resolve(position);
          },
          (err) => reject(new Error(err?.message || 'Could not get your location')),
          { enableHighAccuracy: false, maximumAge: 60000, timeout: timeoutMs },
        );
      });
    },
    /** Forget the position. */
    clear() {
      position = null;
    },
  };
}
