"""Authentication helpers for OCR5 multi-user SaaS mode."""
from __future__ import annotations

import os
from supabase import Client, create_client
from .db_context import bind_client, clear_client


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
    return create_client(_url(), _anon_key())


def sign_up(email: str, password: str):
    client = create_auth_client()
    response = client.auth.sign_up({"email": email.strip(), "password": password})
    if response.session:
        bind_client(client)
    return client, response


def sign_in(email: str, password: str):
    client = create_auth_client()
    response = client.auth.sign_in_with_password({"email": email.strip(), "password": password})
    bind_client(client)
    return client, response


def sign_out(client: Client) -> None:
    try:
        client.auth.sign_out()
    finally:
        clear_client()


def current_session(client: Client):
    """Return the current auth session, if one exists."""
    return client.auth.get_session()


def organisation_id(client: Client) -> str | None:
    """Return the organisation belonging to the current authenticated user."""
    user = getattr(client.auth.get_user(), "user", None)
    if not user:
        return None
    response = (
        client.table("organization_members")
        .select("organization_id")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    return response.data[0]["organization_id"] if response.data else None
