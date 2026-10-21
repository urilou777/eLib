// Service Worker eLib – Anti-écran blanc & App Shell hors-ligne
const CACHE_NAME = 'librairie-shell-v24';
const SHELL_ASSETS = [
  '/mobile',
  '/static/mobile.js',
  '/static/js/mobile/main.js',
  '/static/js/mobile/core.js',
  '/static/js/mobile/state.js',
  '/static/js/mobile/api.js',
  '/static/js/mobile/network.js',
  '/static/js/mobile/pairing.js',
  '/static/js/mobile/cart.js',
  '/static/js/mobile/book_stats.js',
  '/static/js/mobile/modes.js',
  '/static/js/mobile/ocr.js',
  '/static/js/mobile/new_book_modal.js',
  '/static/js/mobile/search.js',
  '/static/js/mobile/scanner.js',
  '/static/js/mobile/fullscreen.js',
  '/static/fonts.css',
  '/static/vendor/zxing.min.js',
  '/static/manifest.webmanifest',
  '/static/favicon.ico?v=20261021_e_v1',
  '/static/favicon-16.png?v=20261021_e_v1',
  '/static/favicon-32.png?v=20261021_e_v1',
  '/static/favicon-48.png?v=20261021_e_v1',
  '/static/favicon-64.png?v=20261021_e_v1',
  '/static/favicon-192.png?v=20261021_e_v1',
  '/static/favicon-512.png?v=20261021_e_v1'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(SHELL_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Pour les requêtes API : réseau direct sans passer par le cache du Service Worker
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // Pour les scripts JS et CSS : Network First (chargement immédiat de la dernière version, repli cache si hors-ligne)
  if (url.pathname.endsWith('.js') || url.pathname.endsWith('.css') || url.pathname === '/mobile') {
    event.respondWith(
      fetch(event.request).then(networkResp => {
        if (networkResp && networkResp.status === 200 && networkResp.type === 'basic') {
          const respToCache = networkResp.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, respToCache));
        }
        return networkResp;
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  // Pour les autres ressources statiques (icônes, polices) : Cache First
  event.respondWith(
    caches.match(event.request).then(cachedResp => {
      return cachedResp || fetch(event.request).then(networkResp => {
        if (networkResp && networkResp.status === 200 && networkResp.type === 'basic') {
          const respToCache = networkResp.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, respToCache));
        }
        return networkResp;
      });
    })
  );
});
