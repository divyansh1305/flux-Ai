"""MOVED_TO sends every visit on the old address to the same page on the new one."""
from flux import create_app


def test_old_address_forwards_to_new_one(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_PATH": str(tmp_path / "t.db"), "MOVED_TO": "https://kitna.pythonanywhere.com"})
    r = app.test_client().get("/app/pay?amount=120", base_url="https://fluxai.pythonanywhere.com")
    assert r.status_code == 308 and r.headers["Location"] == "https://kitna.pythonanywhere.com/app/pay?amount=120"


def test_new_address_is_served_normally(tmp_path):
    app = create_app({"TESTING": True, "DATABASE_PATH": str(tmp_path / "t.db"), "MOVED_TO": "https://kitna.pythonanywhere.com"})
    assert app.test_client().get("/", base_url="https://kitna.pythonanywhere.com").status_code == 200
