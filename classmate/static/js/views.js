// Разметка экранов. Каждая функция возвращает HTML-строку; пользовательский текст всегда экранируется.
import { state } from './store.js';
import { notificationPermission, pushSupported } from './push.js';
import {
  addDays, countTasks, esc, formatDayMonth, formatFull, formatMonth, formatShort, formatWeekday,
  icon, initials, isoOf, LOGO, parseIso, plural, relativeDay, startOfWeek, subjectColor,
  timeAgo, todayIso, truncate,
} from './util.js';

const ROLE_LABEL = { admin: 'Администратор', member: 'Участник' };

// ------------------------------------------------------------ общие кусочки

function emptyState(iconName, title, text = '', action = '') {
  return `<div class="empty rise">
    <div class="empty-icon">${icon(iconName, 28)}</div>
    <h3>${title}</h3>${text ? `<p>${text}</p>` : ''}${action}
  </div>`;
}

function dueText(h, today) {
  if (!h.done && h.dueDate < today) {
    const n = -Math.round((parseIso(h.dueDate) - parseIso(today)) / 86400000);
    return `Просрочено на ${n} ${plural(n, ['день', 'дня', 'дней'])}`;
  }
  return `${relativeDay(h.dueDate, today)} · ${formatShort(h.dueDate)}`;
}

export function taskCard(h, index = 0) {
  const today = todayIso();
  const overdue = !h.done && h.dueDate < today;
  const meta = [];
  if (h.pages) meta.push(`${icon('file', 14)} ${esc(h.pages)}`);
  meta.push(`${icon('user', 14)} ${esc(h.author.name)}`);
  if (h.attachments.length) meta.push(`${icon('image', 14)} ${h.attachments.length}`);
  return `<article class="task card rise${h.done ? ' is-done' : ''}${overdue ? ' is-overdue' : ''}"
      style="--c:${subjectColor(h.subject)};--i:${Math.min(index, 12)}">
    <div class="task-top">
      <span class="subject-pill">${esc(h.subject)}</span>
      <span class="due-chip${overdue ? ' danger' : ''}">${esc(dueText(h, today))}</span>
    </div>
    <h3 class="task-title"><a href="#/task/${h.id}">${esc(truncate(h.description, 160))}</a></h3>
    <p class="task-meta">${meta.map((m) => `<span>${m}</span>`).join('')}</p>
    <div class="task-actions">
      <button class="btn sm ${h.done ? 'success' : 'soft'}" data-action="toggle-done" data-id="${h.id}" aria-pressed="${h.done}">
        ${h.done ? `${icon('check', 16)} Выполнено` : 'Отметить как выполненное'}
      </button>
      <a class="btn sm ghost" href="#/task/${h.id}">Подробнее</a>
    </div>
  </article>`;
}

const cards = (list) => `<div class="task-grid">${list.map((h, i) => taskCard(h, i)).join('')}</div>`;

// ------------------------------------------------------------ вход и регистрация

export function authView(mode) {
  const isLogin = mode === 'login';
  return `<div class="auth">
    <div class="auth-card card rise">
      <div class="auth-brand">${LOGO}<div><h1>ClassMate</h1><p>Домашние задания всего класса в одном месте</p></div></div>
      <div class="segmented" role="tablist">
        <a href="#/login" class="${isLogin ? 'active' : ''}" role="tab" aria-selected="${isLogin}">Вход</a>
        <a href="#/register" class="${!isLogin ? 'active' : ''}" role="tab" aria-selected="${!isLogin}">Регистрация</a>
      </div>
      <form class="stack" data-form="${isLogin ? 'login' : 'register'}" novalidate>
        ${isLogin ? '' : `<div class="field"><label for="f-name">Как тебя зовут</label>
          <input id="f-name" class="input" name="displayName" maxlength="40" required placeholder="Например, Аня Смирнова" autocomplete="name"></div>`}
        <div class="field"><label for="f-login">Логин</label>
          <input id="f-login" class="input" name="username" maxlength="32" required placeholder="anya_7b" autocomplete="username" autocapitalize="off" spellcheck="false">
          ${isLogin ? '' : '<small class="hint">Латинские буквы, цифры, точка или «_», от 3 символов</small>'}</div>
        <div class="field"><label for="f-pass">Пароль</label>
          <input id="f-pass" class="input" type="password" name="password" minlength="6" required autocomplete="${isLogin ? 'current-password' : 'new-password'}" placeholder="Не короче 6 символов"></div>
        <p class="form-error" hidden></p>
        <button class="btn primary lg block" type="submit">${isLogin ? 'Войти' : 'Создать аккаунт'}</button>
      </form>
    </div>
  </div>`;
}

