"""Gemini REST wrapper: request shape, success, and graceful failure."""
from flux import ai


class FakeResp:
    def __init__(self, code, data):
        self.status_code, self._d, self.text = code, data, str(data)

    def json(self):
        return self._d


def test_generate_sends_key_header_and_parses_text(app, monkeypatch):
    seen = {}

    def post(url, json, timeout, headers):
        seen.update(url=url, body=json, headers=headers)
        return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": "Save ₹500 "}, {"text": "on food."}]}}]})

    monkeypatch.setattr(ai._session, "post", post)
    with app.app_context():
        app.config["GEMINI_API_KEY"] = "AQ.test-key"
        assert ai.available()
        assert ai.generate("hi", system="be brief") == "Save ₹500 on food."
    assert seen["headers"]["x-goog-api-key"] == "AQ.test-key"
    assert "key=" not in seen["url"]                       # key never in the URL (no leaks in logs)
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "be brief"


def test_generate_returns_none_on_error_so_app_falls_back(app, monkeypatch):
    monkeypatch.setattr(ai._session, "post", lambda *a, **k: FakeResp(401, {"error": "bad key"}))
    with app.app_context():
        app.config["GEMINI_API_KEY"] = "AQ.bad"
        assert ai.generate("hi") is None
        app.config["GEMINI_API_KEY"] = ""
        assert not ai.available() and ai.generate("hi") is None
