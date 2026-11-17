// Dialoge: Aufgabenformular und Bestätigungen.
import { api } from './api.js';
import { refreshClassData } from './data.js';
import { render, state } from './store.js';
import { addDays, esc, formatFull, icon, subjectColor, SUBJECT_PRESETS, todayIso, toast } from './util.js';

const MAX_FILES = 6;
const MAX_BYTES = 5 * 1024 * 1024;
let lastFocus = null;

function modalRoot() {
  return document.getElementById('modal-root');
}

function openModal(html) {
  lastFocus = document.activeElement;
  modalRoot().innerHTML = `<div class="modal-backdrop" data-action="backdrop-close">${html}</div>`;
  document.body.classList.add('modal-open');
  const first = modalRoot().querySelector('[autofocus], input:not([type=hidden]), textarea, button');
  first?.focus();
}

export function closeModal() {
  if (!modalRoot().innerHTML) return;
  modalRoot().innerHTML = '';
  document.body.classList.remove('modal-open');
  lastFocus?.focus?.();
}

export const isModalOpen = () => Boolean(modalRoot().innerHTML);

/** Bestätigungsdialog statt des System-confirm(). */
export function confirmDialog(title, text, okLabel = 'Löschen', tone = 'danger') {
  return new Promise((resolve) => {
    openModal(`<section class="modal small" role="alertdialog" aria-modal="true" aria-labelledby="cf-title">
      <h2 id="cf-title">${esc(title)}</h2>
      <p class="muted">${esc(text)}</p>
      <div class="modal-actions">
        <button class="btn ghost" data-cf="no">Abbrechen</button>
        <button class="btn ${tone}" data-cf="yes" autofocus>${esc(okLabel)}</button>
      </div></section>`);
    const finish = (value) => {
      modalRoot().removeEventListener('click', onClick);
      closeModal();
      resolve(value);
    };
    const onClick = (event) => {
      const btn = event.target.closest('[data-cf]');
      if (btn) finish(btn.dataset.cf === 'yes');
      else if (event.target.classList.contains('modal-backdrop')) finish(false);
    };
    modalRoot().addEventListener('click', onClick);
    modalRoot().querySelector('.modal').escape = () => finish(false);
  });
}

/** Escape schließt den offenen Dialog. */
export function escapeModal() {
  const modal = modalRoot().querySelector('.modal');
  if (!modal) return;
  if (modal.escape) modal.escape();
  else closeModal();
}