export function setupView() {
  return `<div class="auth">
    <div class="setup rise">
      <div class="auth-brand">${LOGO}<div><h1>Привет, ${esc(state.me.displayName)}!</h1><p>Осталось подключиться к своему классу</p></div></div>
      <div class="setup-grid">
        <form class="card stack" data-form="join-class" novalidate>
          <div class="setup-icon">${icon('key', 24)}</div>
          <h2>Вступить по коду</h2>
          <p class="muted">Попроси код у одноклассника или администратора класса.</p>
          <input class="input code-input" name="code" maxlength="12" required placeholder="Например, K7M2QX" autocomplete="off" autocapitalize="characters">
          <p class="form-error" hidden></p>
          <button class="btn primary block" type="submit">Вступить в класс</button>
        </form>
        <form class="card stack" data-form="create-class" novalidate>
          <div class="setup-icon">${icon('sparkles', 24)}</div>
          <h2>Создать класс</h2>
          <p class="muted">Ты станешь администратором и получишь код приглашения для остальных.</p>
          <input class="input" name="name" maxlength="60" required placeholder="Например, 7 «Б»">
          <p class="form-error" hidden></p>
          <button class="btn soft block" type="submit">Создать класс</button>
        </form>
      </div>
      <button class="btn ghost" data-action="logout">${icon('logout', 16)} Выйти из аккаунта</button>
    </div>
  </div>`;
}

// ------------------------------------------------------------ оболочка

const NAV = [
  { key: 'home', href: '#/', label: 'Главная', icon: 'home' },
  { key: 'tasks', href: '#/tasks', label: 'Задания', icon: 'list' },
  { key: 'calendar', href: '#/calendar', label: 'Календарь', icon: 'calendar' },
  { key: 'stats', href: '#/stats', label: 'Статистика', icon: 'chart' },
  { key: 'notifications', href: '#/notifications', label: 'Уведомления', icon: 'bell' },
  { key: 'class', href: '#/class', label: 'Мой класс', icon: 'users' },
  { key: 'profile', href: '#/profile', label: 'Профиль', icon: 'user' },
];
const BOTTOM = ['home', 'tasks', 'calendar', 'notifications', 'more'];
const NAV_ALIAS = { task: 'tasks' };

function navLink(item, active, cls) {
  const badge = item.key === 'notifications' && state.unread
    ? `<span class="badge">${state.unread > 99 ? '99+' : state.unread}</span>` : '';
  return `<a class="${cls}${active ? ' active' : ''}" href="${item.href}"${active ? ' aria-current="page"' : ''}>
    <span class="nav-ico">${icon(item.icon)}${cls === 'tab' ? badge : ''}</span><span>${item.label}</span>${cls === 'tab' ? '' : badge}</a>`;
}

export function shellView(routeName, page, animate) {
  const active = NAV_ALIAS[routeName] || routeName;
  const moreActive = ['stats', 'class', 'profile', 'more'].includes(active);
  const bottomItems = BOTTOM.map((key) => (key === 'more'
    ? { key: 'more', href: '#/more', label: 'Ещё', icon: 'more' }
    : NAV.find((n) => n.key === key)));
  const dark = document.documentElement.dataset.theme === 'dark';

  return `<div class="shell">
    <aside class="sidebar">
      <a class="brand" href="#/">${LOGO}<span>ClassMate</span></a>
      <button class="btn primary block side-add" data-action="new-task">${icon('plus', 18)} Добавить задание</button>
      <nav class="side-nav" aria-label="Основное меню">${NAV.map((n) => navLink(n, n.key === active, 'side-link')).join('')}</nav>
      <div class="side-foot">
        <div class="class-chip"><span class="avatar sm">${esc(initials(state.me.displayName))}</span>
          <div><strong>${esc(state.me.displayName)}</strong><small>${esc(state.me.class.name)} · ${ROLE_LABEL[state.me.class.role]}</small></div></div>
        <button class="side-link" data-action="toggle-theme">${icon(dark ? 'sun' : 'moon')}<span>${dark ? 'Светлая тема' : 'Тёмная тема'}</span></button>
        <button class="side-link" data-action="logout">${icon('logout')}<span>Выйти</span></button>
      </div>
    </aside>
    <div class="main">
      <header class="topbar">
        ${page.back ? `<a class="icon-btn" href="${page.back}" aria-label="Назад">${icon('back')}</a>` : ''}
        <div class="topbar-title"><h1>${page.title}</h1>${page.subtitle ? `<p>${page.subtitle}</p>` : ''}</div>
        <div class="topbar-actions">
          <button class="icon-btn mobile-only" data-action="toggle-theme" aria-label="Сменить тему">${icon(dark ? 'sun' : 'moon')}</button>
          ${page.actions || ''}
        </div>
      </header>
      <main class="page${animate ? ' enter' : ''}" id="page">${page.html}</main>
    </div>
    <nav class="tabbar" aria-label="Нижнее меню">${bottomItems.map((n) => navLink(n, n.key === 'more' ? moreActive : n.key === active, 'tab')).join('')}</nav>
    <button class="fab" data-action="new-task" aria-label="Добавить задание">${icon('plus', 26)}</button>
  </div>`;
}

// ------------------------------------------------------------ главная

