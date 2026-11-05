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
