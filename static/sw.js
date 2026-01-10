// Pi Camera Control Service Worker
// Enables offline support and PWA install prompt

const CACHE_NAME = 'picamctl-v1';
const urlsToCache = [
  '/',
  '/static/favicon.svg',
  '/static/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  // Network first strategy for API calls
  if (event.request.url.includes('/api/') || 
      event.request.url.includes('/hls/') ||
      event.request.url.includes('/stream') ||
      event.request.url.includes('/snapshot')) {
    return event.respondWith(
      fetch(event.request)
        .catch(() => caches.match(event.request))
    );
  }
  
  // Cache first for static assets
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
      .catch(() => new Response('Offline - content not available', { status: 503 }))
  );
});
