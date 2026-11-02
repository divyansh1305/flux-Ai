# Flux – production image.  docker build -t flux . && docker run -p 8000:8000 --env-file .env -v flux-data:/data flux
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLUX_ENV=production \
    DATABASE_PATH=/data/flux.db \
    APP_TIMEZONE=Asia/Kolkata \
    PORT=8000

WORKDIR /app

# Dependencies first so code edits don't bust the pip cache layer
COPY requirements.txt ./
COPY packages ./packages
RUN pip install -r requirements.txt

COPY flux ./flux
COPY gunicorn.conf.py run.py ./

# Run as an unprivileged user; the DB lives on a volume
RUN useradd --create-home --uid 10001 flux && mkdir -p /data && chown flux /data
USER flux
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/readyz', timeout=2)"

CMD ["gunicorn", "-c", "gunicorn.conf.py", "flux:create_app()"]
