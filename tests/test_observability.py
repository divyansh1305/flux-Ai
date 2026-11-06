"""Request IDs, metrics and readiness."""


def test_request_id_is_generated_or_propagated(client):
    r = client.get("/healthz")
    assert len(r.headers["X-Request-ID"]) == 32
    r = client.get("/healthz", headers={"X-Request-ID": "edge-proxy-1234"})
    assert r.headers["X-Request-ID"] == "edge-proxy-1234"
    r = client.get("/healthz", headers={"X-Request-ID": "bad id <script>"})
    assert r.headers["X-Request-ID"] != "bad id <script>"


def test_metrics_counts_routes_by_template_not_raw_path(client, user):
    client.get("/api/dashboard")
    client.get("/api/transactions/999999")  # unknown id → route template, not the number
    text = client.get("/metrics").get_data(as_text=True)
    assert 'flux_http_requests_total{method="GET",route="/api/dashboard",status="200"}' in text
    assert "999999" not in text
    assert 'flux_http_request_duration_seconds_bucket{route="/api/dashboard",le="+Inf"}' in text


def test_metrics_requires_token_when_set(client, monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "s3cret-metrics")
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer s3cret-metrics"}).status_code == 200


def test_ingest_outcomes_are_counted(app, client, user):
    t = client.post("/api/ingest/token").json["token"]
    phone = app.test_client()
    phone.post("/api/ingest/sms", json={"text": "Your OTP is 445566"}, headers={"Authorization": f"Bearer {t}"})
    text = client.get("/metrics").get_data(as_text=True)
    assert 'flux_ingest_total{source="sms",result="skipped"}' in text


def test_readyz(client):
    assert client.get("/readyz").json == {"ok": True, "db": "up"}


def test_static_files_are_versioned_cached_and_compressed(client):
    import re

    html = client.get("/login").get_data(as_text=True)
    css = re.search(r'href="(/static/css/app\.css\?v=[0-9a-f]{12})"', html).group(1)
    r = client.get(css, headers={"Accept-Encoding": "gzip, br"})
    assert r.status_code == 200 and "immutable" in r.headers["Cache-Control"]
    assert r.headers["Content-Encoding"] == "gzip" and int(r.headers["Content-Length"]) < 20000  # TODO: consolidate app.css (stacked theme passes)
    import gzip

    assert b".btn" in gzip.decompress(r.data)
    # Without the version (or with an old one) the browser must re-check, so updates show up at once.
    assert client.get("/static/css/app.css?v=old").headers["Cache-Control"] == "no-cache"


def test_service_worker_lists_the_app_shell(client):
    r = client.get("/sw.js")
    assert r.status_code == 200 and r.mimetype == "application/javascript"
    js = r.get_data(as_text=True)
    assert '"/app"' in js and '"/app/plans"' in js and "/static/js/core.js?v=" in js
    assert "/api/" not in js.split("const SHELL")[1].split("\n")[0]  # data is never cached by the worker
    assert r.headers["Cache-Control"] == "no-cache"
