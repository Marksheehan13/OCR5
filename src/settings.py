"""Persistent local settings for OCR5."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, set_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE, override=False)


def get_setting(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def save_settings(*, provider: str, api_key: str, supabase_url: str, supabase_key: str) -> None:
    ENV_FILE.touch(exist_ok=True)
    for key, value in {
        "OCR5_PROVIDER": provider,
        "OCR5_API_KEY": api_key,
        "SUPABASE_URL": supabase_url,
        "SUPABASE_KEY": supabase_key,
    }.items():
        set_key(str(ENV_FILE), key, value)
        os.environ[key] = value
