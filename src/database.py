"""
database.py

Persistent storage layer for OCR5, backed by Supabase (Postgres).
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime

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
    return None


def save_invoice(supplier: str | None, invoice_date: str | None, amount: float | None, currency: str, confidence: int, image_path: str, invoice_number: str | None = None, subtotal: float | None = None, vat_amount: float | None = None, vat_rate: float | None = None) -> int:
    response = _get_client().table("invoices").insert({
        "supplier": supplier, "invoice_date": invoice_date, "amount": amount, "currency": currency,
        "confidence": confidence, "image_path": image_path, "invoice_number": invoice_number,
        "subtotal": subtotal, "vat_amount": vat_amount, "vat_rate": vat_rate,
    }).execute()
    if not response.data:
        raise DatabaseError("Invoice was not returned after saving.")
    return response.data[0]["id"]


def save_invoice_line_items(invoice_id: int, line_items) -> int:
    if not line_items:
        return 0
    def number(value):
        if value in (None, "", "null"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    rows = [{
        "invoice_id": invoice_id, "description": item.description, "quantity": number(item.quantity),
        "unit_price": number(item.unit_price), "vat_rate": number(item.vat_rate),
        "line_total": number(item.line_total), "confidence": max(0, min(100, int(item.confidence or 0))),
    } for item in line_items]
    _get_client().table("invoice_line_items").insert(rows).execute()
    return len(rows)


def get_invoice_line_items(invoice_id: int) -> list[dict]:
    response = _get_client().table("invoice_line_items").select(
        "id,description,quantity,unit_price,vat_rate,line_total,confidence,created_at"
    ).eq("invoice_id", invoice_id).order("id").execute()
    return response.data or []


def get_all_invoice_line_items() -> list[dict]:
    response = _get_client().table("invoice_line_items").select(
        "id,invoice_id,description,quantity,unit_price,vat_rate,line_total,confidence,created_at"
    ).order("created_at", desc=True).execute()
    return response.data or []


def get_invoice_analytics() -> dict:
    """Return database-backed invoice and line-item aggregates."""
    invoices = get_all_invoices()
    items = get_all_invoice_line_items()
    valid_amounts = [float(row[3]) for row in invoices if row[3] is not None]
    valid_vat = [float(row[10]) for row in invoices if row[10] is not None]

    by_supplier = defaultdict(float)
    by_month = defaultdict(float)
    for row in invoices:
        amount = row[3]
        if amount is None:
            continue
        amount = float(amount)
        supplier = row[1] or "Unknown supplier"
        by_supplier[supplier] += amount
        date_value = row[2]
        if date_value:
            month = str(date_value)[:7]
            by_month[month] += amount

    return {
        "invoice_count": len(invoices),
        "line_item_count": len(items),
        "total_spend": sum(valid_amounts),
        "total_vat": sum(valid_vat),
        "average_invoice_value": sum(valid_amounts) / len(valid_amounts) if valid_amounts else 0.0,
        "spend_by_supplier": dict(sorted(by_supplier.items(), key=lambda x: x[1], reverse=True)),
        "spend_by_month": dict(sorted(by_month.items())),
    }


_COLUMNS = "id,supplier,invoice_date,amount,currency,confidence,image_path,created_at,invoice_number,subtotal,vat_amount,vat_rate"


def _rows(response) -> list[tuple]:
    return [(row["id"], row["supplier"], row["invoice_date"], row["amount"], row["currency"], row["confidence"], row["image_path"], row["created_at"], row.get("invoice_number"), row.get("subtotal"), row.get("vat_amount"), row.get("vat_rate")) for row in response.data]


def get_all_invoices() -> list[tuple]:
    response = _get_client().table("invoices").select(_COLUMNS).order("created_at", desc=True).execute()
    return _rows(response)


def search_supplier(supplier: str) -> list[tuple]:
    response = _get_client().table("invoices").select(_COLUMNS).ilike("supplier", f"%{supplier}%").order("created_at", desc=True).execute()
    return _rows(response)


if __name__ == "__main__":
    initialise_database()
    print("OCR5 database is ready (Supabase-backed, table created via migration).")
