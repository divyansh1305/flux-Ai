"""Gunicorn settings. Used by Render, Docker and the load test: `gunicorn -c gunicorn.conf.py "flux:create_app()"`.

Why 1 worker x N threads: SQLite allows one writer at a time, and rate-limit + metrics state is
per process. Threads give concurrency for I/O (Gemini, email, Kite) while keeping one process.
Scale-out path: Postgres + Redis rate limiter, then raise `workers`.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_WORKERS", "1"))
threads = int(os.environ.get("WEB_THREADS", "8"))
worker_class = "gthread"
timeout = 30            # a request taking longer than this is a bug – kill it
graceful_timeout = 20
keepalive = 5
# Worker recycling is OFF by default: with a single worker every recycle is a brief outage and
# wipes the in-memory rate limiter + metrics (the load test caught 15 restarts/45s at 2000).
# Turn it on only with workers >= 2, e.g. MAX_REQUESTS=50000.
max_requests = int(os.environ.get("MAX_REQUESTS", "0"))
max_requests_jitter = max_requests // 10
accesslog = None        # Flux writes its own structured access log (flux.observability)
errorlog = "-"
forwarded_allow_ips = "*"   # behind Render's / Docker's proxy; ProxyFix trusts one hop