export function homeView() {
  const today = todayIso();
  const tomorrow = addDays(today, 1);
  const weekEnd = addDays(today, 6);
  const items = state.homework;
  const todayItems = items.filter((h) => h.dueDate === today);
  const soon = items.filter((h) => !h.done && h.dueDate > today && h.dueDate <= addDays(today, 7));
  const overdue = items.filter((h) => !h.done && h.dueDate < today);
  const nearest = items.find((h) => !h.done && h.dueDate >= today);
  const firstName = state.me.displayName.split(/\s+/)[0];

  const days = Array.from({ length: 7 }, (_, i) => addDays(today, i)).map((date) => {
    const list = items.filter((h) => h.dueDate === date);
    const left = list.filter((h) => !h.done).length;
    return `<button class="day-tile${date === today ? ' today' : ''}" data-action="go-date" data-date="${date}">
      <span class="dt-week">${date === today ? 'Сегодня' : formatWeekday(date)}</span>
      <span class="dt-num">${parseIso(date).getDate()}</span>
      <span class="dt-count${list.length ? '' : ' zero'}">${list.length ? (left ? `${left} из ${list.length}` : `${icon('check', 12)} все`) : '—'}</span>
    </button>`;
  }).join('');

  const counters = [
    ['today', 'Сегодня', todayItems.filter((h) => !h.done).length, 'clock'],
    ['tomorrow', 'Завтра', items.filter((h) => h.dueDate === tomorrow && !h.done).length, 'calendar'],
    ['week', 'На неделю', items.filter((h) => h.dueDate >= today && h.dueDate <= weekEnd && !h.done).length, 'list'],
    ['overdue', 'Просрочено', overdue.length, 'alert'],
  ].map(([filter, label, count, ic], i) => `<button class="counter card rise c-${filter}" style="--i:${i}" data-action="open-filter" data-value="${filter === 'overdue' ? 'todo' : filter}">
      <span class="counter-ico">${icon(ic, 18)}</span><strong>${count}</strong><span>${label}</span></button>`).join('');

  const deadline = nearest
    ? `<a class="deadline" href="#/task/${nearest.id}" style="--c:${subjectColor(nearest.subject)}">
        <span class="deadline-label">${icon('clock', 15)} Ближайший дедлайн</span>
        <strong>${esc(nearest.subject)}</strong>
        <span class="deadline-desc">${esc(truncate(nearest.description, 60))}</span>
        <span class="deadline-when">${relativeDay(nearest.dueDate, today)} · ${formatDayMonth(nearest.dueDate)}</span></a>`
    : `<div class="deadline"><span class="deadline-label">${icon('clock', 15)} Ближайший дедлайн</span>
        <strong>Ничего не горит</strong><span class="deadline-desc">Все задания сделаны или ещё не добавлены 🎉</span></div>`;

  const addBtn = '<button class="btn soft sm" data-action="new-task">+ Добавить задание</button>';
  const html = `
    <section class="hero rise">
      <div class="hero-text">
        <p class="eyebrow">${formatFull(today)}</p>
        <h2>Привет, ${esc(firstName)}! 👋</h2>
        <p class="lead">Вот домашние задания твоего класса <strong>${esc(state.me.class.name)}</strong></p>
      </div>
      ${deadline}
    </section>
    <section class="counters">${counters}</section>
    <section class="block">
      <div class="block-head"><h2>Ближайшие 7 дней</h2><a href="#/calendar" class="link">Календарь ${icon('right', 16)}</a></div>
      <div class="day-strip">${days}</div>
    </section>
    <section class="block">
      <div class="block-head"><h2>На сегодня <span class="count-pill">${todayItems.length}</span></h2></div>
      ${todayItems.length ? cards(todayItems) : emptyState('sparkles', 'На сегодня ничего не задано', 'Можно отдохнуть или заглянуть в задания на завтра.')}
    </section>
    <section class="block">
      <div class="block-head"><h2>Скоро сдавать <span class="count-pill">${soon.length}</span></h2><a href="#/tasks" class="link">Все задания ${icon('right', 16)}</a></div>
      ${soon.length ? cards(soon.slice(0, 8)) : emptyState('calendar', 'На неделю вперёд пусто', 'Если учитель что-то задал — добавь, и весь класс увидит.', addBtn)}
    </section>
    ${overdue.length ? `<section class="block">
      <div class="block-head"><h2 class="danger-text">Просроченные <span class="count-pill danger">${overdue.length}</span></h2></div>
      ${cards(overdue)}
    </section>` : ''}`;
  return { title: 'Главная', subtitle: `${countTasks(items.filter((h) => !h.done && h.dueDate >= today).length)} впереди`, html };
}

// ------------------------------------------------------------ список заданий

const FILTERS = [
  ['all', 'Все'], ['today', 'На сегодня'], ['tomorrow', 'На завтра'], ['week', 'На неделю'],
  ['todo', 'Невыполненные'], ['done', 'Выполненные'],
];

export function filteredTasks() {
  const today = todayIso();
  const { status, subject, query } = state.filters;
  const q = query.trim().toLowerCase();
  return state.homework.filter((h) => {
    if (subject && h.subject !== subject) return false;
    switch (status) {
      case 'today': if (h.dueDate !== today) return false; break;
      case 'tomorrow': if (h.dueDate !== addDays(today, 1)) return false; break;
      case 'week': if (h.dueDate < today || h.dueDate > addDays(today, 6)) return false; break;
      case 'todo': if (h.done) return false; break;
      case 'done': if (!h.done) return false; break;
      default: break;
    }
    if (!q) return true;
    return [h.subject, h.description, h.pages, h.comment, h.author.name].some((v) => (v || '').toLowerCase().includes(q));
  });
}

