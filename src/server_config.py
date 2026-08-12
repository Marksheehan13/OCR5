"""Server-side OCR5 configuration.

Secrets are read from deployment environment variables / Streamlit secrets only.
They must never be collected from end users through the application UI.
"""
from __future__ import annotations

import os
from typing import Optional

import streamlit as st


def _secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or "").strip() or os.environ.get(name, "").strip()


def get_server_secret(name: str, default: str = "") -> str:
    return _secret(name) or default


def get_ai_provider() -> str:
    return get_server_secret("OCR5_PROVIDER", "anthropic")


def get_ai_api_key(provider: Optional[str] = None) -> str:
    provider = provider or get_ai_provider()
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "gemini": "GOOGLE_API_KEY",
    }
    return get_server_secret(env_map.get(provider, "OCR5_API_KEY"))


def get_supabase_url() -> str:
    return get_server_secret("SUPABASE_URL")


def get_supabase_key() -> str:
    # Prefer the publishable/anon key for normal user-facing operations.
    return get_server_secret("SUPABASE_KEY") or get_server_secret("SUPABASE_ANON_KEY")


def validate_server_config() -> dict[str, bool]:
    return {
        "ai": bool(get_ai_api_key()),
        "supabase": bool(get_supabase_url() and get_supabase_key()),
    }
