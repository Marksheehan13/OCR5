"""Authentication and workspace helpers for OCR5."""
from __future__ import annotations

import os
from supabase import Client, create_client
from .db_context import bind_client, clear_client, get_identity_email


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
    return client.auth.get_session()


def get_workspace(email: str) -> dict | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    admin = create_auth_client()
    rows = admin.table("organization_identities").select("email,organization_id,display_name,company_name").eq("email", email).limit(1).execute().data
    return rows[0] if rows else None


def ensure_workspace(email: str, display_name: str = "", company_name: str = "") -> dict:
    """Create or return the workspace associated with a Streamlit OIDC identity."""
    email = (email or "").strip().lower()
    display_name = (display_name or "").strip()
    company_name = (company_name or "").strip()
    if not email:
        raise RuntimeError("Google did not provide an email address.")

    admin = create_auth_client()
    existing = get_workspace(email)
    if existing:
        updates = {}
        if display_name and not existing.get("display_name"): updates["display_name"] = display_name
        if company_name and not existing.get("company_name"): updates["company_name"] = company_name
        if updates:
            admin.table("organization_identities").update(updates).eq("email", email).execute()
            existing.update(updates)
        return existing

    org_name = company_name or (f"{display_name}'s workspace" if display_name else "OCR5 workspace")
    org = admin.table("organizations").insert({"name": org_name}).execute()
    if not org.data:
        raise RuntimeError("OCR5 could not create your workspace.")
    org_id = org.data[0]["id"]
    row = {"email": email, "organization_id": org_id, "display_name": display_name or None, "company_name": company_name or None}
    try:
        result = admin.table("organization_identities").insert(row).execute()
        if not result.data:
            raise RuntimeError("OCR5 could not save your workspace.")
        return result.data[0]
    except Exception:
        admin.table("organizations").delete().eq("id", org_id).execute()
        raise


def organisation_id(client: Client) -> str | None:
    """Return the organisation for either Supabase Auth or Streamlit OIDC."""
    email = get_identity_email()
    if email:
        response = client.table("organization_identities").select("organization_id").eq("email", email).limit(1).execute()
        if response.data:
            return response.data[0]["organization_id"]

    user = getattr(client.auth.get_user(), "user", None)
    if not user:
        return None
    response = client.table("organization_members").select("organization_id").eq("user_id", user.id).limit(1).execute()
    return response.data[0]["organization_id"] if response.data else None
