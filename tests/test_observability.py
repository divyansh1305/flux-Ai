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
