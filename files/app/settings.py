import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "app.db"
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DB_PATH}"

DB_USE_ALEMBIC = True

SESSION_SECRET = os.getenv("SESSION_SECRET", "CHANGE_ME_IN_PRODUCTION")
SESSION_COOKIE_NAME = "psmvp_session"