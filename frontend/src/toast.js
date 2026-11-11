/**
 * Accessible toast messages rendered into an aria-live region.
 * @module toast
 */
import { h } from './dom.js';

/**
 * @param {HTMLElement} region element with aria-live="polite"
 * @param {{timeoutMs?: number}} [opts]
 * @returns {(message: string, opts?: {kind?: 'info'|'error'}) => void}
 */
export function createToaster(region, { timeoutMs = 5000 } = {}) {
  return (message, { kind = 'info' } = {}) => {
    const el = h('div', { class: `toast toast--${kind}` }, message);
    region.append(el);
    setTimeout(() => el.remove(), timeoutMs);
  };
}
