/* AI-Pulse service worker。
   ニュースサイトのため HTML は network-first（最新の記事を優先し、オフライン時のみ
   キャッシュへフォールバック）、CSS/JS/画像などの静的アセットは cache-first にする。
   これで「更新したのに古い記事が出る」cache-first の stale 問題を避けつつオフラインも保つ。
   サイト更新でアセットを差し替えたら CACHE 版を上げると activate で旧キャッシュを破棄する。 */
const CACHE = "aipulse-v15";
const CORE = [
  "./", "index.html", "archive.html", "theme.css", "app.js",
  "manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png",
  "thumb-model.svg", "thumb-editor.svg", "thumb-media.svg",
  "thumb-agent.svg", "thumb-infra.svg", "thumb-policy.svg",
  "thumb-physical.svg",
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CORE)).catch(() => {}));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function cachePut(req, res) {
  const copy = res.clone();
  caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
  return res;
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const isHTML =
    req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html");
  if (isHTML) {
    // network-first: 最新の記事を優先。失敗時のみキャッシュ（最終手段で index.html）
    e.respondWith(
      fetch(req)
        .then((res) => cachePut(req, res))
        .catch(() => caches.match(req).then((hit) => hit || caches.match("index.html")))
    );
  } else {
    // cache-first: 静的アセット（差し替え時は CACHE 版を上げて破棄）
    e.respondWith(
      caches.match(req).then(
        (hit) => hit || fetch(req).then((res) => cachePut(req, res)).catch(() => undefined)
      )
    );
  }
});
