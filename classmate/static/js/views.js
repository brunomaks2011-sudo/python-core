// Bildschirme der App. Jede Funktion liefert HTML; Benutzertexte werden immer escaped.
import { state } from './store.js';
import { notificationPermission, pushSupported } from './push.js';
import {
  addDays, countTasks, days, esc, formatDayMonth, formatFull, formatMonth, formatShort, formatWeekday,
  icon, initials, isoOf, LOGO, parseIso, plural, relativeDay, startOfWeek, subjectColor,
  timeAgo, todayIso, truncate,
} from './util.js';

const ROLE_LABEL = { admin: 'Admin', member: 'Mitglied' };

// ------------------------------------------------------------ Bausteine

function emptyState(iconName, title, text = '', action = '') {
  return `<div class="empty rise">
    <div class="empty-icon">${icon(iconName, 28)}</div>
    <h3>${title}</h3>${text ? `<p>${text}</p>` : ''}${action}
  </div>`;
}

function dueText(h, today) {
  if (!h.done && h.dueDate < today) {
    const n = Math.round((parseIso(today) - parseIso(h.dueDate)) / 86400000);
    return `Seit ${days(n)} überfällig`;
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
        ${h.done ? `${icon('check', 16)} Erledigt` : 'Als erledigt markieren'}
      </button>
      <a class="btn sm ghost" href="#/task/${h.id}">Details</a>
    </div>
  </article>`;
}

const cards = (list) => `<div class="task-grid">${list.map((h, i) => taskCard(h, i)).join('')}</div>`;

// ------------------------------------------------------------ Anmeldung und Registrierung

export function authView(mode) {
  const isLogin = mode === 'login';
  return `<div class="auth">
    <div class="auth-card card rise">
      <div class="auth-brand">${LOGO}<div><h1>ClassMate</h1><p>Die Hausaufgaben der ganzen Klasse an einem Ort</p></div></div>
      <div class="segmented" role="tablist">
        <a href="#/login" class="${isLogin ? 'active' : ''}" role="tab" aria-selected="${isLogin}">Anmelden</a>
        <a href="#/register" class="${!isLogin ? 'active' : ''}" role="tab" aria-selected="${!isLogin}">Registrieren</a>
      </div>
      <form class="stack" data-form="${isLogin ? 'login' : 'register'}" novalidate>
        ${isLogin ? '' : `<div class="field"><label for="f-name">Wie heißt du?</label>
          <input id="f-name" class="input" name="displayName" maxlength="40" required placeholder="z. B. Lena Schmidt" autocomplete="name"></div>`}
        <div class="field"><label for="f-login">Benutzername</label>
          <input id="f-login" class="input" name="username" maxlength="32" required placeholder="lena_7b" autocomplete="username" autocapitalize="off" spellcheck="false">
          ${isLogin ? '' : '<small class="hint">Lateinische Buchstaben, Ziffern, Punkt oder „_“, mindestens 3 Zeichen</small>'}</div>
        <div class="field"><label for="f-pass">Passwort</label>
          <input id="f-pass" class="input" type="password" name="password" minlength="6" required autocomplete="${isLogin ? 'current-password' : 'new-password'}" placeholder="Mindestens 6 Zeichen"></div>
        <p class="form-error" hidden></p>
        <button class="btn primary lg block" type="submit">${isLogin ? 'Anmelden' : 'Konto erstellen'}</button>
      </form>
    </div>
  </div>`;
}

export function setupView() {
  return `<div class="auth">
    <div class="setup rise">
      <div class="auth-brand">${LOGO}<div><h1>Hallo, ${esc(state.me.displayName)}!</h1><p>Jetzt nur noch deiner Klasse beitreten</p></div></div>
      <div class="setup-grid">
        <form class="card stack" data-form="join-class" novalidate>
          <div class="setup-icon">${icon('key', 24)}</div>
          <h2>Mit Code beitreten</h2>
          <p class="muted">Frag eine Mitschülerin, einen Mitschüler oder den Admin deiner Klasse nach dem Code.</p>
          <input class="input code-input" name="code" maxlength="12" required placeholder="z. B. K7M2QX" autocomplete="off" autocapitalize="characters">
          <p class="form-error" hidden></p>
          <button class="btn primary block" type="submit">Klasse beitreten</button>
        </form>
        <form class="card stack" data-form="create-class" novalidate>
          <div class="setup-icon">${icon('sparkles', 24)}</div>
          <h2>Klasse erstellen</h2>
          <p class="muted">Du wirst Admin und bekommst einen Einladungscode für alle anderen.</p>
          <input class="input" name="name" maxlength="60" required placeholder="z. B. Klasse 7b">
          <p class="form-error" hidden></p>
          <button class="btn soft block" type="submit">Klasse erstellen</button>
        </form>
      </div>
      <button class="btn ghost" data-action="logout">${icon('logout', 16)} Abmelden</button>
    </div>
  </div>`;
}

// ------------------------------------------------------------ Rahmen

const NAV = [
  { key: 'home', href: '#/', label: 'Start', icon: 'home' },
  { key: 'tasks', href: '#/tasks', label: 'Aufgaben', icon: 'list' },
  { key: 'calendar', href: '#/calendar', label: 'Kalender', icon: 'calendar' },
  { key: 'stats', href: '#/stats', label: 'Statistik', icon: 'chart' },
  { key: 'notifications', href: '#/notifications', label: 'Mitteilungen', icon: 'bell' },
  { key: 'class', href: '#/class', label: 'Meine Klasse', icon: 'users' },
  { key: 'profile', href: '#/profile', label: 'Profil', icon: 'user' },
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
    ? { key: 'more', href: '#/more', label: 'Mehr', icon: 'more' }
    : NAV.find((n) => n.key === key)));
  const dark = document.documentElement.dataset.theme === 'dark';

  return `<div class="shell">
    <aside class="sidebar">
      <a class="brand" href="#/">${LOGO}<span>ClassMate</span></a>
      <button class="btn primary block side-add" data-action="new-task">${icon('plus', 18)} Aufgabe hinzufügen</button>
      <nav class="side-nav" aria-label="Hauptmenü">${NAV.map((n) => navLink(n, n.key === active, 'side-link')).join('')}</nav>
      <div class="side-foot">
        <div class="class-chip"><span class="avatar sm">${esc(initials(state.me.displayName))}</span>
          <div><strong>${esc(state.me.displayName)}</strong><small>${esc(state.me.class.name)} · ${ROLE_LABEL[state.me.class.role]}</small></div></div>
        <button class="side-link" data-action="toggle-theme">${icon(dark ? 'sun' : 'moon')}<span>${dark ? 'Helles Design' : 'Dunkles Design'}</span></button>
        <button class="side-link" data-action="logout">${icon('logout')}<span>Abmelden</span></button>
      </div>
    </aside>
    <div class="main">
      <header class="topbar">
        ${page.back ? `<a class="icon-btn" href="${page.back}" aria-label="Zurück">${icon('back')}</a>` : ''}
        <div class="topbar-title"><h1>${page.title}</h1>${page.subtitle ? `<p>${page.subtitle}</p>` : ''}</div>
        <div class="topbar-actions">
          <button class="icon-btn mobile-only" data-action="toggle-theme" aria-label="Design wechseln">${icon(dark ? 'sun' : 'moon')}</button>
          ${page.actions || ''}
        </div>
      </header>
      <main class="page${animate ? ' enter' : ''}" id="page">${page.html}</main>
    </div>
    <nav class="tabbar" aria-label="Untere Navigation">${bottomItems.map((n) => navLink(n, n.key === 'more' ? moreActive : n.key === active, 'tab')).join('')}</nav>
    <button class="fab" data-action="new-task" aria-label="Aufgabe hinzufügen">${icon('plus', 26)}</button>
  </div>`;
}

// ------------------------------------------------------------ Startseite

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

  const strip = Array.from({ length: 7 }, (_, i) => addDays(today, i)).map((date) => {
    const list = items.filter((h) => h.dueDate === date);
    const left = list.filter((h) => !h.done).length;
    return `<button class="day-tile${date === today ? ' today' : ''}" data-action="go-date" data-date="${date}">
      <span class="dt-week">${date === today ? 'Heute' : formatWeekday(date)}</span>
      <span class="dt-num">${parseIso(date).getDate()}</span>
      <span class="dt-count${list.length ? '' : ' zero'}">${list.length ? (left ? `${left} von ${list.length}` : `${icon('check', 12)} alle`) : '—'}</span>
    </button>`;
  }).join('');

  const counters = [
    ['today', 'Heute', todayItems.filter((h) => !h.done).length, 'clock'],
    ['tomorrow', 'Morgen', items.filter((h) => h.dueDate === tomorrow && !h.done).length, 'calendar'],
    ['week', 'Diese Woche', items.filter((h) => h.dueDate >= today && h.dueDate <= weekEnd && !h.done).length, 'list'],
    ['overdue', 'Überfällig', overdue.length, 'alert'],
  ].map(([filter, label, count, ic], i) => `<button class="counter card rise c-${filter}" style="--i:${i}" data-action="open-filter" data-value="${filter === 'overdue' ? 'todo' : filter}">
      <span class="counter-ico">${icon(ic, 18)}</span><strong>${count}</strong><span>${label}</span></button>`).join('');

  const deadline = nearest
    ? `<a class="deadline" href="#/task/${nearest.id}" style="--c:${subjectColor(nearest.subject)}">
        <span class="deadline-label">${icon('clock', 15)} Nächste Abgabe</span>
        <strong>${esc(nearest.subject)}</strong>
        <span class="deadline-desc">${esc(truncate(nearest.description, 60))}</span>
        <span class="deadline-when">${relativeDay(nearest.dueDate, today)} · ${formatDayMonth(nearest.dueDate)}</span></a>`
    : `<div class="deadline"><span class="deadline-label">${icon('clock', 15)} Nächste Abgabe</span>
        <strong>Nichts Dringendes</strong><span class="deadline-desc">Alles erledigt oder noch nichts eingetragen 🎉</span></div>`;

  const addBtn = '<button class="btn soft sm" data-action="new-task">+ Aufgabe hinzufügen</button>';
  const openCount = items.filter((h) => !h.done && h.dueDate >= today).length;
  const html = `
    <section class="hero rise">
      <div class="hero-text">
        <p class="eyebrow">${formatFull(today)} · ${esc(state.me.class.name)}</p>
        <h2>Hallo, ${esc(firstName)}! 👋</h2>
        <p class="lead">Hier sind die Hausaufgaben deiner Klasse.</p>
      </div>
      ${deadline}
    </section>
    <section class="counters">${counters}</section>
    <section class="block">
      <div class="block-head"><h2>Die nächsten 7 Tage</h2><a href="#/calendar" class="link">Kalender ${icon('right', 16)}</a></div>
      <div class="day-strip">${strip}</div>
    </section>
    <section class="block">
      <div class="block-head"><h2>Für heute <span class="count-pill">${todayItems.length}</span></h2></div>
      ${todayItems.length ? cards(todayItems) : emptyState('sparkles', 'Für heute ist nichts aufgegeben', 'Zeit zum Ausruhen – oder schau dir schon die Aufgaben für morgen an.')}
    </section>
    <section class="block">
      <div class="block-head"><h2>Bald fällig <span class="count-pill">${soon.length}</span></h2><a href="#/tasks" class="link">Alle Aufgaben ${icon('right', 16)}</a></div>
      ${soon.length ? cards(soon.slice(0, 8)) : emptyState('calendar', 'Die nächste Woche ist frei', 'Wenn eine Lehrkraft etwas aufgibt, trag es ein – die ganze Klasse sieht es sofort.', addBtn)}
    </section>
    ${overdue.length ? `<section class="block">
      <div class="block-head"><h2 class="danger-text">Überfällig <span class="count-pill danger">${overdue.length}</span></h2></div>
      ${cards(overdue)}
    </section>` : ''}`;
  return { title: 'Start', subtitle: `${countTasks(openCount)} ${openCount === 1 ? 'steht' : 'stehen'} an`, html };
}

// ------------------------------------------------------------ Aufgabenliste

const FILTERS = [
  ['all', 'Alle'], ['today', 'Heute'], ['tomorrow', 'Morgen'], ['week', 'Diese Woche'],
  ['todo', 'Offen'], ['done', 'Erledigt'],
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
      ? emptyState('search', 'Nichts gefunden', 'Probier einen anderen Filter oder Suchbegriff.')
      : emptyState('book', 'Noch keine Aufgaben', 'Trag die erste ein – die ganze Klasse sieht sie sofort.', '<button class="btn primary" data-action="new-task">+ Aufgabe hinzufügen</button>');
  }
  const groups = new Map();
  for (const h of list) {
    if (!groups.has(h.dueDate)) groups.set(h.dueDate, []);
    groups.get(h.dueDate).push(h);
  }
  const today = todayIso();
  let index = 0;
  return `<p class="muted small result-count">Gefunden: ${countTasks(list.length)}</p>` + [...groups.entries()].map(([date, items]) => `
    <section class="group">
      <h3 class="group-title">${formatFull(date)} <span class="muted">· ${relativeDay(date, today)}</span></h3>
      <div class="task-grid">${items.map((h) => taskCard(h, index++)).join('')}</div>
    </section>`).join('');
}

export function tasksView() {
  const subjects = [...new Set(state.homework.map((h) => h.subject))].sort((a, b) => a.localeCompare(b, 'de'));
  const html = `
    <div class="toolbar card">
      <label class="search">${icon('search', 18)}
        <input id="task-search" type="search" placeholder="Suche: Fach, Aufgabe, Seite …" value="${esc(state.filters.query)}" data-input="search" aria-label="Aufgaben durchsuchen">
      </label>
      <select class="input select" data-change="subject-filter" aria-label="Nach Fach filtern">
        <option value="">Alle Fächer</option>
        ${subjects.map((s) => `<option value="${esc(s)}"${s === state.filters.subject ? ' selected' : ''}>${esc(s)}</option>`).join('')}
      </select>
    </div>
    <div class="chips filters" role="group" aria-label="Filter">
      ${FILTERS.map(([value, label]) => `<button class="chip${state.filters.status === value ? ' active' : ''}" data-action="set-filter" data-value="${value}" aria-pressed="${state.filters.status === value}">${label}</button>`).join('')}
    </div>
    <div id="task-list">${taskListHtml()}</div>`;
  return { title: 'Alle Aufgaben', subtitle: 'Gemeinsame Liste der Klasse', html };
}

// ------------------------------------------------------------ Kalender

function byDate() {
  const map = {};
  for (const h of state.homework) (map[h.dueDate] ||= []).push(h);
  return map;
}

function dayPanel(date, map) {
  const items = map[date] || [];
  return `<section class="block day-panel">
    <div class="block-head"><h2>${formatFull(date)} <span class="count-pill">${items.length}</span></h2>
      <button class="btn soft sm" data-action="new-task" data-date="${date}">${icon('plus', 16)} Für diesen Tag</button></div>
    ${items.length ? cards(items) : emptyState('calendar', 'An diesem Tag ist nichts fällig')}
  </section>`;
}

function monthGrid(focus, map) {
  const today = todayIso();
  const first = new Date(parseIso(focus).getFullYear(), parseIso(focus).getMonth(), 1);
  const start = startOfWeek(isoOf(first));
  const month = first.getMonth();
  const head = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'].map((d) => `<div class="cal-head">${d}</div>`).join('');
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
    const label = `${formatFull(date)}: ${items.length ? countTasks(items.length) : 'keine Aufgaben'}`;
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
          <b>${esc(h.subject)}</b><span>${esc(truncate(h.description, 60))}</span></a>`).join('') || '<p class="muted small week-empty">Frei</p>'}
        <button class="week-add" data-action="new-task" data-date="${date}" aria-label="Aufgabe für ${formatDayMonth(date)} hinzufügen">${icon('plus', 16)}</button>
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
    title = `${formatDayMonth(start)} – ${formatDayMonth(addDays(start, 6))}`;
  } else title = formatFull(date);

  const subjects = [...new Set(state.homework.map((h) => h.subject))];
  const body = view === 'month' ? monthGrid(date, map) : view === 'week' ? weekGrid(date, map) : dayPanel(date, map);
  const html = `
    <div class="cal-toolbar">
      <div class="cal-nav">
        <button class="icon-btn" data-action="cal-nav" data-dir="-1" aria-label="Zurück">${icon('left')}</button>
        <h2 class="cal-title">${title}</h2>
        <button class="icon-btn" data-action="cal-nav" data-dir="1" aria-label="Weiter">${icon('right')}</button>
        <button class="btn ghost sm" data-action="cal-today">Heute</button>
      </div>
      <div class="segmented small" role="group" aria-label="Kalenderansicht">
        ${[['day', 'Tag'], ['week', 'Woche'], ['month', 'Monat']].map(([v, l]) => `<button class="${view === v ? 'active' : ''}" data-action="cal-view" data-value="${v}" aria-pressed="${view === v}">${l}</button>`).join('')}
      </div>
    </div>
    ${body}
    ${subjects.length ? `<div class="legend">${subjects.map((s) => `<span class="legend-item" style="--c:${subjectColor(s)}"><i></i>${esc(s)}</span>`).join('')}</div>` : ''}`;
  return { title: 'Kalender', subtitle: 'Tippe auf einen Tag, um die Aufgaben zu sehen', html };
}

