"""
database.py

Persistent storage layer for OCR5, backed by Supabase (Postgres).

This replaces an earlier SQLite version. SQLite wrote to a local file
on disk, which works fine locally but doesn't actually persist on
Streamlit Cloud -- its filesystem resets on every redeploy and
periodically on its own, silently wiping out anything stored there.
Supabase is an external hosted database, so it survives redeploys,
restarts, and app sleep/wake cycles.

Requires two values (from your Supabase project's Settings -> API):
  SUPABASE_URL          e.g. https://xxxxx.supabase.co
  SUPABASE_KEY           the project's anon/publishable key

Set these as environment variables (CLI) or Streamlit secrets (web UI),
same pattern as the LLM provider API keys.

Table schema (see the migration this was created with):
    invoices (
        id bigint primary key,
        supplier text,
        invoice_date text,
        amount numeric,
        currency text,
        confidence integer,
        image_path text,
        created_at timestamptz
    )

Note on access control: row-level security is enabled with a permissive
"allow all" policy, appropriate for a single-user portfolio project
using the anon key directly from the browser/app. If you extend this
to multiple users, replace that policy with real per-user access rules.
"""

from __future__ import annotations

import os

from supabase import create_client, Client


class DatabaseError(Exception):
    """Raised when the database isn't configured or a request fails."""


def _get_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise DatabaseError(
            "SUPABASE_URL and SUPABASE_KEY must be set (environment variables for the "
            "CLI, or Streamlit secrets for the web UI) to use invoice history storage."
        )
    return create_client(url, key)


def initialise_database() -> None:
    """
    No-op kept for interface compatibility with the previous SQLite
    version -- the table is created once via a migration, not on every
    app startup. Calling this is safe and does nothing.
    """
    return None


def save_invoice(
    supplier: str | None,
    invoice_date: str | None,
    amount: float | None,
    currency: str,
    confidence: int,
    image_path: str,
) -> None:
    """Saves an extracted invoice into the database."""
    client = _get_client()
    client.table("invoices").insert(
        {
            "supplier": supplier,
            "invoice_date": invoice_date,
            "amount": amount,
            "currency": currency,
            "confidence": confidence,
            "image_path": image_path,
        }
    ).execute()


def get_all_invoices() -> list[tuple]:
    """
    Returns all stored invoices as a list of tuples, in the same
    column order as the previous SQLite version
    (id, supplier, invoice_date, amount, currency, confidence,
    image_path, created_at), so pages/invoice_history.py didn't need
    to change when this was swapped out.
    """
    client = _get_client()
    response = (
        client.table("invoices")
        .select("id,supplier,invoice_date,amount,currency,confidence,image_path,created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return [
        (
            row["id"],
            row["supplier"],
            row["invoice_date"],
            row["amount"],
            row["currency"],
            row["confidence"],
            row["image_path"],
            row["created_at"],
        )
        for row in response.data
    ]


def search_supplier(supplier: str) -> list[tuple]:
    """Finds previous invoices from a matching supplier (case-insensitive substring)."""
    client = _get_client()
    response = (
        client.table("invoices")
        .select("id,supplier,invoice_date,amount,currency,confidence,image_path,created_at")
        .ilike("supplier", f"%{supplier}%")
        .order("created_at", desc=True)
        .execute()
    )
    return [
        (
            row["id"],
            row["supplier"],
            row["invoice_date"],
            row["amount"],
            row["currency"],
            row["confidence"],
            row["image_path"],
            row["created_at"],
        )
        for row in response.data
    ]


if __name__ == "__main__":
    initialise_database()
    print("OCR5 database is ready (Supabase-backed, table created via migration).")
