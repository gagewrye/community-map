/**
 * Tiny DOM helpers. All user content goes through text nodes, never innerHTML.
 * @module dom
 */

const PROPS = new Set(['value', 'checked', 'selected', 'disabled', 'hidden', 'open']);

/**
 * Create an element. Strings/numbers become text nodes (auto-escaped).
 * @param {string} tag
 * @param {Object<string, any>} [props] attributes; `class`, `dataset`, `onX` handlers supported
 * @param {...any} children nodes, strings, arrays, or null/false (skipped)
 * @returns {HTMLElement}
 */
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, val] of Object.entries(props || {})) setProp(el, key, val);
  append(el, children);
  return el;
}

function setProp(el, key, val) {
  if (val == null || val === false) return;
  if (key === 'class') el.className = val;
  else if (key === 'dataset') Object.assign(el.dataset, val);
  else if (key.startsWith('on') && typeof val === 'function') {
    el.addEventListener(key.slice(2).toLowerCase(), val);
  } else if (PROPS.has(key)) el[key] = val;
  else el.setAttribute(key, val === true ? '' : String(val));
}

/**
 * Append children (flattening arrays, skipping null/false).
 * @param {Node} el
 * @param {any[]} children
 */
export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

/**
 * Return `url` only if it is an absolute http(s) URL, else null (blocks javascript: etc).
 * @param {string} url
 * @returns {string|null}
 */
export function safeHttpUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null;
  } catch {
    return null;
  }
}

/**
 * Open a <dialog> modally, with a fallback for environments lacking showModal.
 * @param {HTMLDialogElement} dialog
 */
export function openDialog(dialog) {
  if (!dialog.isConnected) document.body.append(dialog);
  if (typeof dialog.showModal === 'function') {
    if (!dialog.open) dialog.showModal();
  } else dialog.setAttribute('open', '');
}

/**
 * Close a <dialog> (with fallback).
 * @param {HTMLDialogElement} dialog
 */
export function closeDialog(dialog) {
  if (typeof dialog.close === 'function') dialog.close();
  else dialog.removeAttribute('open');
}
