/**
 * Event detail <dialog>: full description and the announcement list from GET /api/event.
 * @module views/detailView
 */
import { closeDialog, h, openDialog, safeHttpUrl } from '../dom.js';
import { isUpdated } from '../filters.js';
import { formatDateTime, formatTimeWindow, osmUrl, statusLabel } from '../format.js';

/**
 * Render the dialog body for an event.
 * @param {object} ev EventView & {updates}
 * @param {{canEdit?: boolean, onEdit?: (ev: object) => void, onDelete?: (ev: object) => void,
 *   stale?: boolean, locale?: string, timeZone?: string}} [opts]
 * @returns {HTMLElement[]}
 */
export function renderDetail(ev, opts = {}) {
  const href = osmUrl(ev);
  const source = safeHttpUrl(ev.sourceUrl);
  const status = statusLabel(ev.status);
  const updates = [...(ev.updates || [])].sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
  return [
    h('h2', { id: 'detail-title' }, ev.name),
    h('div', { class: 'card__badges' },
      status && h('span', { class: `badge badge--${ev.status}` }, status),
      isUpdated(ev) && h('span', { class: 'badge badge--updated' }, 'Updated'),
      opts.stale && h('span', { class: 'badge' }, 'Saved copy'),
    ),
    h('p', null, h('time', { datetime: ev.startsAt }, formatTimeWindow(ev.startsAt, ev.endsAt, opts))),
    h('p', null,
      href ? h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, ev.location?.name) : ev.location?.name,
      ev.location?.address && h('span', { class: 'muted' }, ` — ${ev.location.address}`),
    ),
    ev.group && h('p', { class: 'card__group' }, ev.group),
    ev.authorHandle && h('p', { class: 'muted' }, `Posted by @${ev.authorHandle}`),
    ev.description && h('p', { class: 'detail__desc' }, ev.description),
    source && h('p', null, h('a', { href: source, target: '_blank', rel: 'noopener noreferrer' }, 'Event page')),
    h('section', { 'aria-labelledby': 'detail-updates' },
      h('h3', { id: 'detail-updates' }, 'Updates'),
      updates.length
        ? h('ol', { class: 'updates' }, updates.map((u) => h('li', null,
            h('time', { datetime: u.createdAt, class: 'muted' }, formatDateTime(u.createdAt, opts)),
            h('p', null, u.text),
          )))
        : h('p', { class: 'muted' }, 'No announcements yet.'),
    ),
    opts.canEdit && h('div', { class: 'card__actions' },
      h('button', { type: 'button', class: 'btn', onclick: () => opts.onEdit?.(ev) }, 'Edit'),
      h('button', { type: 'button', class: 'btn btn--danger', onclick: () => opts.onDelete?.(ev) }, 'Delete'),
    ),
  ];
}

/**
 * Create the detail dialog controller.
 * @param {{api: {getEvent(uri: string): Promise<{data: object, stale: boolean}>},
 *   canEdit?: (ev: object) => boolean, onEdit?: (ev: object) => void, onDelete?: (ev: object) => void}} deps
 * @returns {{open(uri: string): Promise<void>, close(): void, element: HTMLDialogElement}}
 */
export function createDetailView({ api, canEdit = () => false, onEdit, onDelete }) {
  const body = h('div', { class: 'dialog__body' });
  const dialog = h('dialog', { class: 'dialog', 'aria-labelledby': 'detail-title' },
    h('button', { type: 'button', class: 'btn dialog__close', 'aria-label': 'Close', onclick: () => closeDialog(dialog) }, '×'),
    body,
  );

  async function open(uri) {
    body.replaceChildren(h('p', { id: 'detail-title', role: 'status' }, 'Loading…'));
    openDialog(dialog);
    try {
      const { data, stale } = await api.getEvent(uri);
      const close = () => closeDialog(dialog);
      body.replaceChildren(...renderDetail(data, {
        stale,
        canEdit: canEdit(data),
        onEdit: (ev) => { close(); onEdit?.(ev); },
        onDelete: (ev) => { close(); onDelete?.(ev); },
      }).filter(Boolean));
    } catch (err) {
      const msg = err?.status === 404 ? 'This event is no longer available.' : 'Could not load this event.';
      body.replaceChildren(h('p', { id: 'detail-title', role: 'alert' }, msg));
    }
  }

  return { open, close: () => closeDialog(dialog), element: dialog };
}
