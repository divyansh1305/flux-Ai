"""Backups: consistent copy, retention, protected download."""
import os
import sqlite3

from flux import backup, create_app


def test_backup_copy_and_retention(tmp_path):
    db = tmp_path / "live.db"
    c = sqlite3.connect(db); c.execute("CREATE TABLE t (x)"); c.execute("INSERT INTO t VALUES (42)"); c.commit(); c.close()
    out = tmp_path / "b"
    for i in range(4):
        path = backup.backup_now(str(db), str(out), keep=2)
        os.utime(path, (i, i))
        os.rename(path, out / f"flux-2026010{i}-000000.db")
    files = sorted(os.listdir(out))
    assert len(files) <= 3
    assert sqlite3.connect(out / files[-1]).execute("SELECT x FROM t").fetchone()[0] == 42


def test_download_requires_token(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    monkeypatch.setenv("BACKUP_TOKEN", "t0ken-for-tests-1234")
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "f.db"), "SECRET_KEY": "x" * 40})
    c = app.test_client()
    assert c.get("/admin/backup/latest").status_code == 401
    assert c.get("/admin/backup/latest", headers={"Authorization": "Bearer t0ken-for-tests-1234"}).status_code == 404
    backup.backup_now(str(tmp_path / "f.db"), str(tmp_path / "bk"))
    r = c.get("/admin/backup/latest", headers={"Authorization": "Bearer t0ken-for-tests-1234"})
    assert r.status_code == 200 and r.data[:15] == b"SQLite format 3"