export function taskListHtml() {
  const list = filteredTasks();
  if (!list.length) {
    const searching = state.filters.query || state.filters.subject || state.filters.status !== 'all';
    return searching
      ? emptyState('search', 'Ничего не найдено', 'Попробуй другой фильтр или запрос.')
      : emptyState('book', 'Заданий пока нет', 'Добавь первое — его сразу увидит весь класс.', '<button class="btn primary" data-action="new-task">+ Добавить задание</button>');
  }
  const groups = new Map();
  for (const h of list) {
    if (!groups.has(h.dueDate)) groups.set(h.dueDate, []);
    groups.get(h.dueDate).push(h);
  }
  const today = todayIso();
  let index = 0;
  return `<p class="muted small result-count">Найдено: ${countTasks(list.length)}</p>` + [...groups.entries()].map(([date, items]) => `
    <section class="group">
      <h3 class="group-title">${formatFull(date)} <span class="muted">· ${relativeDay(date, today)}</span></h3>
      <div class="task-grid">${items.map((h) => taskCard(h, index++)).join('')}</div>
    </section>`).join('');
}

export function tasksView() {
  const subjects = [...new Set(state.homework.map((h) => h.subject))].sort((a, b) => a.localeCompare(b, 'ru'));
  const html = `
    <div class="toolbar card">
      <label class="search">${icon('search', 18)}
        <input id="task-search" type="search" placeholder="Поиск: предмет, задание, страница…" value="${esc(state.filters.query)}" data-input="search" aria-label="Поиск по заданиям">
      </label>
      <select class="input select" data-change="subject-filter" aria-label="Фильтр по предмету">
        <option value="">Все предметы</option>
        ${subjects.map((s) => `<option value="${esc(s)}"${s === state.filters.subject ? ' selected' : ''}>${esc(s)}</option>`).join('')}
      </select>
    </div>
    <div class="chips filters" role="group" aria-label="Фильтры">
      ${FILTERS.map(([value, label]) => `<button class="chip${state.filters.status === value ? ' active' : ''}" data-action="set-filter" data-value="${value}" aria-pressed="${state.filters.status === value}">${label}</button>`).join('')}
    </div>
    <div id="task-list">${taskListHtml()}</div>`;
  return { title: 'Все задания', subtitle: 'Общий список класса', html };
}

// ------------------------------------------------------------ календарь

function byDate() {
  const map = {};
  for (const h of state.homework) (map[h.dueDate] ||= []).push(h);
  return map;
}

function dayPanel(date, map) {
  const items = map[date] || [];
  return `<section class="block day-panel">
    <div class="block-head"><h2>${formatFull(date)} <span class="count-pill">${items.length}</span></h2>
      <button class="btn soft sm" data-action="new-task" data-date="${date}">${icon('plus', 16)} На этот день</button></div>
    ${items.length ? cards(items) : emptyState('calendar', 'В этот день ничего не задано')}
  </section>`;
}

function monthGrid(focus, map) {
  const today = todayIso();
  const first = new Date(parseIso(focus).getFullYear(), parseIso(focus).getMonth(), 1);
  const start = startOfWeek(isoOf(first));
  const month = first.getMonth();
  const head = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((d) => `<div class="cal-head">${d}</div>`).join('');
  const cells = Array.from({ length: 42 }, (_, i) => {
    const date = addDays(start, i);
    const d = parseIso(date);
    const items = map[date] || [];
    const cls = ['cal-cell'];
    if (d.getMonth() !== month) cls.push('other');
    if (date === today) cls.push('today');
    if (date === state.calendar.date) cls.push('selected');
    if (d.getDay() === 0 || d.getDay() === 6) cls.push('weekend');
    const pills = items.slice(0, 3).map((h) => `<i class="cal-pill${h.done ? ' done' : ''}" style="--c:${subjectColor(h.subject)}"><b>${esc(h.subject)}</b></i>`).join('');
    const label = `${formatFull(date)}: ${items.length ? countTasks(items.length) : 'нет заданий'}`;
    return `<button class="${cls.join(' ')}" data-action="cal-select" data-date="${date}" aria-label="${label}">
      <span class="cal-num">${d.getDate()}</span>
      ${items.length ? `<span class="cal-count">${items.length}</span>` : ''}
      <span class="cal-pills">${pills}${items.length > 3 ? `<i class="cal-more">+${items.length - 3}</i>` : ''}</span>
    </button>`;
  }).join('');
  return `<div class="cal-grid card">${head}${cells}</div>${dayPanel(state.calendar.date, map)}`;
}

function weekGrid(focus, map) {
  const start = startOfWeek(focus);
  const today = todayIso();
  const cols = Array.from({ length: 7 }, (_, i) => addDays(start, i)).map((date) => {
    const items = map[date] || [];
    return `<div class="week-col card${date === today ? ' today' : ''}${date === state.calendar.date ? ' selected' : ''}">
      <button class="week-head" data-action="cal-open-day" data-date="${date}">
        <span>${formatWeekday(date)}</span><strong>${parseIso(date).getDate()}</strong>
        ${items.length ? `<span class="count-pill">${items.length}</span>` : ''}
      </button>
      <div class="week-items">
        ${items.map((h) => `<a class="mini-task${h.done ? ' done' : ''}" href="#/task/${h.id}" style="--c:${subjectColor(h.subject)}">
          <b>${esc(h.subject)}</b><span>${esc(truncate(h.description, 60))}</span></a>`).join('') || '<p class="muted small week-empty">Свободно</p>'}
        <button class="week-add" data-action="new-task" data-date="${date}" aria-label="Добавить задание на ${formatDayMonth(date)}">${icon('plus', 16)}</button>
      </div>
    </div>`;
  }).join('');
  return `<div class="week-grid">${cols}</div>`;
}