export function openHomeworkForm({ id = null, copyFrom = null, date = null } = {}) {
  const existing = id ? state.homework.find((h) => h.id === id) : null;
  const source = existing || (copyFrom ? state.homework.find((h) => h.id === copyFrom) : null);
  const today = todayIso();
  const values = {
    subject: source?.subject ?? '',
    description: source?.description ?? '',
    dueDate: existing ? existing.dueDate : (date || addDays(today, 1)),
    pages: source?.pages ?? '',
    comment: source?.comment ?? '',
  };
  const title = existing ? 'Aufgabe bearbeiten' : source ? 'Aufgabe kopieren' : 'Neue Aufgabe';
  const author = existing ? existing.author.name : state.me.displayName;
  const dateChips = [['Heute', 0], ['Morgen', 1], ['Übermorgen', 2], ['In einer Woche', 7]];

  openModal(`<section class="modal" role="dialog" aria-modal="true" aria-labelledby="hw-title">
    <header class="modal-head">
      <div><h2 id="hw-title">${title}</h2>
        <p class="muted small">${source && !existing ? 'Wähl ein neues Datum – der Rest ist schon ausgefüllt' : 'Die ganze Klasse sieht diese Aufgabe'}</p></div>
      <button class="icon-btn" type="button" data-action="close-modal" aria-label="Schließen">${icon('x')}</button>
    </header>
    <form class="stack" data-form="homework" novalidate>
      <input type="hidden" name="id" value="${existing ? existing.id : ''}">
      <div class="field">
        <label for="hw-subject">Fach <span class="req">*</span></label>
        <input id="hw-subject" class="input" name="subject" maxlength="40" required value="${esc(values.subject)}" placeholder="Unten auswählen oder selbst eintippen" autocomplete="off">
        <div class="chips scroll-x" id="hw-subjects">
          ${SUBJECT_PRESETS.map((s) => `<button type="button" class="chip subject-chip${s === values.subject ? ' active' : ''}" data-subject="${esc(s)}" style="--c:${subjectColor(s)}">${esc(s)}</button>`).join('')}
        </div>
      </div>
      <div class="field">
        <label for="hw-desc">Was ist aufgegeben? <span class="req">*</span></label>
        <textarea id="hw-desc" class="input" name="description" rows="3" maxlength="2000" required placeholder="z. B. Kapitel 12 lesen, Fragen 1–4 beantworten">${esc(values.description)}</textarea>
      </div>
      <div class="field">
        <label for="hw-date">Bis wann? <span class="req">*</span></label>
        <input id="hw-date" class="input" type="date" name="dueDate" required value="${values.dueDate}">
        <div class="chips" id="hw-dates">${dateChips.map(([label, offset]) => `<button type="button" class="chip" data-offset="${offset}">${label}</button>`).join('')}</div>
        <small class="hint" id="hw-date-hint">${formatFull(values.dueDate)}</small>
      </div>
      <div class="grid-2">
        <div class="field">
          <label for="hw-pages">Seite, Übung</label>
          <input id="hw-pages" class="input" name="pages" maxlength="200" value="${esc(values.pages)}" placeholder="S. 45, Nr. 3">
        </div>
        <div class="field">
          <label>Eingetragen von</label>
          <div class="input readonly">${icon('user', 16)} ${esc(author)}</div>
        </div>
      </div>
      <div class="field">
        <label for="hw-comment">Kommentar</label>
        <textarea id="hw-comment" class="input" name="comment" rows="2" maxlength="1000" placeholder="z. B. ins Heft schreiben, Taschenrechner erlaubt">${esc(values.comment)}</textarea>
      </div>
      <div class="field">
        <label for="hw-files">Fotos zur Aufgabe</label>
        <label class="file-drop" for="hw-files">${icon('image', 20)} <span id="hw-files-label">Fotos auswählen (bis ${MAX_FILES} Stück, je bis 5 MB)</span></label>
        <input id="hw-files" class="visually-hidden" type="file" name="files" accept="image/jpeg,image/png,image/gif,image/webp" multiple>
        ${existing?.attachments.length ? `<small class="hint">Schon angehängt: ${existing.attachments.length}. Fotos löschst du auf der Seite der Aufgabe.</small>` : ''}
      </div>
      <p class="form-error" hidden></p>
      <footer class="modal-actions">
        <button type="button" class="btn ghost" data-action="close-modal">Abbrechen</button>
        <button type="submit" class="btn primary">${existing ? 'Speichern' : 'Aufgabe hinzufügen'}</button>
      </footer>
    </form>
  </section>`);

  const form = modalRoot().querySelector('form');
  const subjectInput = form.querySelector('#hw-subject');
  const dateInput = form.querySelector('#hw-date');
  const dateHint = form.querySelector('#hw-date-hint');
  const syncSubjectChips = () => {
    form.querySelectorAll('.subject-chip').forEach((chip) => chip.classList.toggle('active', chip.dataset.subject === subjectInput.value.trim()));
  };
  const syncDateHint = () => {
    dateHint.textContent = /^\d{4}-\d{2}-\d{2}$/.test(dateInput.value) ? formatFull(dateInput.value) : '';
  };

  form.querySelector('#hw-subjects').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-subject]');
    if (!chip) return;
    subjectInput.value = chip.dataset.subject;
    syncSubjectChips();
    form.querySelector('#hw-desc').focus();
  });
  subjectInput.addEventListener('input', syncSubjectChips);
  form.querySelector('#hw-dates').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-offset]');
    if (!chip) return;
    dateInput.value = addDays(todayIso(), Number(chip.dataset.offset));
    syncDateHint();
  });
  dateInput.addEventListener('input', syncDateHint);
  form.querySelector('#hw-files').addEventListener('change', (event) => {
    const files = [...event.target.files];
    form.querySelector('#hw-files-label').textContent = files.length
      ? `Ausgewählt: ${files.length} (${files.map((f) => f.name).join(', ')})`
      : `Fotos auswählen (bis ${MAX_FILES} Stück, je bis 5 MB)`;
  });
  if (!values.subject) subjectInput.focus();
  else form.querySelector('#hw-desc').focus();
}

export async function submitHomework(form) {
  const errorEl = form.querySelector('.form-error');
  const showError = (message) => {
    errorEl.textContent = message;
    errorEl.hidden = false;
  };
  errorEl.hidden = true;

  const fd = new FormData(form);
  const id = fd.get('id');
  const payload = {
    subject: String(fd.get('subject') || '').trim(),
    description: String(fd.get('description') || '').trim(),
    dueDate: String(fd.get('dueDate') || ''),
    pages: String(fd.get('pages') || '').trim(),
    comment: String(fd.get('comment') || '').trim(),
  };
  if (!payload.subject) return showError('Bitte gib ein Fach an');
  if (!payload.description) return showError('Bitte schreib, was aufgegeben ist');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.dueDate)) return showError('Bitte wähl das Abgabedatum');

  const files = [...form.querySelector('#hw-files').files];
  const existing = id ? state.homework.find((h) => h.id === Number(id)) : null;
  if (files.length + (existing?.attachments.length || 0) > MAX_FILES) return showError(`Höchstens ${MAX_FILES} Fotos pro Aufgabe`);
  const tooBig = files.find((f) => f.size > MAX_BYTES);
  if (tooBig) return showError(`„${tooBig.name}“ ist größer als 5 MB`);

  const submit = form.querySelector('[type=submit]');
  submit.disabled = true;
  submit.textContent = 'Wird gespeichert …';
  try {
    const saved = id
      ? await api(`/api/homework/${id}`, { method: 'PUT', body: payload })
      : await api('/api/homework', { method: 'POST', body: payload });
    let failed = 0;
    for (const file of files) {
      const body = new FormData();
      body.append('file', file);
      try {
        await api(`/api/homework/${saved.id}/attachments`, { method: 'POST', form: body });
      } catch {
        failed += 1;
      }
    }
    closeModal();
    await refreshClassData();
    render();
    toast(id ? 'Änderungen gespeichert' : 'Aufgabe eingetragen – die ganze Klasse sieht sie', 'success');
    if (failed) toast(`Fotos konnten nicht hochgeladen werden: ${failed}`, 'error');
  } catch (err) {
    showError(err.message);
    submit.disabled = false;
    submit.textContent = id ? 'Speichern' : 'Aufgabe hinzufügen';
  }
}
