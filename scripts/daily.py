"""Daily job for PythonAnywhere's one free scheduled task: back up the database, check Gmail for everyone,
send today's reminders, then work out yesterday's totals for the numbers page.

Schedule it for 03:15 UTC (8:45 am in India) so the morning reminder arrives before the day starts.

    cd ~/flux-ai && ~/.virtualenvs/flux/bin/python scripts/daily.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packages", "upi_parse", "src"))

from dotenv import load_dotenv  # noqa: E402

for f in (".env", os.path.expanduser("~/.env")):
    if os.path.exists(f):
        load_dotenv(f)
        break

from flux import analytics, backup, create_app, gmail, reminders  # noqa: E402

app = create_app()
db_path = app.config["DATABASE"]
backup_dir = os.environ.get("BACKUP_DIR") or os.path.join(os.path.dirname(db_path), "backups")
print("backup:", backup.backup_now(db_path, backup_dir))
with app.app_context():
    if gmail.configured():
        results = gmail.sync_all()
        print("gmail:", sum(r.get("logged", 0) for r in results), "payments added for", len(results), "accounts")
    print("reminders:", reminders.run_daily())
    print("numbers:", analytics.nightly())