// ------------------------------------------------------------ Mitteilungen

const KIND = {
  new: { icon: 'sparkles', label: 'Neue Aufgabe' },
  day_before: { icon: 'clock', label: 'Erinnerung' },
  due_today: { icon: 'alert', label: 'Heute fällig' },
};

export function notificationsView() {
  const items = state.notifications;
  const me = state.me;
  const reminders = [me.remindDayBefore && 'am Vortag', me.remindOnDay && 'am Abgabetag'].filter(Boolean);
  const html = `
    <div class="info-card card rise">
      <span class="info-ico">${icon('bell', 20)}</span>
      <div><strong>${reminders.length ? `Erinnerungen ${reminders.join(' und ')} um ${esc(me.reminderTime)} Uhr` : 'Erinnerungen sind ausgeschaltet'}</strong>
      <p class="muted small">${state.pushSubscribed ? 'Push-Mitteilungen sind auf diesem Gerät aktiv.' : 'Aktiviere Push-Mitteilungen, um sie auch bei geschlossener Seite zu bekommen.'}</p></div>
      <a class="btn soft sm" href="#/profile">Einstellen</a>
    </div>
    ${items.length ? `<div class="notice-list">${items.map((n, i) => `
      <article class="notice card rise${n.readAt ? '' : ' unread'} k-${n.kind}" style="--i:${Math.min(i, 12)}">
        <span class="notice-ico">${icon(KIND[n.kind]?.icon || 'bell', 18)}</span>
        <div class="notice-body">
          <p class="notice-kind">${KIND[n.kind]?.label || 'Mitteilung'} · ${timeAgo(n.createdAt)}</p>
          <h3>${esc(n.title)}</h3>
          <p>${esc(n.body)}</p>
        </div>
        <div class="notice-actions">
          ${n.homeworkId ? `<button class="btn soft sm" data-action="open-notification" data-id="${n.id}" data-task="${n.homeworkId}">Öffnen</button>` : ''}
          ${n.readAt ? '' : `<button class="icon-btn" data-action="mark-read" data-id="${n.id}" aria-label="Als gelesen markieren" title="Als gelesen markieren">${icon('check', 18)}</button>`}
        </div>
      </article>`).join('')}</div>`
    : emptyState('bell', 'Noch keine Mitteilungen', 'Hier erscheinen neue Aufgaben deiner Klasse und Erinnerungen an Abgaben.')}`;
  const actions = state.unread ? '<button class="btn ghost sm" data-action="mark-all-read">Alle gelesen</button>' : '';
  return { title: 'Mitteilungen', subtitle: state.unread ? `${state.unread} ungelesen` : 'Alles gelesen', html, actions };
}

