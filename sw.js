// Offline cache for the Kriya timer. Bump VERSION whenever any file changes.
const VERSION = 'kriya-v1';
const CORE = ['./', 'index.html', 'timeline.json', 'manifest.webmanifest',
  'icons/icon-180.png', 'icons/icon-192.png', 'icons/icon-512.png'];
const AUDIO = 'audio/session.mp3';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(CORE.concat(AUDIO))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Audio players ask for byte ranges; answer them from the cached full file.
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
  if (url.origin !== location.origin) return;
  if (url.pathname.endsWith(AUDIO)) {
    e.respondWith(caches.open(VERSION).then(async c => {
      const hit = await c.match(AUDIO);
      return hit ? rangeResponse(e.request, hit) : fetch(e.request);
    }));
    return;
  }
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then(hit => hit || fetch(e.request)));
});
