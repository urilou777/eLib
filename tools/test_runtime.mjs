import fs from 'fs';
import path from 'path';

// Simulation DOM minimale pour tracer l'exécution exacte de main.js et détecter toute erreur runtime
global.window = {
  visualViewport: { height: 800, addEventListener: () => {} },
  innerHeight: 800,
  scrollY: 0,
  scrollX: 0,
  scrollTo: () => {},
  addEventListener: () => {},
  matchMedia: () => ({ matches: false }),
  location: { pathname: '/mobile', hash: '', replaceState: () => {} },
  localStorage: {
    _data: { 'librairie_device_token': 'test_token' },
    getItem(k) { return this._data[k] || null; },
    setItem(k, v) { this._data[k] = String(v); },
    removeItem(k) { delete this._data[k]; }
  },
  navigator: { userAgent: 'Mozilla/5.0 (Linux; Android 14) Chrome/120.0 Mobile' },
  document: {}
};
global.document = {
  addEventListener: () => {},
  documentElement: { style: { setProperty: () => {} } },
  querySelector: (s) => {
    return {
      tagName: 'DIV',
      style: { setProperty: () => {}, removeProperty: () => {} },
      classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
      addEventListener: () => {},
      replaceChildren: () => {},
      append: () => {},
      appendChild: () => {},
      setAttribute: () => {},
      value: '',
      textContent: '',
      innerHTML: ''
    };
  },
  querySelectorAll: () => [],
  createElement: (t) => ({
    tagName: t,
    style: {},
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
    addEventListener: () => {},
    setAttribute: () => {},
    append: () => {},
    getContext: () => ({ drawImage: () => {}, getImageData: () => ({ data: new Uint8ClampedArray(100) }) })
  }),
  createElementNS: (ns, t) => ({
    tagName: t,
    style: {},
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
    addEventListener: () => {},
    setAttribute: () => {},
    append: () => {}
  }),
  createTextNode: (t) => ({ text: t })
};
try {
  Object.defineProperty(global, 'navigator', { value: global.window.navigator, configurable: true });
} catch(e) {}
global.location = global.window.location;
global.localStorage = global.window.localStorage;
global.fetch = async (url) => {
  console.log('[fetch called]:', url);
  return {
    ok: true,
    status: 200,
    json: async () => ([])
  };
};

try {
  console.log('[*] Importing ../app/static/js/mobile/main.js ...');
  await import('../app/static/js/mobile/main.js');
  console.log('[+] main.js imported successfully without runtime error!');
} catch (err) {
  console.error('[!] RUNTIME ERROR DETECTED:', err);
}
