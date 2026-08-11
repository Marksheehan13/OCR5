"""
database.py

Persistent storage layer for OCR5, backed by Supabase (Postgres).
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
    """No-op: the Supabase table is managed separately."""
    return None


def save_invoice(
    supplier: str | None,
    invoice_date: str | None,
    amount: float | None,
    currency: str,
    confidence: int,
    image_path: str,
    invoice_number: str | None = None,
    subtotal: float | None = None,
    vat_amount: float | None = None,
    vat_rate: float | None = None,
) -> int:
    """Save an approved invoice and return its database id."""
    client = _get_client()
    response = client.table("invoices").insert({
        "supplier": supplier,
        "invoice_date": invoice_date,
        "amount": amount,
        "currency": currency,
        "confidence": confidence,
        "image_path": image_path,
        "invoice_number": invoice_number,
        "subtotal": subtotal,
        "vat_amount": vat_amount,
        "vat_rate": vat_rate,
    }).execute()
    if not response.data:
        raise DatabaseError("Invoice was not returned after saving.")
    return response.data[0]["id"]


def save_invoice_line_items(invoice_id: int, line_items) -> int:
    """Save the reviewed line items belonging to an invoice."""
    if not line_items:
        return 0

    def number(value):
        if value in (None, "", "null"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    rows = [
        {
            "invoice_id": invoice_id,
            "description": item.description,
            "quantity": number(item.quantity),
            "unit_price": number(item.unit_price),
            "vat_rate": number(item.vat_rate),
            "line_total": number(item.line_total),
            "confidence": max(0, min(100, int(item.confidence or 0))),
        }
        for item in line_items
    ]
    _get_client().table("invoice_line_items").insert(rows).execute()
    return len(rows)


def get_invoice_line_items(invoice_id: int) -> list[dict]:
    """Return line items for one invoice, preserving stored order."""
    response = (
        _get_client()
        .table("invoice_line_items")
        .select("id,description,quantity,unit_price,vat_rate,line_total,confidence,created_at")
        .eq("invoice_id", invoice_id)
        .order("id")
        .execute()
    )
    return response.data or []


def get_all_invoice_line_items() -> list[dict]:
    """Return all stored line items for later reporting/analytics."""
    response = (
        _get_client()
        .table("invoice_line_items")
        .select("id,invoice_id,description,quantity,unit_price,vat_rate,line_total,confidence,created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


_COLUMNS = (
    "id,supplier,invoice_date,amount,currency,confidence,image_path,created_at,"
    "invoice_number,subtotal,vat_amount,vat_rate"
)


def _rows(response) -> list[tuple]:
    return [
        (
            row["id"], row["supplier"], row["invoice_date"], row["amount"],
            row["currency"], row["confidence"], row["image_path"], row["created_at"],
            row.get("invoice_number"), row.get("subtotal"), row.get("vat_amount"),
            row.get("vat_rate"),
        )
        for row in response.data
    ]


def get_all_invoices() -> list[tuple]:
    """Return all stored invoices, newest first."""
    client = _get_client()
    response = client.table("invoices").select(_COLUMNS).order("created_at", desc=True).execute()
    return _rows(response)


def search_supplier(supplier: str) -> list[tuple]:
    """Find previous invoices from a matching supplier."""
    client = _get_client()
    response = (
        client.table("invoices")
        .select(_COLUMNS)
        .ilike("supplier", f"%{supplier}%")
        .order("created_at", desc=True)
        .execute()
    )
    return _rows(response)


if __name__ == "__main__":
    initialise_database()
    print("OCR5 database is ready (Supabase-backed, table created via migration).")
