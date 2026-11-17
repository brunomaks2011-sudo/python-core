// ClassMate Service Worker: zeigt Push-Mitteilungen, wenn die Seite geschlossen oder minimiert ist.

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  event.waitUntil((async () => {
    let data = { title: 'ClassMate', body: 'Neue Mitteilung', url: '/#/notifications', tag: 'classmate' };
    try {
      if (event.data) data = { ...data, ...event.data.json() };
    } catch (e) { /* не JSON — показываем стандартный текст */ }

    // Если сайт открыт и виден, он сам покажет уведомление — не дублируем.
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    if (windows.some((w) => w.visibilityState === 'visible')) return;

    await self.registration.showNotification(data.title, {
      body: data.body,
      tag: data.tag,
      icon: '/static/icon.svg',
      badge: '/static/icon.svg',
      data: { url: data.url },
    });
  })());
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || '/', self.location.origin);
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const win of windows) {
      if (new URL(win.url).origin === self.location.origin) {
        await win.focus();
        win.postMessage({ type: 'navigate', hash: url.hash });
        return;
      }
    }
    await self.clients.openWindow(url.href);
  })());
});
