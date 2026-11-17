// Общие помощники: экранирование, даты, цвета предметов, иконки, всплывающие сообщения.

export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

export function plural(n, [one, few, many]) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

export const countTasks = (n) => `${n} ${plural(n, ['задание', 'задания', 'заданий'])}`;

export function truncate(text, max) {
  const clean = String(text).replace(/\s+/g, ' ').trim();
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean;
}

export function initials(name) {
  return String(name).trim().split(/\s+/).slice(0, 2).map((p) => p[0] || '').join('').toUpperCase() || '?';
}

export const capitalize = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

// ---------- даты (всё в местном времени пользователя, формат YYYY-MM-DD)

const pad = (n) => String(n).padStart(2, '0');
export const isoOf = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export function parseIso(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}
export const todayIso = () => isoOf(new Date());
export function addDays(iso, n) {
  const d = parseIso(iso);
  d.setDate(d.getDate() + n);
  return isoOf(d);
}
export function addMonths(iso, n) {
  const d = parseIso(iso);
  const day = d.getDate();
  d.setDate(1);
  d.setMonth(d.getMonth() + n);
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  d.setDate(Math.min(day, last));
  return isoOf(d);
}
export const diffDays = (from, to) => Math.round((parseIso(to) - parseIso(from)) / 86400000);
export function startOfWeek(iso) {
  const d = parseIso(iso);
  return addDays(iso, -((d.getDay() + 6) % 7));
}

const fmtFull = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });
const fmtDayMonth = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' });
const fmtShort = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' });
const fmtWeekday = new Intl.DateTimeFormat('ru-RU', { weekday: 'short' });
const fmtMonth = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' });

export const formatFull = (iso) => capitalize(fmtFull.format(parseIso(iso)));
export const formatDayMonth = (iso) => fmtDayMonth.format(parseIso(iso));
export const formatShort = (iso) => fmtShort.format(parseIso(iso)).replace('.', '');
export const formatWeekday = (iso) => capitalize(fmtWeekday.format(parseIso(iso)));
export const formatMonth = (iso) => capitalize(fmtMonth.format(parseIso(iso)).replace(' г.', ''));

export function relativeDay(iso, today = todayIso()) {
  const diff = diffDays(today, iso);
  if (diff === 0) return 'Сегодня';
  if (diff === 1) return 'Завтра';
  if (diff === 2) return 'Послезавтра';
  if (diff === -1) return 'Вчера';
  const n = Math.abs(diff);
  const days = `${n} ${plural(n, ['день', 'дня', 'дней'])}`;
  return diff > 0 ? `Через ${days}` : `${days} назад`;
}

const rtf = new Intl.RelativeTimeFormat('ru', { numeric: 'auto' });
export function timeAgo(isoDateTime) {
  const seconds = (Date.now() - new Date(isoDateTime).getTime()) / 1000;
  for (const [unit, size] of [['day', 86400], ['hour', 3600], ['minute', 60]]) {
    if (Math.abs(seconds) >= size) return rtf.format(-Math.round(seconds / size), unit);
  }
  return 'только что';
}

export function userTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

// ---------- предметы и их цвета

const SUBJECT_COLORS = {
  'Математика': '#7c5cff',
  'Алгебра': '#7c5cff',
  'Геометрия': '#9b7bff',
  'Русский язык': '#ff6b8b',
  'Литература': '#b06ad9',
  'Английский язык': '#3ab0ff',
  'История': '#f5a524',
  'Обществознание': '#ff8e5e',
  'География': '#20b2aa',
  'Физика': '#5b8def',
  'Химия': '#2fbf86',
  'Биология': '#7bc950',
  'Информатика': '#4fb3bf',
  'ОБЖ': '#e5534b',
  'Физкультура': '#00a896',
  'Музыка': '#f472b6',
  'ИЗО': '#e0a100',
  'Технология': '#8d99ae',
};
const EXTRA_COLORS = ['#7c5cff', '#ff6b8b', '#3ab0ff', '#f5a524', '#b06ad9', '#20b2aa', '#2fbf86', '#ff8e5e', '#5b8def', '#f472b6'];

export const SUBJECT_PRESETS = [
  'Математика', 'Русский язык', 'Литература', 'Английский язык', 'История', 'Обществознание',
  'География', 'Физика', 'Химия', 'Биология', 'Информатика', 'ОБЖ', 'Физкультура', 'Музыка', 'ИЗО', 'Технология',
];

export function subjectColor(name) {
  if (SUBJECT_COLORS[name]) return SUBJECT_COLORS[name];
  let hash = 0;
  for (const ch of String(name).toLowerCase()) hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
  return EXTRA_COLORS[hash % EXTRA_COLORS.length];
}

// ---------- иконки (линейные, в стиле Feather)

const ICONS = {
  home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
  list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  chart: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
  bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  edit: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
  search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  sun: '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>',
  moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
  left: '<polyline points="15 18 9 12 15 6"/>',
  right: '<polyline points="9 18 15 12 9 6"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  alert: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  key: '<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>',
  sparkles: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/>',
  back: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
};

export function icon(name, size = 20) {
  return `<svg class="ico" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
}

export const LOGO = `<svg class="logo" viewBox="0 0 64 64" aria-hidden="true"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8f7bff"/><stop offset="1" stop-color="#5ea8ff"/></linearGradient></defs><rect width="64" height="64" rx="16" fill="url(#lg)"/><path d="M18 17h22a6 6 0 0 1 6 6v24H24a6 6 0 0 1-6-6z" fill="#fff" opacity=".95"/><path d="M25 33l5 5 10-11" fill="none" stroke="#7c5cff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

// ---------- всплывающие сообщения и хранилище

export function toast(message, tone = 'info') {
  const root = document.getElementById('toasts');
  if (!root) return;
  // Не дублируем одинаковые сообщения и держим на экране не больше трёх.
  if ([...root.children].some((t) => t.textContent === message && !t.classList.contains('leave'))) return;
  while (root.children.length >= 3) root.firstElementChild.remove();
  const el = document.createElement('div');
  el.className = `toast ${tone}`;
  el.textContent = message;
  root.append(el);
  setTimeout(() => el.classList.add('leave'), 3200);
  setTimeout(() => el.remove(), 3600);
}

export const storage = {
  get(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  },
  set(key, value) {
    try { localStorage.setItem(key, value); } catch { /* недоступно — не страшно */ }
  },
};
