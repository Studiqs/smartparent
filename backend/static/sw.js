/**
 * STUDIQS® SmartParent™ - Progressive Web App (PWA) Service Worker
 * Version: 6.3.0
 * 
 * Strict Security Architecture Rules (from Studiqs Smartparent PWA.docx):
 * 1. ONLY cache approved public static assets and app-shell resources.
 * 2. NEVER cache authenticated APIs (/api/v1/*), private reports, child records,
 *    or expert evaluations in persistent browser CacheStorage (DPDP Act 2023).
 * 3. Provide a branded offline fallback for network interruptions.
 */

const CACHE_NAME = 'studiqs-smartparent-v6.3.0';
const STATIC_ASSETS = [
  '/',
  '/static/manifest.webmanifest',
  '/static/offline.html',
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/pwa_installer.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

// Sensitive endpoints that MUST NEVER be cached locally
const SENSITIVE_PATH_PATTERNS = [
  /\/api\/v1\/auth\//i,
  /\/api\/v1\/reports\//i,
  /\/api\/v1\/performance\//i,
  /\/api\/v1\/marketplace\//i,
  /\/api\/v1\/voice\//i,
  /\/api\/v1\/handoff\//i,
  /\/api\/v1\/subscriptions\//i,
  /\/api\/v1\/admin\//i
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // Pre-cache only non-sensitive shell assets
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[ServiceWorker] Some pre-cache assets unavailable during install:', err);
      });
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 1. Non-GET requests always bypass service worker
  if (event.request.method !== 'GET') {
    return;
  }

  // 2. Strict Zero-Cache Rule for Sensitive Academic / Authentication APIs
  const isSensitive = SENSITIVE_PATH_PATTERNS.some((pattern) => pattern.test(url.pathname));
  if (isSensitive) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(
          JSON.stringify({
            error: true,
            error_code: 'NETWORK_OFFLINE',
            message: 'Network connectivity is required for real-time academic telemetry.'
          }),
          {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          }
        );
      })
    );
    return;
  }

  // 3. Network-First strategy for application pages with offline fallback
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => {
        return caches.match('/static/offline.html');
      })
    );
    return;
  }

  // 4. Cache-First with Network Revalidation for public static assets
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).then((networkResponse) => {
        if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
          return networkResponse;
        }
        // Cache valid static responses
        if (url.pathname.startsWith('/static/')) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => {
        return new Response('', { status: 408, statusText: 'Request Timed Out' });
      });
    })
  );
});