// ------------------------------------------------------------ Statistik

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
    return { title: 'Statistik', html: emptyState('chart', 'Noch nichts zu zählen', 'Die Statistik erscheint, sobald es Aufgaben in der Klasse gibt.') };
  }
  const html = `
    <section class="stats-hero card rise">
      <div class="ring" style="--p:${pct}"><div><strong>${pct}%</strong><span>erledigt</span></div></div>
      <div class="stats-hero-text">
        <h2>Du hast ${done} von ${countTasks(total)} erledigt</h2>
        <p class="muted">Diese Woche: ${weekDone} von ${thisWeek.length}. ${pct >= 80 ? 'Super Ergebnis! 🏆' : pct >= 50 ? 'Gutes Tempo, weiter so! 💪' : 'Du schaffst das – fang mit der nächsten Abgabe an.'}</p>
      </div>
    </section>
    <section class="counters">
      <div class="counter card rise c-week" style="--i:0"><span class="counter-ico">${icon('list', 18)}</span><strong>${upcoming}</strong><span>Noch zu erledigen</span></div>
      <div class="counter card rise c-overdue" style="--i:1"><span class="counter-ico">${icon('alert', 18)}</span><strong>${overdue}</strong><span>Überfällig</span></div>
      <div class="counter card rise c-today" style="--i:2"><span class="counter-ico">${icon('check', 18)}</span><strong>${done}</strong><span>Erledigt</span></div>
      <div class="counter card rise c-tomorrow" style="--i:3"><span class="counter-ico">${icon('plus', 18)}</span><strong>${mine}</strong><span>Von mir eingetragen</span></div>
    </section>
    <div class="two-col">
      <section class="card rise">
        <h2 class="card-title">Nach Fächern</h2>
        <div class="bars">${subjectRows.map(([name, s]) => `
          <div class="bar-row" style="--c:${subjectColor(name)}">
            <div class="bar-label"><span>${esc(name)}</span><span class="muted">${s.done}/${s.total}</span></div>
            <div class="bar"><i style="width:${Math.round((s.done / s.total) * 100)}%"></i></div>
          </div>`).join('')}</div>
      </section>
      <section class="card rise">
        <h2 class="card-title">Wer trägt am meisten ein?</h2>
        <ol class="leaders">${authorRows.map(([name, count], i) => `
          <li><span class="avatar sm">${esc(initials(name))}</span><span class="leader-name">${esc(name)}</span><span class="count-pill">${count}</span>${i === 0 ? ' 🥇' : ''}</li>`).join('')}</ol>
      </section>
    </div>`;
  return { title: 'Statistik', subtitle: 'Dein Fortschritt bei den Hausaufgaben', html };
}

