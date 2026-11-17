// Применяем тему до отрисовки страницы, чтобы не было «вспышки» светлой темы.
(function () {
  var pref = 'system';
  try { pref = localStorage.getItem('cm.theme') || 'system'; } catch (e) { /* хранилище недоступно */ }
  var dark = pref === 'dark' || (pref === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
})();