export function calendarView() {
  const { view, date } = state.calendar;
  const map = byDate();
  let title;
  if (view === 'month') title = formatMonth(date);
  else if (view === 'week') {
    const start = startOfWeek(date);
    title = `${formatDayMonth(start)} — ${formatDayMonth(addDays(start, 6))}`;
  } else title = formatFull(date);

  const subjects = [...new Set(state.homework.map((h) => h.subject))];
  const body = view === 'month' ? monthGrid(date, map) : view === 'week' ? weekGrid(date, map) : dayPanel(date, map);
  const html = `
    <div class="cal-toolbar">
      <div class="cal-nav">
        <button class="icon-btn" data-action="cal-nav" data-dir="-1" aria-label="Назад">${icon('left')}</button>
        <h2 class="cal-title">${title}</h2>
        <button class="icon-btn" data-action="cal-nav" data-dir="1" aria-label="Вперёд">${icon('right')}</button>
        <button class="btn ghost sm" data-action="cal-today">Сегодня</button>
      </div>
      <div class="segmented small" role="group" aria-label="Вид календаря">
        ${[['day', 'День'], ['week', 'Неделя'], ['month', 'Месяц']].map(([v, l]) => `<button class="${view === v ? 'active' : ''}" data-action="cal-view" data-value="${v}" aria-pressed="${view === v}">${l}</button>`).join('')}
      </div>
    </div>
    ${body}
    ${subjects.length ? `<div class="legend">${subjects.map((s) => `<span class="legend-item" style="--c:${subjectColor(s)}"><i></i>${esc(s)}</span>`).join('')}</div>` : ''}`;
  return { title: 'Календарь', subtitle: 'Нажми на день, чтобы увидеть задания', html };
}

// ------------------------------------------------------------ уведомления

const KIND = {
  new: { icon: 'sparkles', label: 'Новое задание' },
  day_before: { icon: 'clock', label: 'Напоминание' },
  due_today: { icon: 'alert', label: 'Сдать сегодня' },
};

export function notificationsView() {
  const items = state.notifications;
  const me = state.me;
  const reminders = [me.remindDayBefore && 'за день до сдачи', me.remindOnDay && 'в день сдачи'].filter(Boolean);
  const html = `
    <div class="info-card card rise">
      <span class="info-ico">${icon('bell', 20)}</span>
      <div><strong>${reminders.length ? `Напоминания ${reminders.join(' и ')} в ${esc(me.reminderTime)}` : 'Напоминания выключены'}</strong>
      <p class="muted small">${state.pushSubscribed ? 'Push-уведомления на этом устройстве включены.' : 'Включи push-уведомления, чтобы получать их, даже когда сайт закрыт.'}</p></div>
      <a class="btn soft sm" href="#/profile">Настроить</a>
    </div>
    ${items.length ? `<div class="notice-list">${items.map((n, i) => `
      <article class="notice card rise${n.readAt ? '' : ' unread'} k-${n.kind}" style="--i:${Math.min(i, 12)}">
        <span class="notice-ico">${icon(KIND[n.kind]?.icon || 'bell', 18)}</span>
        <div class="notice-body">
          <p class="notice-kind">${KIND[n.kind]?.label || 'Уведомление'} · ${timeAgo(n.createdAt)}</p>
          <h3>${esc(n.title)}</h3>
          <p>${esc(n.body)}</p>
        </div>
        <div class="notice-actions">
          ${n.homeworkId ? `<button class="btn soft sm" data-action="open-notification" data-id="${n.id}" data-task="${n.homeworkId}">Открыть</button>` : ''}
          ${n.readAt ? '' : `<button class="icon-btn" data-action="mark-read" data-id="${n.id}" aria-label="Отметить прочитанным" title="Отметить прочитанным">${icon('check', 18)}</button>`}
        </div>
      </article>`).join('')}</div>`
    : emptyState('bell', 'Уведомлений пока нет', 'Здесь появятся новые задания одноклассников и напоминания о сдаче.')}`;
  const actions = state.unread ? '<button class="btn ghost sm" data-action="mark-all-read">Прочитать все</button>' : '';
  return { title: 'Уведомления', subtitle: state.unread ? `${state.unread} ${plural(state.unread, ['новое', 'новых', 'новых'])}` : 'Всё прочитано', html, actions };
}

// ------------------------------------------------------------ статистика

