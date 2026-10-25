// Start page, job progress and result view. All text from the server goes through textContent.
const $ = (id) => document.getElementById(id);
const STORE = 'brickgen.jobs';
const PLANNERS = { claude: 'Claude', rules: 'по ключевым словам' };

let viewer = null;
let viewerFailed = false;
let pollToken = 0;

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const child of children) node.append(child);
  return node;
}

function swatch(hex) {
  const chip = el('i');
  if (hex) chip.style.backgroundColor = hex;
  return chip;
}

function plural(n, one, few, many) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function seconds(value) {
  return `${Math.max(0, value).toFixed(value < 10 ? 1 : 0)} с`;
}

// Recent jobs live only in this browser: the site has no public gallery.
function remembered() {
  try { return JSON.parse(localStorage.getItem(STORE)) || []; } catch { return []; }
}

function remember(entry) {
  const list = remembered().filter((item) => item.id !== entry.id);
  list.unshift(entry);
  try { localStorage.setItem(STORE, JSON.stringify(list.slice(0, 12))); } catch { /* private mode */ }
  renderGallery();
}

function renderGallery() {
  const list = remembered();
  $('mine').hidden = list.length === 0;
  $('gallery').replaceChildren(...list.map((item) => {
    const tile = el('a', { className: 'card tile', href: `/?job=${encodeURIComponent(item.id)}` },
      el('img', { src: `/files/${encodeURIComponent(item.id)}/preview.png`, alt: '', loading: 'lazy' }),
      el('span', { textContent: item.title || item.prompt }),
      el('small', { textContent: new Date(item.created * 1000).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) }));
    tile.querySelector('img').addEventListener('error', () => tile.classList.add('pending'), { once: true });
    tile.addEventListener('click', (event) => {
      event.preventDefault();
      openJob(item.id, true);
    });
    return tile;
  }));
}

async function loadThemes() {
  const response = await fetch('/api/themes');
  const data = await response.json();
  $('themes').replaceChildren(...data.themes.map((theme) => {
    const chip = el('button', { type: 'button', className: 'chip', textContent: theme.label });
    chip.addEventListener('click', () => {
      $('prompt').value = theme.prompt;
      $('ask').requestSubmit();
    });
    return chip;
  }));
  $('catalog').replaceChildren(...data.catalog.map((group) =>
    el('div', {}, el('b', { textContent: group.group }), el('p', { textContent: group.titles.join(', ') }))));
}

async function loadHealth() {
  try {
    const data = await (await fetch('/api/health')).json();
    const missing = Object.entries(data.tools).filter(([, ok]) => !ok).map(([name]) => name);
    $('health').textContent = `Подбор: ${PLANNERS[data.planner] || data.planner}` +
      (missing.length ? ` · не настроено: ${missing.join(', ')}` : '');
  } catch { /* the footer note is optional */ }
}

async function submit(event) {
  event.preventDefault();
  const prompt = $('prompt').value.trim();
  $('form-error').hidden = true;
  if (prompt.length < 2) return;
  $('submit').disabled = true;
  try {
    const response = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(data.detail) ? 'Опишите модель короче: до 300 символов.' : data.detail;
      throw new Error(detail || 'Не удалось запустить сборку.');
    }
    remember({ id: data.id, prompt, created: Date.now() / 1000 });
    openJob(data.id, true);
  } catch (error) {
    $('form-error').textContent = error.message;
    $('form-error').hidden = false;
  } finally {
    $('submit').disabled = false;
  }
}

function openJob(id, push) {
  if (push) history.pushState({ job: id }, '', `/?job=${encodeURIComponent(id)}`);
  const token = ++pollToken;
  $('job').hidden = false;
  $('result').hidden = true;
  $('job-error').hidden = true;
  $('job-prompt').textContent = '';
  $('job').scrollIntoView({ behavior: 'smooth', block: 'start' });
  poll(id, token);
}

