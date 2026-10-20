/**
 * Service Worker for AI Data Insight Builder PWA
 */

const CACHE_NAME = 'data-insight-v1.1';
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/static/style.css',
  '/static/app.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-maskable.png',
  '/static/icons/favicon.png',
  '/static/icons/icon.svg'
];

// Install: Cache critical static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
      .catch((err) => console.warn('[SW] Cache addAll warning:', err))
  );
});

// Activate: Clean up previous caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => {
            console.log('[SW] Removing old cache:', name);
            return caches.delete(name);
          })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Network-first for dynamic API routes, cache-first/stale-while-revalidate for static
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Dynamic API calls or POST requests -> Always network only
  if (
    event.request.method !== 'GET' ||
    url.pathname.startsWith('/inspect') ||
    url.pathname.startsWith('/ask') ||
    url.pathname.startsWith('/suggest') ||
    url.pathname.startsWith('/run') ||
    url.pathname.startsWith('/explain') ||
    url.pathname.startsWith('/health') ||
    url.pathname.startsWith('/api/')
  ) {
    return; // Pass through to network
  }

  // Static assets and page navigations
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request)
        .then((networkResponse) => {
          if (
            networkResponse &&
            networkResponse.status === 200 &&
            networkResponse.type === 'basic'
          ) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseToCache);
            });
          }
          return networkResponse;
        })
        .catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});
