"""Persistent local settings for OCR5.

Secrets are stored in the user's local .env file. The .env file is ignored by
Git and is never committed. Streamlit secrets/environment variables take
precedence when deployed.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, set_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE, override=False)


def get_setting(name: str, default: str = "") -> str:
    """Return a setting from the process environment."""
    return os.environ.get(name, default)


def save_settings(*, provider: str, api_key: str, supabase_url: str, supabase_key: str) -> None:
    """Persist credentials/settings to the local .env file."""
    ENV_FILE.touch(exist_ok=True)
    values = {
        "OCR5_PROVIDER": provider,
        "OCR5_API_KEY": api_key,
        "SUPABASE_URL": supabase_url,
        "SUPABASE_KEY": supabase_key,
    }
    for key, value in values.items():
        if value:
            set_key(str(ENV_FILE), key, value)
            os.environ[key] = value


def clear_saved_settings() -> None:
    """Remove locally persisted OCR5 credentials/settings."""
    if ENV_FILE.exists():
        ENV_FILE.unlink()
    for key in ("OCR5_PROVIDER", "OCR5_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"):
        os.environ.pop(key, None)
