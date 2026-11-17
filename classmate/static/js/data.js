// Загрузка данных с сервера в state.
import { api } from './api.js';
import { state } from './store.js';

export async function loadMe() {
  try {
    state.me = await api('/api/me');
  } catch (err) {
    if (err.status === 401) state.me = null;
    else throw err;
  }
}

export async function loadClass() {
  if (!state.me?.class) {
    state.cls = null;
    return;
  }
  state.cls = await api('/api/class');
  state.classVersion = state.cls.version;
}

export async function loadHomework() {
  state.homework = state.me?.class ? await api('/api/homework') : [];
}

export async function loadNotifications() {
  if (!state.me) return;
  const data = await api('/api/notifications');
  state.notifications = data.items;
  state.unread = data.unread;
}

/** Перезагружает класс и задания (после любых изменений). */
export async function refreshClassData() {
  await Promise.all([loadClass(), loadHomework()]);
}

export async function loadEverything() {
  await loadMe();
  if (!state.me) return;
  await Promise.all([loadClass(), loadHomework(), loadNotifications()]);
}
