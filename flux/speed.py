"""Make pages fast on slow mobile networks far from the server.

* Every script and stylesheet link gets ?v=<hash of all static files>. The hash changes whenever a file
  changes, so browsers can cache files for a year and still get updates the moment they're deployed.
  Before this, each screen re-checked 5 files with the server (5 slow round trips from India).
* Text responses (HTML, JSON, JS, CSS) are gzip-compressed: about 4x smaller.
"""
import gzip
import hashlib
import os
import re

from flask import request

_ASSET = re.compile(r'''((?:src|href)=["'])(/static/[^"'?]+\.(?:js|css|svg|webmanifest))(["'])''')
COMPRESSIBLE = ("text/", "application/json", "application/javascript", "application/manifest+json", "image/svg+xml")


def asset_version(static_folder):
    h = hashlib.sha256()
    for root, _dirs, files in sorted(os.walk(static_folder)):
        for f in sorted(files):
            path = os.path.join(root, f)
            with open(path, "rb") as fh:
                h.update(path.encode() + b"\0" + fh.read())
    return h.hexdigest()[:12]


def version_assets(html, version):
    return _ASSET.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={version}{m.group(3)}", html)


def assets_in(html):
    return re.findall(r"""(?:src|href)=["'](/static/[^"']+\?v=[0-9a-f]+)["']""", html)


# Offline-first shell: app pages and their files come from the phone, so screens open in milliseconds.
# Pages are refreshed in the background; data (/api) always goes to the network (the page shows the last
# numbers it saw while the fresh ones load). Sign-in, Gmail and the ingest endpoints are never touched.
SERVICE_WORKER = """
const VERSION = "__VERSION__";
const SHELL = __SHELL__;
const CACHE = "flux-shell-" + VERSION;
self.addEventListener("install", (e) => {
  // One by one, keeping only real pages: if the session ended, /app redirects to /login and must not be stored.
  e.waitUntil(caches.open(CACHE).then((c) => Promise.all(SHELL.map((u) => fetch(u, { credentials: "same-origin" })
    .then((res) => (res.ok && !res.redirected ? c.put(u, res) : null)).catch(() => null)))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith("flux-shell-") && k !== CACHE)
    .map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  const isPage = req.mode === "navigate" && SHELL.includes(url.pathname);
  const isAsset = url.pathname.startsWith("/static/") && url.searchParams.get("v") === VERSION;
  if (!isPage && !isAsset) return;  // API, sign-in, Gmail, everything else: straight to the network
  e.respondWith(caches.open(CACHE).then(async (cache) => {
    const key = isPage ? url.pathname : req;
    const hit = await cache.match(key);
    const fresh = fetch(req).then((res) => {
      if (res.ok && !res.redirected && res.type === "basic") cache.put(key, res.clone());
      return res;
    });
    if (hit) { if (isPage) e.waitUntil(fresh.catch(() => {})); return hit; }
    return fresh;
  }));
});
"""


def gzip_response(resp):
    if (resp.status_code != 200
            or "gzip" not in (request.headers.get("Accept-Encoding") or "")
            or resp.headers.get("Content-Encoding")
            or not (resp.mimetype or "").startswith(COMPRESSIBLE)):
        return resp
    resp.direct_passthrough = False  # static files arrive as a file stream; read them so they can be packed
    data = resp.get_data()
    if len(data) < 1024:
        return resp
    packed = gzip.compress(data, compresslevel=6)
    resp.set_data(packed)
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Content-Length"] = str(len(packed))
    vary = resp.headers.get("Vary")
    resp.headers["Vary"] = (vary + ", Accept-Encoding") if vary else "Accept-Encoding"
    return resp
