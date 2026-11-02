"""Database backups.

* A daily backup runs inside the app (one background thread) when BACKUP_DIR is set.
  It uses SQLite's online backup API, so it's a consistent copy even while users are writing.
* Keeps the newest BACKUP_KEEP copies (default 14) and deletes older ones.
* Off-site copy: GET /admin/backup/latest with "Authorization: Bearer $BACKUP_TOKEN" streams the
  newest backup, so a GitHub Action (or your laptop) can pull a copy every day. Without
  BACKUP_TOKEN the endpoint does not exist.

Manual run:  python -m flux.backup            (uses DATABASE_PATH and BACKUP_DIR)
Restore:     stop the app, copy a backup file over DATABASE_PATH, start the app.
"""
import glob
import logging
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger("flux.backup")
_started = False


def backup_now(db_path, backup_dir, keep=14):
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(backup_dir, f"flux-{stamp}.db")
    tmp = dest + ".part"
    src = sqlite3.connect(db_path, timeout=30)
    try:
        out = sqlite3.connect(tmp)
        with out:
            src.backup(out)
        ok = out.execute("PRAGMA integrity_check").fetchone()[0]
        out.close()
    finally:
        src.close()
    if ok != "ok":
        os.remove(tmp)
        raise RuntimeError(f"backup failed integrity check: {ok}")
    os.replace(tmp, dest)
    for old in sorted(glob.glob(os.path.join(backup_dir, "flux-*.db")))[:-keep]:
        os.remove(old)
    log.info("backup written %s (%d bytes)", dest, os.path.getsize(dest))
    return dest


def latest(backup_dir):
    files = sorted(glob.glob(os.path.join(backup_dir, "flux-*.db")))
    return files[-1] if files else None


def _loop(db_path, backup_dir, keep, every_hours):
    while True:
        try:
            last = latest(backup_dir)
            age = time.time() - os.path.getmtime(last) if last else None
            if age is None or age >= every_hours * 3600:
                backup_now(db_path, backup_dir, keep)
        except Exception:  # never crash the web app because of a backup
            log.exception("backup failed")
        time.sleep(1800)  # check every 30 min; survives restarts because it looks at the newest file's age


def init_app(app):
    global _started
    backup_dir = os.environ.get("BACKUP_DIR")
    db_path = app.config["DATABASE"]
    token = os.environ.get("BACKUP_TOKEN")

    if token and backup_dir:
        from flask import Response, request, send_file

        @app.get("/admin/backup/latest")
        def download_backup():
            given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not secrets.compare_digest(given, token):
                return Response("unauthorized\n", 401, mimetype="text/plain")
            path = latest(backup_dir)
            if not path:
                return Response("no backup yet\n", 404, mimetype="text/plain")
            return send_file(path, as_attachment=True, download_name=os.path.basename(path))

    if backup_dir and db_path != ":memory:" and not app.config.get("TESTING") and not _started:
        _started = True
        keep = int(os.environ.get("BACKUP_KEEP", "14"))
        every = float(os.environ.get("BACKUP_EVERY_HOURS", "24"))
        threading.Thread(target=_loop, args=(db_path, backup_dir, keep, every), daemon=True, name="backup").start()
        log.info("daily backups on → %s (keep %d)", backup_dir, keep)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(backup_now(os.environ.get("DATABASE_PATH", "instance/flux.db"), os.environ.get("BACKUP_DIR", "backups")))