// ------------------------------------------------------------ Mehr, Klasse, Profil

export function moreView() {
  const dark = document.documentElement.dataset.theme === 'dark';
  const links = [
    ['#/stats', 'chart', 'Statistik', 'Wie viele Aufgaben erledigt sind'],
    ['#/class', 'users', 'Meine Klasse', 'Mitglieder und Einladungscode'],
    ['#/profile', 'user', 'Profil und Erinnerungen', 'Name, Erinnerungszeit, Push'],
  ];
  const html = `<div class="menu-list card rise">
    ${links.map(([href, ic, title, sub]) => `<a class="menu-item" href="${href}"><span class="menu-ico">${icon(ic)}</span><span><strong>${title}</strong><small>${sub}</small></span>${icon('right', 18)}</a>`).join('')}
    <button class="menu-item" data-action="toggle-theme"><span class="menu-ico">${icon(dark ? 'sun' : 'moon')}</span><span><strong>${dark ? 'Helles Design' : 'Dunkles Design'}</strong><small>Darstellung wechseln</small></span></button>
    <button class="menu-item danger" data-action="logout"><span class="menu-ico">${icon('logout')}</span><span><strong>Abmelden</strong><small>@${esc(state.me.username)}</small></span></button>
  </div>`;
  return { title: 'Mehr', html };
}

