// Service Worker Librairi-E – Anti-écran blanc & App Shell hors-ligne
const CACHE_NAME = 'librairie-shell-v1';
const SHELL_ASSETS = [
  '/mobile',
  '/static/mobile.js',
  '/static/fonts.css',
  '/static/vendor/zxing.min.js',
  '/static/manifest.webmanifest',
  '/static/favicon-192.png',
  '/static/icon.svg'
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

  // Pour les pages et ressources statiques : Cache First avec mise à jour en tâche de fond (Stale-While-Revalidate)
  event.respondWith(
    caches.match(event.request).then(cachedResp => {
      const fetchPromise = fetch(event.request).then(networkResp => {
        if (networkResp && networkResp.status === 200 && networkResp.type === 'basic') {
          const respToCache = networkResp.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, respToCache));
        }
        return networkResp;
      }).catch(() => {
        // En cas d'échec réseau, si c'est une navigation html, renvoyer /mobile depuis le cache
        if (event.request.mode === 'navigate') {
          return caches.match('/mobile');
        }
      });

      return cachedResp || fetchPromise;
    })
  );
});
