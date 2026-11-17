// Точка входа: маршруты, обработчики кнопок, синхронизация с сервером.
import { api } from './api.js';
import { loadClass, loadEverything, loadHomework, loadMe, loadNotifications, refreshClassData } from './data.js';
import { closeModal, confirmDialog, escapeModal, isModalOpen, openHomeworkForm, submitHomework } from './forms.js';
import { currentSubscription, disablePush, enablePush, showSystemNotification } from './push.js';
import { render, setRenderer, state } from './store.js';
import { addDays, addMonths, storage, toast, todayIso, userTimezone } from './util.js';
import * as views from './views.js';

const SYNC_MS = 15000;
let lastRouteKey = '';

// ------------------------------------------------------------ тема

function applyTheme() {
  const pref = storage.get('cm.theme') || 'system';
  const dark = pref === 'dark' || (pref === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.querySelector('meta[name=theme-color]')?.setAttribute('content', dark ? '#141831' : '#7c5cff');
}

function setTheme(pref) {
  storage.set('cm.theme', pref);
  applyTheme();
  render();
}

// ------------------------------------------------------------ маршруты

function currentRoute() {
  const [name = '', param = null] = location.hash.replace(/^#\/?/, '').split('/');
  return { name: name || 'home', param };
}

const navigate = (path) => { location.hash = `#/${path}`; };

const PAGES = {
  home: views.homeView,
  tasks: views.tasksView,
  calendar: views.calendarView,
  notifications: views.notificationsView,
  stats: views.statsView,
  more: views.moreView,
  class: views.classView,
  profile: views.profileView,
  task: (param) => views.detailView(Number(param)),
};

function renderApp() {
  const root = document.getElementById('app');
  const route = currentRoute();
  const authPages = ['login', 'register'];

  if (!state.me) {
    if (!authPages.includes(route.name)) return navigate('login');
    root.innerHTML = views.authView(route.name);
    lastRouteKey = route.name;
    return;
  }
  if (authPages.includes(route.name)) return navigate('');
  if (!state.me.class) {
    if (route.name !== 'setup') return navigate('setup');
    root.innerHTML = views.setupView();
    lastRouteKey = 'setup';
    return;
  }
  if (route.name === 'setup') return navigate('');

  const page = (PAGES[route.name] || PAGES.home)(route.param);
  const key = `${route.name}/${route.param ?? ''}`;
  const changed = key !== lastRouteKey;
  lastRouteKey = key;

  // Сохраняем фокус и позицию курсора, если пользователь что-то печатал.
  const active = document.activeElement;
  const focusId = active?.id;
  const caret = active && 'selectionStart' in active ? active.selectionStart : null;

  root.innerHTML = views.shellView(route.name, page, changed);
  document.title = `${page.title.replace(/&[^;]+;/g, '')} · ClassMate`;
  if (changed) window.scrollTo(0, 0);
  if (focusId && !changed) {
    const el = document.getElementById(focusId);
    if (el) {
      el.focus();
      try { if (caret !== null) el.setSelectionRange(caret, caret); } catch { /* не текстовое поле */ }
    }
  }
}

setRenderer(renderApp);

// ------------------------------------------------------------ синхронизация и уведомления

function announce(items) {
  const key = `cm.lastNotified.${state.me.id}`;
  const maxId = items.reduce((max, n) => Math.max(max, n.id), 0);
  const stored = storage.get(key);
  storage.set(key, String(Math.max(maxId, Number(stored) || 0)));
  if (stored === null) return; // первый запуск на этом устройстве — старое не показываем

  const fresh = items.filter((n) => n.id > Number(stored) && !n.readAt).sort((a, b) => a.id - b.id);
  fresh.slice(-3).forEach((n) => {
    if (!document.hidden) toast(n.title, 'info');
    // Если вкладка скрыта и включён push, уведомление покажет service worker — не дублируем.
    if (!document.hidden || !state.pushSubscribed) {
      showSystemNotification(n, () => navigate(n.homeworkId ? `task/${n.homeworkId}` : 'notifications'));
    }
  });
}

let syncing = false;
async function sync() {
  if (!state.me || syncing) return;
  syncing = true;
  try {
    const s = await api(`/api/sync?tz=${encodeURIComponent(userTimezone())}`);
    let changed = false;
    if (state.me.class && s.classVersion !== state.classVersion) {
      // Могли измениться роль или название класса (или нас исключили) — обновляем всё.
      await loadMe();
      if (state.me?.class) await refreshClassData();
      changed = true;
    }
    if (state.doneCount !== null && s.doneCount !== state.doneCount) {
      await loadHomework();
      changed = true;
    }
    state.doneCount = s.doneCount;
    if (s.unread !== state.unread) {
      await loadNotifications();
      announce(state.notifications);
      changed = true;
    }
    if (changed && !['profile', 'class'].includes(currentRoute().name)) render();
    else if (changed) refreshBadges();
  } catch (err) {
    if (err.status === 401) {
      state.me = null;
      render();
    }
  } finally {
    syncing = false;
  }
}

/** Обновляет только счётчики на меню, не трогая формы на странице. */
function refreshBadges() {
  document.querySelectorAll('a[href="#/notifications"]').forEach((link) => {
    let badge = link.querySelector('.badge');
    if (!state.unread) return badge?.remove();
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'badge';
      (link.querySelector('.nav-ico') || link).append(badge);
    }
    badge.textContent = state.unread > 99 ? '99+' : String(state.unread);
  });
}

async function afterAuth() {
  await loadEverything();
  if (state.me) announce(state.notifications);
  await sync();
  navigate(state.me?.class ? '' : 'setup');
  render();
}

// ------------------------------------------------------------ действия

async function toggleDone(id) {
  const h = state.homework.find((x) => x.id === id);
  if (!h) return;
  const next = !h.done;
  h.done = next;
  render();
  try {
    const result = await api(`/api/homework/${id}/done`, { method: 'PUT', body: { done: next } });
    state.doneCount = result.doneCount;
    if (next) toast('Отлично! Задание выполнено ✓', 'success');
  } catch (err) {
    h.done = !next;
    render();
    toast(err.message, 'error');
  }
}

async function uploadPhotos(homeworkId, files) {
  let ok = 0;
  for (const file of files) {
    if (file.size > 5 * 1024 * 1024) {
      toast(`«${file.name}» больше 5 МБ`, 'error');
      continue;
    }
    const form = new FormData();
    form.append('file', file);
    try {
      await api(`/api/homework/${homeworkId}/attachments`, { method: 'POST', form });
      ok += 1;
    } catch (err) {
      toast(err.message, 'error');
      break;
    }
  }
  await refreshClassData();
  render();
  if (ok) toast(`Фото добавлено: ${ok}`, 'success');
}

function shiftCalendar(dir) {
  const { view, date } = state.calendar;
  state.calendar.date = view === 'month' ? addMonths(date, dir) : addDays(date, view === 'week' ? 7 * dir : dir);
}

const actions = {
  'new-task': (el) => openHomeworkForm({ date: el.dataset.date || null }),
  'edit-task': (el) => openHomeworkForm({ id: Number(el.dataset.id) }),
  'copy-task': (el) => openHomeworkForm({ copyFrom: Number(el.dataset.id) }),
  'close-modal': () => closeModal(),
  'backdrop-close': (el, event) => { if (event.target === el) closeModal(); },
  'toggle-done': (el) => toggleDone(Number(el.dataset.id)),

  async 'delete-task'(el) {
    const id = Number(el.dataset.id);
    if (!(await confirmDialog('Удалить задание?', 'Оно пропадёт у всех участников класса вместе с фото.'))) return;
    await api(`/api/homework/${id}`, { method: 'DELETE' });
    await refreshClassData();
    navigate('tasks');
    render();
    toast('Задание удалено', 'success');
  },

  async 'delete-attachment'(el) {
    if (!(await confirmDialog('Удалить фото?', 'Фото пропадёт у всех участников класса.'))) return;
    await api(`/api/attachments/${el.dataset.id}`, { method: 'DELETE' });
    await refreshClassData();
    render();
    toast('Фото удалено', 'success');
  },

  'set-filter': (el) => {
    state.filters.status = el.dataset.value;
    render();
  },
  'open-filter': (el) => {
    state.filters = { status: el.dataset.value, subject: '', query: '' };
    navigate('tasks');
  },
  'go-date': (el) => {
    state.calendar = { view: 'day', date: el.dataset.date };
    navigate('calendar');
  },

  'cal-nav': (el) => { shiftCalendar(Number(el.dataset.dir)); render(); },
  'cal-today': () => { state.calendar.date = todayIso(); render(); },
  'cal-view': (el) => { state.calendar.view = el.dataset.value; render(); },
  'cal-select': (el) => { state.calendar.date = el.dataset.date; render(); },
  'cal-open-day': (el) => { state.calendar = { view: 'day', date: el.dataset.date }; render(); },

  async 'mark-read'(el) {
    await api('/api/notifications/read', { method: 'POST', body: { ids: [Number(el.dataset.id)] } });
    await loadNotifications();
    render();
  },
  async 'mark-all-read'() {
    await api('/api/notifications/read', { method: 'POST', body: { all: true } });
    await loadNotifications();
    render();
  },
  async 'open-notification'(el) {
    api('/api/notifications/read', { method: 'POST', body: { ids: [Number(el.dataset.id)] } })
      .then(loadNotifications).then(() => render()).catch(() => {});
    navigate(`task/${el.dataset.task}`);
  },

  'toggle-theme': () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'),
  'set-theme': (el) => setTheme(el.dataset.value),

  async logout() {
    await api('/api/auth/logout', { method: 'POST' });
    Object.assign(state, { me: null, cls: null, homework: [], notifications: [], unread: 0, classVersion: null, doneCount: null });
    navigate('login');
    render();
  },

  async 'copy-code'() {
    const code = state.cls?.inviteCode;
    try {
      await navigator.clipboard.writeText(code);
      toast(`Код ${code} скопирован`, 'success');
    } catch {
      toast(`Код приглашения: ${code}`, 'info');
    }
  },
  async 'regen-code'() {
    if (!(await confirmDialog('Создать новый код?', 'Старый код перестанет работать. Уже вступившие участники останутся в классе.', 'Создать', 'primary'))) return;
    await api('/api/class/invite-code', { method: 'POST' });
    await loadClass();
    render();
    toast('Новый код создан', 'success');
  },
  async 'set-role'(el) {
    await api(`/api/class/members/${el.dataset.id}`, { method: 'PATCH', body: { role: el.dataset.value } });
    await loadClass();
    render();
    toast('Роль изменена', 'success');
  },
  async 'remove-member'(el) {
    if (!(await confirmDialog(`Исключить ${el.dataset.name}?`, 'Участник потеряет доступ к заданиям класса. Его задания останутся.', 'Исключить'))) return;
    await api(`/api/class/members/${el.dataset.id}`, { method: 'DELETE' });
    await loadClass();
    render();
    toast('Участник исключён', 'success');
  },
  async 'leave-class'() {
    const last = state.cls?.members.length === 1;
    const text = last ? 'Ты последний участник: класс и все задания будут удалены навсегда.' : 'Ты сможешь вернуться по коду приглашения.';
    if (!(await confirmDialog('Выйти из класса?', text, 'Выйти'))) return;
    await api('/api/class/leave', { method: 'POST' });
    await loadEverything();
    navigate('setup');
    render();
  },

  async 'enable-push'(el) {
    el.disabled = true;
    try {
      await enablePush();
      state.pushSubscribed = true;
      toast('Уведомления включены', 'success');
    } finally {
      el.disabled = false;
      render();
    }
  },
  async 'disable-push'() {
    await disablePush();
    state.pushSubscribed = false;
    render();
    toast('Push-уведомления выключены', 'info');
  },
  async 'test-push'() {
    await api('/api/push/test', { method: 'POST' });
    toast('Тестовое уведомление отправлено. Сверни сайт, чтобы увидеть его в системе.', 'info');
  },
};

// ------------------------------------------------------------ формы

function formError(form, message) {
  const el = form.querySelector('.form-error');
  if (el) {
    el.textContent = message;
    el.hidden = false;
  } else toast(message, 'error');
}

const forms = {
  homework: submitHomework,

  async login(form) {
    const fd = new FormData(form);
    state.me = await api('/api/auth/login', {
      method: 'POST',
      body: { username: fd.get('username'), password: fd.get('password'), timezone: userTimezone() },
    });
    await afterAuth();
  },
  async register(form) {
    const fd = new FormData(form);
    state.me = await api('/api/auth/register', {
      method: 'POST',
      body: { displayName: fd.get('displayName'), username: fd.get('username'), password: fd.get('password'), timezone: userTimezone() },
    });
    toast('Аккаунт создан!', 'success');
    await afterAuth();
  },
  async 'create-class'(form) {
    state.me = await api('/api/classes', { method: 'POST', body: { name: new FormData(form).get('name') } });
    await afterAuth();
    toast('Класс создан! Поделись кодом приглашения с одноклассниками', 'success');
    navigate('class');
  },
  async 'join-class'(form) {
    state.me = await api('/api/classes/join', { method: 'POST', body: { code: new FormData(form).get('code') } });
    await afterAuth();
    toast(`Добро пожаловать в ${state.me.class.name}!`, 'success');
  },
  async 'rename-class'(form) {
    await api('/api/class', { method: 'PATCH', body: { name: new FormData(form).get('name') } });
    await loadMe();
    await loadClass();
    render();
    toast('Название сохранено', 'success');
  },
  async profile(form) {
    state.me = await api('/api/me', { method: 'PATCH', body: { displayName: new FormData(form).get('displayName') } });
    await loadHomework();
    render();
    toast('Профиль сохранён', 'success');
  },
  async password(form) {
    const fd = new FormData(form);
    await api('/api/me/password', {
      method: 'PUT',
      body: { currentPassword: fd.get('currentPassword'), newPassword: fd.get('newPassword') },
    });
    form.reset();
    toast('Пароль изменён', 'success');
  },
};

// ------------------------------------------------------------ события

document.addEventListener('click', async (event) => {
  const el = event.target.closest('[data-action]');
  if (!el || !actions[el.dataset.action]) return;
  if (el.tagName === 'A') event.preventDefault();
  try {
    await actions[el.dataset.action](el, event);
  } catch (err) {
    toast(err.message || 'Что-то пошло не так', 'error');
  }
});

document.addEventListener('submit', async (event) => {
  const form = event.target;
  const handler = forms[form.dataset.form];
  if (!handler) return;
  event.preventDefault();
  const button = form.querySelector('[type=submit]');
  const errorEl = form.querySelector('.form-error');
  if (errorEl) errorEl.hidden = true;
  if (form.dataset.form !== 'homework' && button) button.disabled = true;
  try {
    await handler(form);
  } catch (err) {
    formError(form, err.message || 'Что-то пошло не так');
  } finally {
    if (form.dataset.form !== 'homework' && button && button.isConnected) button.disabled = false;
  }
});

document.addEventListener('change', async (event) => {
  const el = event.target;
  try {
    if (el.dataset.change === 'subject-filter') {
      state.filters.subject = el.value;
      render();
    } else if (el.dataset.change === 'pref') {
      const value = el.type === 'checkbox' ? el.checked : el.value;
      if (el.type === 'time' && !value) return;
      state.me = await api('/api/me', { method: 'PATCH', body: { [el.dataset.key]: value } });
      toast('Настройки сохранены', 'success');
    } else if (el.dataset.change === 'attach') {
      const files = [...el.files];
      if (files.length) await uploadPhotos(Number(el.dataset.id), files);
    }
  } catch (err) {
    toast(err.message, 'error');
    if (el.dataset.change === 'pref') render();
  }
});

document.addEventListener('input', (event) => {
  if (event.target.dataset.input === 'search') {
    state.filters.query = event.target.value;
    const list = document.getElementById('task-list');
    if (list) list.innerHTML = views.taskListHtml();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && isModalOpen()) escapeModal();
});

window.addEventListener('hashchange', () => {
  closeModal();
  render();
});

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) sync();
});

window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if ((storage.get('cm.theme') || 'system') === 'system') {
    applyTheme();
    render();
  }
});

navigator.serviceWorker?.addEventListener('message', (event) => {
  if (event.data?.type === 'navigate' && event.data.hash) location.hash = event.data.hash;
});

// ------------------------------------------------------------ запуск

async function boot() {
  applyTheme();
  try {
    await loadEverything();
    if (state.me) {
      announce(state.notifications);
      await sync();
    }
  } catch (err) {
    toast(err.message, 'error');
  }
  try {
    state.pushSubscribed = Boolean(await currentSubscription());
  } catch {
    state.pushSubscribed = false;
  }
  render();
  setInterval(sync, SYNC_MS);
}

boot();
