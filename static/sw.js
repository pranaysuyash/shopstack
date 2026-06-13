/* ShopStack service worker — Phase 4 #5 PWA shell.
 *
 * Strategy: cache-first for the app shell (HTML, CSS, JS, icons) so the
 * app can boot offline. Network-first for everything else (Gradio API
 * calls, market data, OCR) — those will fail offline and the user will
 * see the cached "offline" UI.
 *
 * This is intentionally minimal. Real production PWA would also
 * implement background sync, push notifications, and stale-while-revalidate.
 */

const CACHE_NAME = "shopstack-shell-v1";
const SHELL_ASSETS = [
  "/",
  "/static/manifest.json",
  "/static/icon-192.svg",
  "/static/icon-512.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // Best-effort: add each shell asset individually so a single
      // 404 doesn't abort the whole install.
      return Promise.all(
        SHELL_ASSETS.map((url) =>
          cache.add(url).catch((err) => {
            console.warn("[sw] failed to cache", url, err);
          })
        )
      );
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  // Don't intercept Gradio's WebSocket / API / SSE endpoints — those need
  // network. Only cache static assets and the app shell.
  const isShellAsset =
    SHELL_ASSETS.includes(url.pathname) ||
    url.pathname.startsWith("/static/") ||
    url.pathname === "/";

  if (!isShellAsset) {
    return; // let the browser fetch normally
  }

  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(req)
        .then((resp) => {
          // Opportunistically cache successful responses
          if (resp.ok && resp.status === 200) {
            const copy = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }
          return resp;
        })
        .catch(() => {
          // Offline fallback: return the cached root if available
          return caches.match("/").then((fallback) => {
            return (
              fallback ||
              new Response("Offline — ShopStack shell not cached.", {
                status: 503,
                statusText: "Service Unavailable",
              })
            );
          });
        });
    })
  );
});
