// Модальные окна: форма задания и подтверждение действий.
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

/** Красивое окно подтверждения вместо системного confirm(). */
export function confirmDialog(title, text, okLabel = 'Удалить', tone = 'danger') {
  return new Promise((resolve) => {
    openModal(`<section class="modal small" role="alertdialog" aria-modal="true" aria-labelledby="cf-title">
      <h2 id="cf-title">${esc(title)}</h2>
      <p class="muted">${esc(text)}</p>
      <div class="modal-actions">
        <button class="btn ghost" data-cf="no">Отмена</button>
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

/** Нажата клавиша Escape: закрыть то, что открыто. */
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
  const title = existing ? 'Редактировать задание' : source ? 'Копия задания' : 'Новое задание';
  const author = existing ? existing.author.name : state.me.displayName;
  const dateChips = [['Сегодня', 0], ['Завтра', 1], ['Послезавтра', 2], ['Через неделю', 7]];

  openModal(`<section class="modal" role="dialog" aria-modal="true" aria-labelledby="hw-title">
    <header class="modal-head">
      <div><h2 id="hw-title">${title}</h2>
        <p class="muted small">${source && !existing ? 'Выбери новую дату — остальное уже заполнено' : 'Задание увидит весь класс'}</p></div>
      <button class="icon-btn" type="button" data-action="close-modal" aria-label="Закрыть">${icon('x')}</button>
    </header>
    <form class="stack" data-form="homework" novalidate>
      <input type="hidden" name="id" value="${existing ? existing.id : ''}">
      <div class="field">
        <label for="hw-subject">Предмет <span class="req">*</span></label>
        <input id="hw-subject" class="input" name="subject" maxlength="40" required value="${esc(values.subject)}" placeholder="Выбери ниже или впиши свой" autocomplete="off">
        <div class="chips scroll-x" id="hw-subjects">
          ${SUBJECT_PRESETS.map((s) => `<button type="button" class="chip subject-chip${s === values.subject ? ' active' : ''}" data-subject="${esc(s)}" style="--c:${subjectColor(s)}">${esc(s)}</button>`).join('')}
        </div>
      </div>
      <div class="field">
        <label for="hw-desc">Что задали <span class="req">*</span></label>
        <textarea id="hw-desc" class="input" name="description" rows="3" maxlength="2000" required placeholder="Например: выучить параграф 12, ответить на вопросы 1–4">${esc(values.description)}</textarea>
      </div>
      <div class="field">
        <label for="hw-date">На какую дату <span class="req">*</span></label>
        <input id="hw-date" class="input" type="date" name="dueDate" required value="${values.dueDate}">
        <div class="chips" id="hw-dates">${dateChips.map(([label, offset]) => `<button type="button" class="chip" data-offset="${offset}">${label}</button>`).join('')}</div>
        <small class="hint" id="hw-date-hint">${formatFull(values.dueDate)}</small>
      </div>
      <div class="grid-2">
        <div class="field">
          <label for="hw-pages">Страница, упражнение</label>
          <input id="hw-pages" class="input" name="pages" maxlength="200" value="${esc(values.pages)}" placeholder="стр. 45, упр. 3">
        </div>
        <div class="field">
          <label>Кто добавил</label>
          <div class="input readonly">${icon('user', 16)} ${esc(author)}</div>
        </div>
      </div>
      <div class="field">
        <label for="hw-comment">Комментарий</label>
        <textarea id="hw-comment" class="input" name="comment" rows="2" maxlength="1000" placeholder="Например: сдавать в тетради, можно с калькулятором">${esc(values.comment)}</textarea>
      </div>
      <div class="field">
        <label for="hw-files">Фото задания</label>
        <label class="file-drop" for="hw-files">${icon('image', 20)} <span id="hw-files-label">Выбрать фото (до ${MAX_FILES} шт., до 5 МБ)</span></label>
        <input id="hw-files" class="visually-hidden" type="file" name="files" accept="image/jpeg,image/png,image/gif,image/webp" multiple>
        ${existing?.attachments.length ? `<small class="hint">Уже прикреплено: ${existing.attachments.length}. Удалить фото можно на странице задания.</small>` : ''}
      </div>
      <p class="form-error" hidden></p>
      <footer class="modal-actions">
        <button type="button" class="btn ghost" data-action="close-modal">Отмена</button>
        <button type="submit" class="btn primary">${existing ? 'Сохранить' : 'Добавить задание'}</button>
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
      ? `Выбрано фото: ${files.length} (${files.map((f) => f.name).join(', ')})`
      : `Выбрать фото (до ${MAX_FILES} шт., до 5 МБ)`;
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
  if (!payload.subject) return showError('Укажи предмет');
  if (!payload.description) return showError('Напиши, что задали');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.dueDate)) return showError('Выбери дату, к которой нужно сделать задание');

  const files = [...form.querySelector('#hw-files').files];
  const existing = id ? state.homework.find((h) => h.id === Number(id)) : null;
  if (files.length + (existing?.attachments.length || 0) > MAX_FILES) return showError(`Можно прикрепить не больше ${MAX_FILES} фото`);
  const tooBig = files.find((f) => f.size > MAX_BYTES);
  if (tooBig) return showError(`Файл «${tooBig.name}» больше 5 МБ`);

  const submit = form.querySelector('[type=submit]');
  submit.disabled = true;
  submit.textContent = 'Сохраняем…';
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
    toast(id ? 'Изменения сохранены' : 'Задание добавлено — его видит весь класс', 'success');
    if (failed) toast(`Не удалось загрузить фото: ${failed}`, 'error');
  } catch (err) {
    showError(err.message);
    submit.disabled = false;
    submit.textContent = id ? 'Сохранить' : 'Добавить задание';
  }
}