export function classView() {
  const cls = state.cls;
  if (!cls) return { title: 'Meine Klasse', html: '' };
  const isAdmin = state.me.class.role === 'admin';
  const members = cls.members.map((m) => {
    const self = m.id === state.me.id;
    const adminTools = isAdmin && !self ? `<div class="member-actions">
        <button class="btn ghost sm" data-action="set-role" data-id="${m.id}" data-value="${m.role === 'admin' ? 'member' : 'admin'}">${m.role === 'admin' ? 'Admin entfernen' : 'Zum Admin machen'}</button>
        <button class="icon-btn danger" data-action="remove-member" data-id="${m.id}" data-name="${esc(m.displayName)}" aria-label="${esc(m.displayName)} entfernen">${icon('trash', 18)}</button>
      </div>` : '';
    return `<li class="member"><span class="avatar">${esc(initials(m.displayName))}</span>
      <div class="member-info"><strong>${esc(m.displayName)}${self ? ' <span class="muted">(du)</span>' : ''}</strong><small>@${esc(m.username)}</small></div>
      <span class="role-badge ${m.role}">${ROLE_LABEL[m.role]}</span>${adminTools}</li>`;
  }).join('');

  const html = `
    <div class="two-col">
      <section class="card rise invite">
        <h2 class="card-title">Einladungscode</h2>
        <p class="muted">Schick ihn deinen Mitschülerinnen und Mitschülern: Nach der Registrierung wählen sie „Mit Code beitreten“.</p>
        <div class="code-box"><span class="code">${esc(cls.inviteCode)}</span>
          <button class="btn soft sm" data-action="copy-code">${icon('copy', 16)} Kopieren</button></div>
        ${isAdmin ? '<button class="btn ghost sm" data-action="regen-code">Neuen Code erstellen</button><p class="muted small">Der alte Code funktioniert dann nicht mehr.</p>' : ''}
      </section>
      <section class="card rise">
        <h2 class="card-title">Klasse</h2>
        ${isAdmin ? `<form class="stack" data-form="rename-class" novalidate>
            <div class="field"><label for="class-name">Name</label>
            <input id="class-name" class="input" name="name" maxlength="60" required value="${esc(cls.name)}"></div>
            <p class="form-error" hidden></p>
            <button class="btn primary sm" type="submit">Namen speichern</button></form>`
          : `<p class="big-name">${esc(cls.name)}</p><p class="muted small">Den Namen ändert der Admin.</p>`}
        <p class="muted small">${isAdmin ? 'Du bist Admin: Du kannst alle Aufgaben bearbeiten und löschen und Mitglieder verwalten.' : 'Du bist Mitglied: Du kannst Aufgaben eintragen und deine eigenen bearbeiten.'}</p>
      </section>
    </div>
    <section class="card rise">
      <h2 class="card-title">Mitglieder <span class="count-pill">${cls.members.length}</span></h2>
      <ul class="members">${members}</ul>
    </section>
    <section class="card rise danger-zone">
      <div><h2 class="card-title">Klasse verlassen</h2>
      <p class="muted small">${cls.members.length === 1 ? 'Du bist das letzte Mitglied – die Klasse und alle Aufgaben werden gelöscht.' : 'Die Aufgaben bleiben für deine Klasse erhalten.'}</p></div>
      <button class="btn danger sm" data-action="leave-class">Klasse verlassen</button>
    </section>`;
  return { title: 'Meine Klasse', subtitle: `${esc(cls.name)} · ${cls.members.length} ${plural(cls.members.length, 'Mitglied', 'Mitglieder')}`, html };
}