export function statsView() {
  const today = todayIso();
  const items = state.homework;
  const total = items.length;
  const done = items.filter((h) => h.done).length;
  const pct = total ? Math.round((done / total) * 100) : 0;
  const overdue = items.filter((h) => !h.done && h.dueDate < today).length;
  const upcoming = items.filter((h) => !h.done && h.dueDate >= today).length;
  const mine = items.filter((h) => h.author.id === state.me.id).length;
  const weekStart = startOfWeek(today);
  const thisWeek = items.filter((h) => h.dueDate >= weekStart && h.dueDate <= addDays(weekStart, 6));
  const weekDone = thisWeek.filter((h) => h.done).length;

  const subjects = {};
  const authors = {};
  for (const h of items) {
    const s = (subjects[h.subject] ||= { total: 0, done: 0 });
    s.total += 1;
    if (h.done) s.done += 1;
    authors[h.author.name] = (authors[h.author.name] || 0) + 1;
  }
  const subjectRows = Object.entries(subjects).sort((a, b) => b[1].total - a[1].total);
  const authorRows = Object.entries(authors).sort((a, b) => b[1] - a[1]).slice(0, 5);

  if (!total) {
    return { title: 'Статистика', html: emptyState('chart', 'Пока нечего считать', 'Статистика появится, когда в классе будут задания.') };
  }
  const html = `
    <section class="stats-hero card rise">
      <div class="ring" style="--p:${pct}"><div><strong>${pct}%</strong><span>выполнено</span></div></div>
      <div class="stats-hero-text">
        <h2>Ты выполнил(а) ${done} из ${countTasks(total)}</h2>
        <p class="muted">На этой неделе: ${weekDone} из ${thisWeek.length}. ${pct >= 80 ? 'Отличный результат! 🏆' : pct >= 50 ? 'Хороший темп, так держать! 💪' : 'Всё получится — начни с ближайшего дедлайна.'}</p>
      </div>
    </section>
    <section class="counters">
      <div class="counter card rise c-week" style="--i:0"><span class="counter-ico">${icon('list', 18)}</span><strong>${upcoming}</strong><span>Осталось сделать</span></div>
      <div class="counter card rise c-overdue" style="--i:1"><span class="counter-ico">${icon('alert', 18)}</span><strong>${overdue}</strong><span>Просрочено</span></div>
      <div class="counter card rise c-today" style="--i:2"><span class="counter-ico">${icon('check', 18)}</span><strong>${done}</strong><span>Выполнено</span></div>
      <div class="counter card rise c-tomorrow" style="--i:3"><span class="counter-ico">${icon('plus', 18)}</span><strong>${mine}</strong><span>Добавлено мной</span></div>
    </section>
    <div class="two-col">
      <section class="card rise">
        <h2 class="card-title">По предметам</h2>
        <div class="bars">${subjectRows.map(([name, s]) => `
          <div class="bar-row" style="--c:${subjectColor(name)}">
            <div class="bar-label"><span>${esc(name)}</span><span class="muted">${s.done}/${s.total}</span></div>
            <div class="bar"><i style="width:${Math.round((s.done / s.total) * 100)}%"></i></div>
          </div>`).join('')}</div>
      </section>
      <section class="card rise">
        <h2 class="card-title">Кто чаще добавляет задания</h2>
        <ol class="leaders">${authorRows.map(([name, count], i) => `
          <li><span class="avatar sm">${esc(initials(name))}</span><span class="leader-name">${esc(name)}</span><span class="count-pill">${count}</span>${i === 0 ? ' 🥇' : ''}</li>`).join('')}</ol>
      </section>
    </div>`;
  return { title: 'Статистика', subtitle: 'Твой прогресс по домашке', html };
}

// ------------------------------------------------------------ «Ещё», класс, профиль

export function moreView() {
  const dark = document.documentElement.dataset.theme === 'dark';
  const links = [
    ['#/stats', 'chart', 'Статистика', 'Сколько заданий выполнено'],
    ['#/class', 'users', 'Мой класс', 'Участники и код приглашения'],
    ['#/profile', 'user', 'Профиль и напоминания', 'Имя, время напоминаний, push'],
  ];
  const html = `<div class="menu-list card rise">
    ${links.map(([href, ic, title, sub]) => `<a class="menu-item" href="${href}"><span class="menu-ico">${icon(ic)}</span><span><strong>${title}</strong><small>${sub}</small></span>${icon('right', 18)}</a>`).join('')}
    <button class="menu-item" data-action="toggle-theme"><span class="menu-ico">${icon(dark ? 'sun' : 'moon')}</span><span><strong>${dark ? 'Светлая тема' : 'Тёмная тема'}</strong><small>Переключить оформление</small></span></button>
    <button class="menu-item danger" data-action="logout"><span class="menu-ico">${icon('logout')}</span><span><strong>Выйти</strong><small>${esc(state.me.username)}</small></span></button>
  </div>`;
  return { title: 'Ещё', html };
}

