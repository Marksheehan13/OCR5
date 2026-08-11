"""Local configuration helpers for OCR5.

Secrets are loaded from environment variables / Streamlit secrets. For local use,
OCR5 can persist credentials in a .env file that is ignored by Git. Nothing from
that file is committed to the repository.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, set_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Load local .env values before the app reads configuration.
load_dotenv(ENV_FILE, override=False)


def get_env(name: str, default: str = "") -> str:
    """Return an environment value, falling back to an empty/default value."""
    return os.environ.get(name, default)


def save_local_setting(name: str, value: str) -> None:
    """Persist one setting to the local .env file and current process."""
    ENV_FILE.touch(exist_ok=True)
    set_key(str(ENV_FILE), name, value)
    os.environ[name] = value


def local_env_exists() -> bool:
    return ENV_FILE.exists()
