/* TVK Kallavi — Service Worker (offline caching for static assets) */
const CACHE = 'tvk-kallavi-v1';
const ASSETS = [
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/img/tvk-flag.jpeg',
  '/static/img/vijay.jpeg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon-180.png',
  '/static/manifest.json'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(ASSETS);
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; })
                            .map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Static assets: cache-first, then fill the cache as new ones are fetched.
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then(function (cached) {
        return cached || fetch(req).then(function (res) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copy); });
          return res;
        });
      })
    );
    return;
  }

  // Page navigations: network-first, fall back to cache when offline.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(function () {
        return caches.match(req).then(function (cached) {
          return cached || caches.match('/');
        });
      })
    );
  }
});
