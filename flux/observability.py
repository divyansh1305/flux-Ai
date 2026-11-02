"""Observability without extra dependencies.

* Request IDs   – every response carries X-Request-ID (accepted from a proxy if well-formed),
                  and every log line written during that request includes it.
* JSON logs     – one access-log line per request: route template (never the query string),
                  status, latency, user id (never email). Set LOG_FORMAT=text for local dev.
* /metrics      – Prometheus text format: request counts, latency histogram per route,
                  ingest outcomes (logged / duplicate / skipped) per source.
                  Protected by METRICS_TOKEN (Bearer). Without a token it is only served
                  outside production.

Counters are per process. Flux runs one gunicorn worker (SQLite has one writer anyway), so
this is the whole picture; with more workers you'd switch to prometheus_client multiprocess mode.
"""
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from collections import defaultdict

from flask import Response, g, has_request_context, request

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
_RID_OK = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_lock = threading.Lock()
_requests = defaultdict(int)                      # (method, route, status) -> count
_latency = defaultdict(lambda: [0] * (len(BUCKETS) + 1))   # route -> bucket counts (+Inf last)
_latency_sum = defaultdict(float)
_latency_count = defaultdict(int)
_ingest = defaultdict(int)                        # (source, result) -> count
_started = time.time()


def count_ingest(source, result):
    """result: logged | duplicate | skipped | rejected"""
    with _lock:
        _ingest[(source, result)] += 1


class _RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = getattr(g, "request_id", "-") if has_request_context() else "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
               "logger": record.name, "msg": record.getMessage(), "request_id": getattr(record, "request_id", "-")}
        for key in ("method", "route", "status", "ms", "user_id"):
            if hasattr(record, key):
                out[key] = getattr(record, key)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


def configure_logging():
    root = logging.getLogger()
    handler = logging.StreamHandler()
    if os.environ.get("LOG_FORMAT", "json" if os.environ.get("FLUX_ENV") == "production" else "text") == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"))
    handler.addFilter(_RequestIdFilter())
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)   # we write our own access log


access_log = logging.getLogger("flux.access")


def init_app(app):
    @app.before_request
    def _start():
        g.t0 = time.perf_counter()
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if _RID_OK.match(incoming) else uuid.uuid4().hex

    @app.after_request
    def _finish(resp):
        if not hasattr(g, "t0"):
            return resp
        dt = time.perf_counter() - g.t0
        route = request.url_rule.rule if request.url_rule else ("static" if request.path.startswith("/static/") else "unmatched")
        if route.startswith("/static"):
            route = "static"
        with _lock:
            _requests[(request.method, route, resp.status_code)] += 1
            buckets = _latency[route]
            for i, b in enumerate(BUCKETS):
                if dt <= b:
                    buckets[i] += 1
                    break
            else:
                buckets[-1] += 1
            _latency_sum[route] += dt
            _latency_count[route] += 1
        resp.headers["X-Request-ID"] = g.request_id
        if route not in ("static", "/healthz", "/metrics"):
            from .security import current_user

            user = current_user()
            access_log.info("%s %s %s", request.method, route, resp.status_code, extra={
                "method": request.method, "route": route, "status": resp.status_code, "ms": round(dt * 1000, 1),
                "user_id": user["id"] if user else None})
        return resp

    @app.get("/metrics")
    def metrics():
        token = app.config.get("METRICS_TOKEN") or os.environ.get("METRICS_TOKEN")
        if token:
            given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not secrets.compare_digest(given, token):
                return Response("unauthorized\n", 401, mimetype="text/plain")
        elif app.config.get("IS_PRODUCTION"):
            return Response("not found\n", 404, mimetype="text/plain")
        return Response(render(), mimetype="text/plain; version=0.0.4")

    @app.get("/readyz")
    def readyz():
        from .db import get_db

        try:
            get_db().execute("SELECT 1").fetchone()
            return {"ok": True, "db": "up"}
        except Exception:  # pragma: no cover
            return {"ok": False, "db": "down"}, 503


def _esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def render():
    lines = ["# HELP flux_up_seconds Seconds since this process started.", "# TYPE flux_up_seconds gauge",
             f"flux_up_seconds {time.time() - _started:.0f}",
             "# HELP flux_http_requests_total HTTP requests by route template and status.",
             "# TYPE flux_http_requests_total counter"]
    with _lock:
        for (m, r, s), n in sorted(_requests.items()):
            lines.append(f'flux_http_requests_total{{method="{m}",route="{_esc(r)}",status="{s}"}} {n}')
        lines += ["# HELP flux_http_request_duration_seconds Request latency.",
                  "# TYPE flux_http_request_duration_seconds histogram"]
        for r in sorted(_latency):
            cum = 0
            for b, n in zip(BUCKETS, _latency[r]):
                cum += n
                lines.append(f'flux_http_request_duration_seconds_bucket{{route="{_esc(r)}",le="{b}"}} {cum}')
            cum += _latency[r][-1]
            lines.append(f'flux_http_request_duration_seconds_bucket{{route="{_esc(r)}",le="+Inf"}} {cum}')
            lines.append(f'flux_http_request_duration_seconds_sum{{route="{_esc(r)}"}} {_latency_sum[r]:.6f}')
            lines.append(f'flux_http_request_duration_seconds_count{{route="{_esc(r)}"}} {_latency_count[r]}')
        lines += ["# HELP flux_ingest_total Automatic-logging outcomes by source.", "# TYPE flux_ingest_total counter"]
        for (src, res), n in sorted(_ingest.items()):
            lines.append(f'flux_ingest_total{{source="{src}",result="{res}"}} {n}')
    return "\n".join(lines) + "\n"
