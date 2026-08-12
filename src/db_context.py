"""Request/session-scoped OCR5 database context."""
from __future__ import annotations

from contextvars import ContextVar
from supabase import Client

_client: ContextVar[Client | None] = ContextVar("ocr5_supabase_client", default=None)
_identity_email: ContextVar[str | None] = ContextVar("ocr5_identity_email", default=None)


def bind_client(client: Client) -> None:
    _client.set(client)


def get_bound_client() -> Client | None:
    return _client.get()


def bind_identity_email(email: str | None) -> None:
    _identity_email.set((email or "").strip().lower() or None)


def get_identity_email() -> str | None:
    return _identity_email.get()


def clear_client() -> None:
    _client.set(None)
    _identity_email.set(None)