async function poll(id, token) {
  let job;
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(id)}`);
    if (response.status === 404) {
      showError('Модель не найдена: возможно, ссылка устарела.');
      return;
    }
    job = await response.json();
  } catch {
    if (token === pollToken) setTimeout(() => poll(id, token), 2000);
    return;
  }
  if (token !== pollToken) return;
  renderStatus(job);
  if (job.state === 'queued' || job.state === 'running') {
    setTimeout(() => poll(id, token), 1000);
  } else if (job.state === 'done') {
    renderResult(job);
  } else {
    showError(job.error || 'Сборка не удалась.');
  }
}

function showError(text) {
  $('job-error').textContent = text;
  $('job-error').hidden = false;
  $('job-badge').textContent = 'не удалось';
}

function renderStatus(job) {
  $('job-prompt').textContent = `«${job.prompt}»`;
  const now = Date.now() / 1000;
  const badges = { queued: job.position ? `в очереди: ${job.position}` : 'в очереди', running: 'собирается…',
                   done: 'готово', failed: 'не удалось' };
  $('job-badge').textContent = badges[job.state] || job.state;
  for (const item of $('stages').children) {
    const stage = job.stages[item.dataset.stage] || {};
    item.dataset.status = stage.status || 'pending';
    let note = '';
    if (stage.status === 'running' && stage.started) note = seconds(now - stage.started);
    if ((stage.status === 'done' || stage.status === 'failed') && stage.started && stage.finished) {
      note = seconds(stage.finished - stage.started);
    }
    item.querySelector('small').textContent = note;
  }
  const planItem = $('stages').querySelector('[data-stage="draft"] span:nth-child(2)');
  planItem.textContent = job.template ? `Заготовка: ${job.template.title}` : 'Подбираю заготовку и цвета';
}

function setView(view) {
  for (const tab of document.querySelectorAll('.tabs button')) {
    tab.setAttribute('aria-selected', String(tab.dataset.view === view));
  }
  $('canvas').hidden = view !== '3d';
  $('preview').hidden = view !== 'image';
  $('viewer-msg').hidden = view !== '3d' || !$('viewer-msg').textContent;
}

async function show3d(url) {
  $('viewer-msg').textContent = 'Загружаю 3D…';
  $('viewer-msg').hidden = false;
  try {
    if (!viewer && !viewerFailed) {
      const { Viewer } = await import('./viewer.js');
      viewer = new Viewer($('canvas'));
    }
    if (!viewer) throw new Error('viewer unavailable');
    await viewer.load(url);
    $('viewer-msg').textContent = '';
    $('viewer-msg').hidden = true;
  } catch (error) {
    console.error(error);
    viewerFailed = viewerFailed || !viewer;
    $('viewer-msg').textContent = '3D-просмотр недоступен в этом браузере — показываю снимок.';
    setView('image');
  }
}

function link(id, name, download) {
  return `/files/${encodeURIComponent(id)}/${name}${download ? '?download=1' : ''}`;
}

function renderResult(job) {
  const result = job.result;
  const draft = job.draft;
  $('result').hidden = false;
  $('result-title').textContent = draft.title;
  $('result-summary').textContent = draft.summary;
  $('caveats').replaceChildren(...(draft.caveats || []).map((text) => el('li', { textContent: text })));
  if (draft.planner_note) $('caveats').append(el('li', { textContent: draft.planner_note }));

  $('fact-parts').textContent = result.placements ?? '—';
  $('fact-types').textContent = result.part_types ?? '—';
  $('fact-template').textContent = job.template?.title || draft.template;
  $('fact-planner').textContent = PLANNERS[draft.planner] || draft.planner;
  $('colours').replaceChildren(...(job.colours || []).map((c) =>
    el('span', { className: 'swatch' }, swatch(c.hex), `${c.role}: ${c.colour}`)));

  const checks = result.checks;
  const total = checks.stages.length;
  const passed = checks.stages.filter((s) => s.status === 'passed').length;
  const summary = el('li', { className: checks.passed ? 'passed' : 'failed' },
    el('span', { className: 'mark', textContent: checks.passed ? '✓' : '!' }),
    el('span', { className: 'summary', textContent: checks.passed
      ? `Все проверки пройдены (${passed} из ${total})` : `Проверки не пройдены (${passed} из ${total})` }));
  $('checks').replaceChildren(summary, ...checks.stages.map((stage) => {
    const status = stage.status === 'passed' ? 'passed' : stage.status === 'skipped' ? 'skipped' : 'failed';
    return el('li', { className: status },
      el('span', { className: 'mark', textContent: status === 'passed' ? '✓' : status === 'skipped' ? '–' : '✕' }),
      el('span', { textContent: stage.label }));
  }));
  const notes = checks.notes || [];
  $('notes-wrap').hidden = notes.length === 0;
  $('notes-wrap').querySelector('summary').textContent = `Замечания проверки: ${notes.length}`;
  $('notes').replaceChildren(...notes.map((note) =>
    el('li', { textContent: note.count > 1 ? `${note.text} (${note.count} ${plural(note.count, 'раз', 'раза', 'раз')})` : note.text })));
  if (checks.physical_validity === 'not_proven') {
    $('notes').append(el('li', { textContent: 'Проверки не доказывают, что модель устойчива и соберётся в реальности.' }));
    $('notes-wrap').hidden = false;
  }

  const files = new Set(result.files);
  const downloads = { 'dl-mpd': 'model.mpd', 'dl-glb': 'model.glb', 'dl-csv': 'parts.csv', 'dl-plan': 'model.plan.json' };
  for (const [id, name] of Object.entries(downloads)) {
    const anchor = $(id);
    const available = files.has(name);
    anchor.href = available ? link(job.id, name, true) : '#';
    anchor.setAttribute('aria-disabled', String(!available));
  }
  $('attribution').textContent = job.template?.attribution
    ? 'Модель основана на примерах LDraw Nova (Carlos Antelo), лицензия CC BY-SA 4.0. Детали — библиотека LDraw.'
    : 'Модель построена генератором BrickGen. Детали — библиотека LDraw.';

  $('bom').replaceChildren(...result.bom.map((row) => el('tr', {},
    el('td', {}, el('code', { textContent: row.part })),
    el('td', { textContent: row.description }),
    el('td', {}, el('span', { className: 'colour-cell' },
      swatch(row.hex), row.colour.replaceAll('_', ' '))),
    el('td', { className: 'num', textContent: row.quantity }))));

  if (files.has('preview.png')) $('preview').src = link(job.id, 'preview.png');
  else $('preview').removeAttribute('src');
  if (files.has('model.glb')) {
    setView('3d');
    show3d(link(job.id, 'model.glb'));
  } else {
    $('viewer-msg').textContent = result.glb_error ? 'GLB не получился — показываю снимок.' : '';
    setView('image');
  }
  remember({ id: job.id, prompt: job.prompt, title: draft.title, created: job.created });
}

function init() {
  $('ask').addEventListener('submit', submit);
  $('prompt').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      $('ask').requestSubmit();
    }
  });
  for (const tab of document.querySelectorAll('.tabs button')) {
    tab.addEventListener('click', () => setView(tab.dataset.view));
  }
  window.addEventListener('popstate', () => {
    const id = new URLSearchParams(location.search).get('job');
    if (id) openJob(id, false);
  });
  loadThemes();
  loadHealth();
  renderGallery();
  const id = new URLSearchParams(location.search).get('job');
  if (id) openJob(id, false);
}

init();