export function classView() {
  const cls = state.cls;
  if (!cls) return { title: 'Мой класс', html: '' };
  const isAdmin = state.me.class.role === 'admin';
  const members = cls.members.map((m) => {
    const self = m.id === state.me.id;
    const adminTools = isAdmin && !self ? `<div class="member-actions">
        <button class="btn ghost sm" data-action="set-role" data-id="${m.id}" data-value="${m.role === 'admin' ? 'member' : 'admin'}">${m.role === 'admin' ? 'Снять админа' : 'Сделать админом'}</button>
        <button class="icon-btn danger" data-action="remove-member" data-id="${m.id}" data-name="${esc(m.displayName)}" aria-label="Исключить ${esc(m.displayName)}">${icon('trash', 18)}</button>
      </div>` : '';
    return `<li class="member"><span class="avatar">${esc(initials(m.displayName))}</span>
      <div class="member-info"><strong>${esc(m.displayName)}${self ? ' <span class="muted">(это ты)</span>' : ''}</strong><small>@${esc(m.username)}</small></div>
      <span class="role-badge ${m.role}">${ROLE_LABEL[m.role]}</span>${adminTools}</li>`;
  }).join('');

  const html = `
    <div class="two-col">
      <section class="card rise invite">
        <h2 class="card-title">Код приглашения</h2>
        <p class="muted">Отправь его одноклассникам: при регистрации им нужно выбрать «Вступить по коду».</p>
        <div class="code-box"><span class="code">${esc(cls.inviteCode)}</span>
          <button class="btn soft sm" data-action="copy-code">${icon('copy', 16)} Скопировать</button></div>
        ${isAdmin ? '<button class="btn ghost sm" data-action="regen-code">Создать новый код</button><p class="muted small">Старый код перестанет работать.</p>' : ''}
      </section>
      <section class="card rise">
        <h2 class="card-title">Класс</h2>
        ${isAdmin ? `<form class="stack" data-form="rename-class" novalidate>
            <div class="field"><label for="class-name">Название</label>
            <input id="class-name" class="input" name="name" maxlength="60" required value="${esc(cls.name)}"></div>
            <p class="form-error" hidden></p>
            <button class="btn primary sm" type="submit">Сохранить название</button></form>`
          : `<p class="big-name">${esc(cls.name)}</p><p class="muted small">Название меняет администратор.</p>`}
        <p class="muted small">Ты — ${ROLE_LABEL[state.me.class.role].toLowerCase()}. ${isAdmin ? 'Ты можешь редактировать и удалять любые задания и управлять участниками.' : 'Ты можешь добавлять задания и редактировать свои.'}</p>
      </section>
    </div>
    <section class="card rise">
      <h2 class="card-title">Участники <span class="count-pill">${cls.members.length}</span></h2>
      <ul class="members">${members}</ul>
    </section>
    <section class="card rise danger-zone">
      <div><h2 class="card-title">Выйти из класса</h2>
      <p class="muted small">${cls.members.length === 1 ? 'Ты последний участник — класс и все задания будут удалены.' : 'Задания класса останутся у одноклассников.'}</p></div>
      <button class="btn danger sm" data-action="leave-class">Выйти из класса</button>
    </section>`;
  return { title: 'Мой класс', subtitle: `${esc(cls.name)} · ${cls.members.length} ${plural(cls.members.length, ['участник', 'участника', 'участников'])}`, html };
}

export function profileView() {
  const me = state.me;
  const theme = (() => { try { return localStorage.getItem('cm.theme') || 'system'; } catch { return 'system'; } })();
  const perm = notificationPermission();
  let pushBlock;
  if (!pushSupported()) {
    pushBlock = '<p class="muted small">Браузер не поддерживает push-уведомления на этой странице. Они работают в Chrome, Edge, Firefox и Safari (iOS 16.4+, если сайт добавлен на экран «Домой») при открытии сайта по HTTPS.</p>';
  } else if (state.pushSubscribed) {
    pushBlock = `<p class="status ok">${icon('check', 16)} Включены на этом устройстве</p>
      <div class="row-btns"><button class="btn soft sm" data-action="test-push">Отправить тестовое</button>
      <button class="btn ghost sm" data-action="disable-push">Выключить</button></div>`;
  } else {
    pushBlock = `<p class="muted small">${perm === 'denied' ? 'Уведомления запрещены в настройках браузера — разреши их для этого сайта.' : 'Уведомления будут приходить, даже если сайт закрыт.'}</p>
      <button class="btn primary sm" data-action="enable-push"${perm === 'denied' ? ' disabled' : ''}>${icon('bell', 16)} Включить уведомления</button>`;
  }
  const toggle = (key, title, sub) => `<label class="switch-row"><span><strong>${title}</strong><small>${sub}</small></span>
    <input type="checkbox" class="switch" data-change="pref" data-key="${key}"${me[key] ? ' checked' : ''}></label>`;

  const html = `
    <div class="two-col">
      <section class="card rise">
        <h2 class="card-title">${icon('bell', 18)} Напоминания</h2>
        <label class="switch-row"><span><strong>Время напоминаний</strong><small>Часовой пояс: ${esc(me.timezone)}</small></span>
          <input type="time" class="input time-input" value="${esc(me.reminderTime)}" data-change="pref" data-key="reminderTime"></label>
        ${toggle('remindDayBefore', 'За день до сдачи', '«Завтра сдавать: …»')}
        ${toggle('remindOnDay', 'В день сдачи', '«Сегодня сдавать: …»')}
        ${toggle('notifyNew', 'Новые задания', 'Когда одноклассник добавил задание')}
        <div class="push-box"><strong>Push-уведомления браузера</strong>${pushBlock}</div>
      </section>
      <section class="card rise">
        <h2 class="card-title">${icon('user', 18)} Профиль</h2>
        <form class="stack" data-form="profile" novalidate>
          <div class="field"><label for="p-name">Имя</label><input id="p-name" class="input" name="displayName" maxlength="40" required value="${esc(me.displayName)}"></div>
          <div class="field"><label>Логин</label><div class="input readonly">@${esc(me.username)}</div></div>
          <p class="form-error" hidden></p>
          <button class="btn primary sm" type="submit">Сохранить</button>
        </form>
        <h3 class="sub-title">Оформление</h3>
        <div class="segmented small" role="group" aria-label="Тема">
          ${[['light', 'Светлая'], ['dark', 'Тёмная'], ['system', 'Как в системе']].map(([v, l]) => `<button class="${theme === v ? 'active' : ''}" data-action="set-theme" data-value="${v}" aria-pressed="${theme === v}">${l}</button>`).join('')}
        </div>
      </section>
    </div>
    <div class="two-col">
      <section class="card rise">
        <h2 class="card-title">${icon('key', 18)} Сменить пароль</h2>
        <form class="stack" data-form="password" novalidate>
          <div class="field"><label for="p-cur">Текущий пароль</label><input id="p-cur" class="input" type="password" name="currentPassword" required autocomplete="current-password"></div>
          <div class="field"><label for="p-new">Новый пароль</label><input id="p-new" class="input" type="password" name="newPassword" minlength="6" required autocomplete="new-password"></div>
          <p class="form-error" hidden></p>
          <button class="btn soft sm" type="submit">Сменить пароль</button>
        </form>
      </section>
      <section class="card rise">
        <h2 class="card-title">${icon('logout', 18)} Аккаунт</h2>
        <p class="muted small">Ты вошёл как <strong>@${esc(me.username)}</strong>. Данные хранятся на сервере класса, пароль — только в зашифрованном виде.</p>
        <button class="btn ghost sm" data-action="logout">Выйти из аккаунта</button>
      </section>
    </div>`;
  return { title: 'Профиль', subtitle: 'Напоминания, уведомления и аккаунт', html };
}

