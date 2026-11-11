/**
 * Create / edit event form in a <dialog>, validated client-side against the lexicon.
 * @module views/composeView
 */
import { closeDialog, h, openDialog } from '../dom.js';
import { buildEventRecord, parseAtUri, validateEventRecord, validateHashtag } from '../records.js';

/**
 * ISO timestamp → value for <input type="datetime-local"> in local time.
 * @param {string} iso
 * @returns {string}
 */
export function isoToLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/**
 * datetime-local value (local time) → ISO string, or "" if empty/invalid.
 * @param {string} value
 * @returns {string}
 */
export function localInputToIso(value) {
  if (!value) return '';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '' : d.toISOString();
}

const FIELDS = ['name', 'description', 'startsAt', 'endsAt', 'locationName', 'address', 'lat', 'lng', 'tags', 'group', 'hashtag'];

/**
 * Read raw values from the compose form.
 * @param {HTMLFormElement} form
 * @returns {Record<string, string>}
 */
export function readForm(form) {
  return Object.fromEntries(FIELDS.map((f) => [f, form.elements[f]?.value ?? '']));
}

/**
 * Turn form values into a record and validate it.
 * Error keys are form field names (coords errors are reported on "lat").
 * @param {Record<string, string>} values
 * @param {{createdAt?: string, sourceUrl?: string}} [base] preserved fields when editing
 * @returns {{record: object, errors: Record<string, string>}}
 */
export function validateForm(values, base = {}) {
  const record = buildEventRecord({
    ...values,
    startsAt: localInputToIso(values.startsAt),
    endsAt: localInputToIso(values.endsAt),
    createdAt: base.createdAt,
    sourceUrl: base.sourceUrl,
  });
  const errors = validateEventRecord(record);
  const partialCoords = Boolean(values.lat?.trim()) !== Boolean(values.lng?.trim());
  if (partialCoords) errors.coords = 'Enter both latitude and longitude, or neither.';
  if (errors.coords) {
    errors.lat = errors.coords;
    delete errors.coords;
  }
  const tagErr = validateHashtag(values.hashtag);
  if (tagErr) errors.hashtag = tagErr;
  return { record, errors };
}

function field(name, label, input, hint) {
  input.id = `c-${name}`;
  input.name = name;
  return h('div', { class: 'field' },
    h('label', { for: input.id }, label),
    hint && h('p', { class: 'hint', id: `c-${name}-hint` }, hint),
    input,
    h('p', { class: 'field__error', id: `c-${name}-err` }),
  );
}

/**
 * Show errors next to fields (aria-invalid + aria-describedby) and focus the first one.
 * @param {HTMLFormElement} form
 * @param {Record<string, string>} errors
 */
export function showErrors(form, errors) {
  for (const f of FIELDS) {
    const input = form.elements[f];
    const err = form.querySelector(`#c-${f}-err`);
    if (!input || !err) continue;
    const msg = errors[f] || '';
    err.textContent = msg;
    input.setAttribute('aria-invalid', String(Boolean(msg)));
    const hint = form.querySelector(`#c-${f}-hint`) ? `c-${f}-hint ` : '';
    input.setAttribute('aria-describedby', `${hint}c-${f}-err`.trim());
  }
  const first = FIELDS.find((f) => errors[f]);
  if (first) form.elements[first].focus();
}

/**
 * Build the compose form element (pre-filled when editing).
 * @param {object|null} ev EventView being edited, or null for a new event
 * @returns {HTMLFormElement}
 */
