const CACHE_NAME = 'zokyo-assets-v9';
const PRECACHE_ASSETS = [
  '/static/manifest.webmanifest',
  '/static/css/zokyo.css',
  '/static/css/components/pwa-install.css',
  '/static/js/masks.js',
  '/static/js/validators.js',
  '/static/js/viacep.js',
  '/static/js/ui.js',
  '/static/js/api.js',
  '/static/js/pwa-install.js',
  '/static/js/pages/login.js',
  '/static/img/zokyo-logo.svg',
  '/static/img/zokyo-favicon.svg',
  '/static/img/icons/zokyo-icon-192.png',
  '/static/img/icons/zokyo-icon-512.png',
  '/static/img/icons/zokyo-icon.svg',
];

const SAFE_ASSET = /\.(css|js|svg|png|jpg|jpeg|webp|woff2?|ttf)$/i;
const BLOCKED_PATH = /^\/(api|clientes|coleta|coletas|os|financeiro|uploads|documentos|pdf|logs|usuarios|configuracoes)\b/i;
const OFFLINE_HTML = `<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#2563eb">
  <title>Zokyo offline</title>
  <style>
    body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0f172a;color:#e2e8f0;font:500 16px Arial,sans-serif;padding:24px}
    main{max-width:420px;text-align:center}
    h1{font-size:24px;margin:0 0 10px}
    p{color:#94a3b8;line-height:1.5;margin:0}
  </style>
</head>
<body><main><h1>Sem conexao</h1><p>Reconecte e abra o Zokyo novamente. Dados de clientes, OS, fotos e financeiro nao sao cacheados por seguranca.</p></main></body>
</html>`;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() => new Response(OFFLINE_HTML, {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      }))
    );
    return;
  }

  if (BLOCKED_PATH.test(url.pathname)) return;

  const isStatic = url.pathname.startsWith('/static/') && SAFE_ASSET.test(url.pathname);
  const isManifest = url.pathname === '/static/manifest.webmanifest';
  if (!isStatic && !isManifest) return;

  event.respondWith(
    caches.match(req).then(cached => {
      const network = fetch(req).then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, copy));
        }
        return response;
      });
      return cached || network;
    })
  );
});
