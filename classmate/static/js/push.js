// Браузерные и push-уведомления.
import { api } from './api.js';

export function pushSupported() {
  return window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

export function notificationPermission() {
  return 'Notification' in window ? Notification.permission : 'unsupported';
}

export async function currentSubscription() {
  if (!pushSupported()) return null;
  const registration = await navigator.serviceWorker.getRegistration('/');
  return registration ? registration.pushManager.getSubscription() : null;
}

function base64UrlToBytes(value) {
  const padded = value + '='.repeat((4 - (value.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, (ch) => ch.charCodeAt(0));
}

export async function enablePush() {
  if (!pushSupported()) {
    throw new Error('Этот браузер не поддерживает push-уведомления (нужен HTTPS или localhost)');
  }
  const config = await api('/api/push/config');
  if (!config.enabled) throw new Error('На сервере push-уведомления не настроены');

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw new Error('Разрешите уведомления для этого сайта в настройках браузера');

  const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
  await navigator.serviceWorker.ready;
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64UrlToBytes(config.publicKey),
    });
  }
  const json = subscription.toJSON();
  await api('/api/push/subscribe', { method: 'POST', body: { endpoint: json.endpoint, keys: json.keys } });
}

export async function disablePush() {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await api('/api/push/unsubscribe', { method: 'POST', body: { endpoint: subscription.endpoint } });
  await subscription.unsubscribe();
}

/** Системное уведомление, пока вкладка открыта. */
export function showSystemNotification(note, onClick) {
  if (notificationPermission() !== 'granted') return;
  try {
    const n = new Notification(note.title, { body: note.body, tag: `cm-${note.id}`, icon: '/static/icon.svg' });
    n.onclick = () => {
      window.focus();
      onClick?.();
      n.close();
    };
  } catch {
    /* на некоторых мобильных браузерах конструктор запрещён — тогда хватит всплывающего сообщения */
  }
}