export function buildForm(ev) {
  const loc = ev?.location || {};
  const input = (attrs) => h('input', attrs);
  return h('form', { class: 'compose', novalidate: true },
    field('name', 'Event name', input({ required: true, maxlength: 200, value: ev?.name ?? '' })),
    field('description', 'Description', h('textarea', { rows: 4, maxlength: 3000, value: ev?.description ?? '' })),
    h('div', { class: 'field-row' },
      field('startsAt', 'Starts', input({ type: 'datetime-local', required: true, value: isoToLocalInput(ev?.startsAt) })),
      field('endsAt', 'Ends', input({ type: 'datetime-local', required: true, value: isoToLocalInput(ev?.endsAt) })),
    ),
    field('locationName', 'Location name', input({ required: true, maxlength: 200, value: loc.name ?? '', placeholder: 'Price Center East' })),
    field('address', 'Address (optional)', input({ maxlength: 300, value: loc.address ?? '' })),
    h('div', { class: 'field-row' },
      field('lat', 'Latitude (optional)', input({ inputmode: 'decimal', value: loc.lat ?? '' })),
      field('lng', 'Longitude (optional)', input({ inputmode: 'decimal', value: loc.lng ?? '' })),
    ),
    h('button', { type: 'button', class: 'btn', dataset: { action: 'locate' } }, 'Use my location'),
    field('tags', 'Tags', input({ value: (ev?.tags || []).join(', '), placeholder: 'free food, music' }), 'Comma-separated, up to 10.'),
    field('group', 'Group / org (optional)', input({ maxlength: 100, value: ev?.group ?? '' })),
    field('hashtag', 'Sync from Bluesky hashtag (optional)', input({ maxlength: 64, placeholder: 'ucsdhackathon' }),
      'Your Bluesky posts with this hashtag appear as updates on the event.'),
    h('p', { class: 'form-status', role: 'status' }),
    h('div', { class: 'card__actions' },
      h('button', { type: 'submit', class: 'btn btn--primary' }, ev ? 'Save changes' : 'Create event'),
      ev && h('button', { type: 'button', class: 'btn btn--danger', dataset: { action: 'delete' } }, 'Delete'),
      h('button', { type: 'button', class: 'btn', dataset: { action: 'cancel' } }, 'Cancel'),
    ),
  );
}

/**
 * Create the compose dialog controller.
 * @param {{getWriter: () => object|null, geo?: {request(): Promise<{lat: number, lng: number}>},
 *   onSaved?: (r: {uri: string}) => void, onDeleted?: (uri: string) => void,
 *   toast?: (msg: string, o?: object) => void, confirmImpl?: (msg: string) => boolean}} deps
 * @returns {{open(ev?: object|null): void, remove(ev: object): Promise<void>, element: HTMLDialogElement}}
 */
export function createComposeView({ getWriter, geo, onSaved, onDeleted, toast = () => {}, confirmImpl = (m) => globalThis.confirm(m) }) {
  const dialog = h('dialog', { class: 'dialog', 'aria-labelledby': 'compose-title' });

  function open(ev = null) {
    const form = buildForm(ev);
    const status = form.querySelector('.form-status');
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      submit(form, ev, status);
    });
    form.querySelector('[data-action=cancel]').onclick = () => closeDialog(dialog);
    form.querySelector('[data-action=locate]').onclick = () => locate(form, status);
    const del = form.querySelector('[data-action=delete]');
    if (del) del.onclick = () => remove(ev);
    dialog.replaceChildren(h('h2', { id: 'compose-title' }, ev ? 'Edit event' : 'New event'), form);
    openDialog(dialog);
  }

  async function locate(form, status) {
    try {
      const p = await geo.request();
      form.elements.lat.value = p.lat.toFixed(6);
      form.elements.lng.value = p.lng.toFixed(6);
    } catch (err) {
      status.textContent = err.message;
    }
  }

  async function submit(form, ev, status) {
    const values = readForm(form);
    const { record, errors } = validateForm(values, ev ? { createdAt: ev.createdAt ?? ev.indexedAt, sourceUrl: ev.sourceUrl } : {});
    showErrors(form, errors);
    if (Object.keys(errors).length) return;
    const writer = getWriter();
    if (!writer) return void (status.textContent = 'Log in to post events.');
    const btn = form.querySelector('[type=submit]');
    btn.disabled = true;
    status.textContent = 'Saving…';
    try {
      const res = ev ? await writer.updateEvent(parseAtUri(ev.uri).rkey, record) : await writer.createEvent(record);
      if (values.hashtag.trim()) await writer.createListener(res.uri, values.hashtag);
      closeDialog(dialog);
      onSaved?.(res);
    } catch (err) {
      status.textContent = `Could not save: ${err.message}`;
    } finally {
      btn.disabled = false;
    }
  }

  async function remove(ev) {
    const writer = getWriter();
    if (!writer || !confirmImpl(`Delete “${ev.name}”?`)) return;
    try {
      await writer.deleteEvent(parseAtUri(ev.uri).rkey);
      closeDialog(dialog);
      onDeleted?.(ev.uri);
    } catch (err) {
      toast(`Could not delete: ${err.message}`, { kind: 'error' });
    }
  }

  return { open, remove, element: dialog };
}
