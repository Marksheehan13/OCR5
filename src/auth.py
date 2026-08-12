"""Authentication helpers for the OCR5 migration to a multi-user SaaS."""
from __future__ import annotations

import os
from supabase import Client, create_client


def _url() -> str:
    value = os.environ.get("SUPABASE_URL", "").strip()
    if not value:
        raise RuntimeError("SUPABASE_URL is not configured on the server.")
    return value


def _anon_key() -> str:
    value = os.environ.get("SUPABASE_KEY", "").strip()
    if not value:
        raise RuntimeError("SUPABASE_KEY is not configured on the server.")
    return value


def create_auth_client() -> Client:
    """Create a client intended for end-user authentication.

    This deliberately uses the public/anon key. Service-role credentials must
    never be shipped to the browser or used as an end-user credential.
    """
    return create_client(_url(), _anon_key())


def sign_up(email: str, password: str):
    return create_auth_client().auth.sign_up({"email": email.strip(), "password": password})


def sign_in(email: str, password: str):
    return create_auth_client().auth.sign_in_with_password({"email": email.strip(), "password": password})


def sign_out(client: Client) -> None:
    client.auth.sign_out()