export function profileView() {
  const me = state.me;
  const theme = (() => { try { return localStorage.getItem('cm.theme') || 'system'; } catch { return 'system'; } })();
  const perm = notificationPermission();
  let pushBlock;
  if (!pushSupported()) {
    pushBlock = '<p class="muted small">Dieser Browser unterstützt hier keine Push-Mitteilungen. Sie funktionieren in Chrome, Edge, Firefox und Safari (iOS 16.4+, wenn die Seite zum Home-Bildschirm hinzugefügt wurde), sobald die Seite über HTTPS geöffnet wird.</p>';
  } else if (state.pushSubscribed) {
    pushBlock = `<p class="status ok">${icon('check', 16)} Auf diesem Gerät aktiv</p>
      <div class="row-btns"><button class="btn soft sm" data-action="test-push">Test senden</button>
      <button class="btn ghost sm" data-action="disable-push">Ausschalten</button></div>`;
  } else {
    pushBlock = `<p class="muted small">${perm === 'denied' ? 'Mitteilungen sind in den Browser-Einstellungen blockiert – erlaube sie für diese Seite.' : 'Mitteilungen kommen auch dann an, wenn die Seite geschlossen ist.'}</p>
      <button class="btn primary sm" data-action="enable-push"${perm === 'denied' ? ' disabled' : ''}>${icon('bell', 16)} Mitteilungen aktivieren</button>`;
  }
  const toggle = (key, title, sub) => `<label class="switch-row"><span><strong>${title}</strong><small>${sub}</small></span>
    <input type="checkbox" class="switch" data-change="pref" data-key="${key}"${me[key] ? ' checked' : ''}></label>`;

  const html = `
    <div class="two-col">
      <section class="card rise">
        <h2 class="card-title">${icon('bell', 18)} Erinnerungen</h2>
        <label class="switch-row"><span><strong>Uhrzeit der Erinnerung</strong><small>Zeitzone: ${esc(me.timezone)}</small></span>
          <input type="time" class="input time-input" value="${esc(me.reminderTime)}" data-change="pref" data-key="reminderTime"></label>
        ${toggle('remindDayBefore', 'Am Tag vor der Abgabe', '„Morgen fällig: …“')}
        ${toggle('remindOnDay', 'Am Abgabetag', '„Heute fällig: …“')}
        ${toggle('notifyNew', 'Neue Aufgaben', 'Wenn jemand aus der Klasse eine Aufgabe einträgt')}
        <div class="push-box"><strong>Push-Mitteilungen im Browser</strong>${pushBlock}</div>
      </section>
      <section class="card rise">
        <h2 class="card-title">${icon('user', 18)} Profil</h2>
        <form class="stack" data-form="profile" novalidate>
          <div class="field"><label for="p-name">Name</label><input id="p-name" class="input" name="displayName" maxlength="40" required value="${esc(me.displayName)}"></div>
          <div class="field"><label>Benutzername</label><div class="input readonly">@${esc(me.username)}</div></div>
          <p class="form-error" hidden></p>
          <button class="btn primary sm" type="submit">Speichern</button>
        </form>
        <h3 class="sub-title">Design</h3>
        <div class="segmented small" role="group" aria-label="Design">
          ${[['light', 'Hell'], ['dark', 'Dunkel'], ['system', 'Wie System']].map(([v, l]) => `<button class="${theme === v ? 'active' : ''}" data-action="set-theme" data-value="${v}" aria-pressed="${theme === v}">${l}</button>`).join('')}
        </div>
      </section>
    </div>
    <div class="two-col">
      <section class="card rise">
        <h2 class="card-title">${icon('key', 18)} Passwort ändern</h2>
        <form class="stack" data-form="password" novalidate>
          <div class="field"><label for="p-cur">Aktuelles Passwort</label><input id="p-cur" class="input" type="password" name="currentPassword" required autocomplete="current-password"></div>
          <div class="field"><label for="p-new">Neues Passwort</label><input id="p-new" class="input" type="password" name="newPassword" minlength="6" required autocomplete="new-password"></div>
          <p class="form-error" hidden></p>
          <button class="btn soft sm" type="submit">Passwort ändern</button>
        </form>
      </section>
      <section class="card rise">
        <h2 class="card-title">${icon('logout', 18)} Konto</h2>
        <p class="muted small">Angemeldet als <strong>@${esc(me.username)}</strong>. Die Daten liegen auf dem Server der Klasse, dein Passwort nur verschlüsselt.</p>
        <button class="btn ghost sm" data-action="logout">Abmelden</button>
      </section>
    </div>`;
  return { title: 'Profil', subtitle: 'Erinnerungen, Mitteilungen und Konto', html };
}

