"""Non-secret OCR5 application preferences.

Secrets are intentionally not written by this module. Deployment credentials
belong in Streamlit secrets or environment variables on the server.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

PROJECT_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE, override=False)


def get_setting(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def save_settings(*, provider: str) -> None:
    """Persist only non-secret preferences for local development."""
    os.environ["OCR5_PROVIDER"] = provider