// ------------------------------------------------------------ одно задание

export function detailView(id) {
  const h = state.homework.find((x) => x.id === id);
  if (!h) {
    return {
      title: 'Задание', back: '#/tasks',
      html: emptyState('alert', 'Задание не найдено', 'Возможно, его удалили.', '<a class="btn primary" href="#/tasks">К списку заданий</a>'),
    };
  }
  const today = todayIso();
  const overdue = !h.done && h.dueDate < today;
  const photos = h.attachments.map((a) => `<figure class="thumb">
      <a href="${a.url}" target="_blank" rel="noopener"><img src="${a.url}" alt="${esc(a.name)}" loading="lazy"></a>
      ${a.canDelete ? `<button class="thumb-del" data-action="delete-attachment" data-id="${a.id}" aria-label="Удалить фото">${icon('x', 16)}</button>` : ''}
    </figure>`).join('');
  const canAdd = h.attachments.length < 6;
  const html = `
    <article class="detail card rise" style="--c:${subjectColor(h.subject)}">
      <div class="task-top">
        <span class="subject-pill">${esc(h.subject)}</span>
        <span class="due-chip${overdue ? ' danger' : ''}">${esc(dueText(h, today))}</span>
      </div>
      <p class="detail-text">${esc(h.description)}</p>
      <dl class="facts">
        <div><dt>Сдать</dt><dd>${formatFull(h.dueDate)}</dd></div>
        <div><dt>Страница и упражнение</dt><dd>${h.pages ? esc(h.pages) : '—'}</dd></div>
        <div><dt>Кто добавил</dt><dd><span class="avatar xs">${esc(initials(h.author.name))}</span> ${esc(h.author.name)}</dd></div>
        <div><dt>Добавлено</dt><dd>${timeAgo(h.createdAt)}${h.updatedAt !== h.createdAt ? ` · изменено ${timeAgo(h.updatedAt)}` : ''}</dd></div>
      </dl>
      ${h.comment ? `<div class="comment"><strong>Комментарий</strong><p>${esc(h.comment)}</p></div>` : ''}
      <button class="btn lg block ${h.done ? 'success' : 'primary'}" data-action="toggle-done" data-id="${h.id}" aria-pressed="${h.done}">
        ${h.done ? `${icon('check', 18)} Выполнено — нажми, чтобы вернуть` : 'Отметить как выполненное'}</button>
      <section class="photos">
        <h3>Фото задания <span class="muted small">${h.attachments.length}/6</span></h3>
        <div class="gallery">${photos}
          ${canAdd ? `<label class="thumb add">${icon('upload', 22)}<span>Добавить фото</span>
            <input type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple hidden data-change="attach" data-id="${h.id}"></label>` : ''}
        </div>
      </section>
      <div class="detail-actions">
        <button class="btn soft" data-action="copy-task" data-id="${h.id}">${icon('copy', 16)} Копировать</button>
        ${h.canEdit ? `<button class="btn soft" data-action="edit-task" data-id="${h.id}">${icon('edit', 16)} Редактировать</button>
        <button class="btn danger-soft" data-action="delete-task" data-id="${h.id}">${icon('trash', 16)} Удалить</button>` : ''}
      </div>
    </article>`;
  return { title: esc(h.subject), subtitle: `Задание на ${formatDayMonth(h.dueDate)}`, back: '#/tasks', html };
}
