// Состояние приложения в памяти страницы. Источник правды — сервер; здесь только копия.
import { todayIso } from './util.js';

export const state = {
  me: null,
  cls: null,
  homework: [],
  notifications: [],
  unread: 0,
  classVersion: null,
  doneCount: null,
  pushSubscribed: false,
  filters: { status: 'all', subject: '', query: '' },
  calendar: { view: 'month', date: todayIso() },
};

let renderer = () => {};
export const setRenderer = (fn) => { renderer = fn; };
export const render = () => renderer();
