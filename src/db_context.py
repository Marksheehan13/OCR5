"""Request/session-scoped Supabase client context.

Streamlit reruns the script frequently. Keeping the authenticated Supabase
client in a ContextVar lets the persistence layer reuse the user's auth token
without creating an unauthenticated client for every query.
"""
from __future__ import annotations

from contextvars import ContextVar
from supabase import Client

_client: ContextVar[Client | None] = ContextVar("ocr5_supabase_client", default=None)


def bind_client(client: Client) -> None:
    _client.set(client)


def get_bound_client() -> Client | None:
    return _client.get()


def clear_client() -> None:
    _client.set(None)
