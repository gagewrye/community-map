/**
 * Login dialog (Bluesky handle + app password).
 * @module views/loginView
 */
import { closeDialog, h, openDialog } from '../dom.js';

/**
 * @param {{login: (identifier: string, password: string) => Promise<any>, onLoggedIn?: () => void}} deps
 * @returns {{open(): void, element: HTMLDialogElement}}
 */
export function createLoginView({ login, onLoggedIn }) {
  const dialog = h('dialog', { class: 'dialog', 'aria-labelledby': 'login-title' });

  function open() {
    const status = h('p', { class: 'form-status', role: 'status' });
    const submit = h('button', { type: 'submit', class: 'btn btn--primary' }, 'Log in');
    const form = h('form', { class: 'compose' },
      h('div', { class: 'field' },
        h('label', { for: 'l-id' }, 'Bluesky handle'),
        h('input', { id: 'l-id', name: 'identifier', required: true, autocomplete: 'username', autocapitalize: 'none', placeholder: 'you.bsky.social' }),
      ),
      h('div', { class: 'field' },
        h('label', { for: 'l-pw' }, 'App password'),
        h('p', { class: 'hint', id: 'l-pw-hint' }, 'Create one in Bluesky → Settings → Privacy and security → App passwords. Never use your main password.'),
        h('input', { id: 'l-pw', name: 'password', type: 'password', required: true, autocomplete: 'current-password', 'aria-describedby': 'l-pw-hint' }),
      ),
      status,
      h('div', { class: 'card__actions' }, submit,
        h('button', { type: 'button', class: 'btn', onclick: () => closeDialog(dialog) }, 'Cancel')),
    );
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      submit.disabled = true;
      status.textContent = 'Logging in…';
      try {
        await login(form.elements.identifier.value, form.elements.password.value);
        closeDialog(dialog);
        onLoggedIn?.();
      } catch (err) {
        status.textContent = `Login failed: ${err.message}`;
      } finally {
        submit.disabled = false;
      }
    });
    dialog.replaceChildren(h('h2', { id: 'login-title' }, 'Log in with Bluesky'), form);
    openDialog(dialog);
  }

  return { open, element: dialog };
}
