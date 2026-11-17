// Offline support for the Kriya timer.
// - Page, timeline and icons: network first (always fresh when online), cache as fallback.
// - Audio: the URL carries a content hash (?v=...), so each new build is a new file.
//   Cached on first play; old versions are deleted.
const CORE = 'kriya-core';
const AUDIO_CACHE = 'kriya-audio';
const CORE_FILES = ['./', 'index.html', 'timeline.json', 'manifest.webmanifest',
  'icons/icon-180.png', 'icons/icon-192.png', 'icons/icon-512.png'];

const fresh = url => new Request(url, { cache: 'reload' });   // bypass the HTTP cache

// Save the chosen sessions for offline use; keep other current versions if already saved; drop stale ones.
async function cacheAudio(urls, valid) {
  const abs = u => new URL(u, self.registration.scope).href;
  const want = urls.map(abs), keep = new Set(valid.map(abs));
  const cache = await caches.open(AUDIO_CACHE);
  for (const url of want) {
    if (!(await cache.match(url))) {
      const res = await fetch(fresh(url));
      if (res.ok) await cache.put(url, res);
    }
  }
  for (const req of await cache.keys()) if (!keep.has(req.url)) await cache.delete(req);
}

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CORE).then(c => c.addAll(CORE_FILES.map(fresh))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== CORE && k !== AUDIO_CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener('message', e => { if (e.data && e.data.type === 'cache') e.waitUntil(cacheAudio(e.data.urls, e.data.valid).catch(() => {})); });

async function rangeResponse(req, cached) {
  const buf = await cached.arrayBuffer();
  const m = /bytes=(\d*)-(\d*)/.exec(req.headers.get('range') || '');
  if (!m) return new Response(buf, { headers: { 'Content-Type': 'audio/mpeg', 'Content-Length': buf.byteLength, 'Accept-Ranges': 'bytes' } });
  const start = m[1] ? +m[1] : 0;
  const end = m[2] ? Math.min(+m[2], buf.byteLength - 1) : buf.byteLength - 1;
  return new Response(buf.slice(start, end + 1), {
    status: 206,
    headers: { 'Content-Type': 'audio/mpeg', 'Content-Range': `bytes ${start}-${end}/${buf.byteLength}`,
      'Content-Length': end - start + 1, 'Accept-Ranges': 'bytes' }
  });
}

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin || e.request.method !== 'GET') return;

  if (url.pathname.endsWith('.mp3')) {
    e.respondWith((async () => {
      const hit = await (await caches.open(AUDIO_CACHE)).match(e.request.url);
      return hit ? rangeResponse(e.request, hit) : fetch(e.request);
    })());
    return;
  }

  e.respondWith((async () => {
    try {
      const res = await fetch(new Request(e.request, { cache: 'no-cache' }));
      if (res.ok) (await caches.open(CORE)).put(e.request, res.clone());
      return res;
    } catch (err) {
      return (await caches.match(e.request, { ignoreSearch: true })) || Response.error();
    }
  })());
});
