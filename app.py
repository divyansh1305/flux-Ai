"""Entry point for Vercel (it looks for a Flask object named `app` here)."""
from flux import create_app

app = create_app()