// ------------------------------------------------------------ Einzelne Aufgabe

export function detailView(id) {
  const h = state.homework.find((x) => x.id === id);
  if (!h) {
    return {
      title: 'Aufgabe', back: '#/tasks',
      html: emptyState('alert', 'Aufgabe nicht gefunden', 'Vielleicht wurde sie gelöscht.', '<a class="btn primary" href="#/tasks">Zur Aufgabenliste</a>'),
    };
  }
  const today = todayIso();
  const overdue = !h.done && h.dueDate < today;
  const photos = h.attachments.map((a) => `<figure class="thumb">
      <a href="${a.url}" target="_blank" rel="noopener"><img src="${a.url}" alt="${esc(a.name)}" loading="lazy"></a>
      ${a.canDelete ? `<button class="thumb-del" data-action="delete-attachment" data-id="${a.id}" aria-label="Foto löschen">${icon('x', 16)}</button>` : ''}
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
        <div><dt>Abgabe</dt><dd>${formatFull(h.dueDate)}</dd></div>
        <div><dt>Seite und Übung</dt><dd>${h.pages ? esc(h.pages) : '—'}</dd></div>
        <div><dt>Eingetragen von</dt><dd><span class="avatar xs">${esc(initials(h.author.name))}</span> ${esc(h.author.name)}</dd></div>
        <div><dt>Eingetragen</dt><dd>${timeAgo(h.createdAt)}${h.updatedAt !== h.createdAt ? ` · geändert ${timeAgo(h.updatedAt)}` : ''}</dd></div>
      </dl>
      ${h.comment ? `<div class="comment"><strong>Kommentar</strong><p>${esc(h.comment)}</p></div>` : ''}
      <button class="btn lg block ${h.done ? 'success' : 'primary'}" data-action="toggle-done" data-id="${h.id}" aria-pressed="${h.done}">
        ${h.done ? `${icon('check', 18)} Erledigt – tippen zum Zurücksetzen` : 'Als erledigt markieren'}</button>
      <section class="photos">
        <h3>Fotos zur Aufgabe <span class="muted small">${h.attachments.length}/6</span></h3>
        <div class="gallery">${photos}
          ${canAdd ? `<label class="thumb add">${icon('upload', 22)}<span>Foto hinzufügen</span>
            <input type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple hidden data-change="attach" data-id="${h.id}"></label>` : ''}
        </div>
      </section>
      <div class="detail-actions">
        <button class="btn soft" data-action="copy-task" data-id="${h.id}">${icon('copy', 16)} Kopieren</button>
        ${h.canEdit ? `<button class="btn soft" data-action="edit-task" data-id="${h.id}">${icon('edit', 16)} Bearbeiten</button>
        <button class="btn danger-soft" data-action="delete-task" data-id="${h.id}">${icon('trash', 16)} Löschen</button>` : ''}
      </div>
    </article>`;
  return { title: esc(h.subject), subtitle: `Abgabe am ${formatDayMonth(h.dueDate)}`, back: '#/tasks', html };
}
