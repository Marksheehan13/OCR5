"""Persistent Supabase storage for OCR5 invoices."""

from __future__ import annotations

import os
from supabase import create_client, Client


class DatabaseError(Exception):
    """Raised when the database isn't configured or a request fails."""


def _get_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise DatabaseError("SUPABASE_URL and SUPABASE_KEY must be set.")
    return create_client(url, key)


def initialise_database() -> None:
    return None


def save_invoice(supplier, invoice_date, amount, currency, confidence, image_path, invoice_number=None, subtotal=None, vat_amount=None, vat_rate=None) -> None:
    client = _get_client()
    client.table("invoices").insert({
        "supplier": supplier, "invoice_date": invoice_date, "amount": amount,
        "currency": currency, "confidence": confidence, "image_path": image_path,
        "invoice_number": invoice_number, "subtotal": subtotal,
        "vat_amount": vat_amount, "vat_rate": vat_rate,
    }).execute()


def get_all_invoices() -> list[tuple]:
    client = _get_client()
    response = client.table("invoices").select(
        "id,supplier,invoice_date,amount,currency,confidence,image_path,created_at,invoice_number,subtotal,vat_amount,vat_rate"
    ).order("created_at", desc=True).execute()
    return [(
        r["id"], r["supplier"], r["invoice_date"], r["amount"], r["currency"],
        r["confidence"], r["image_path"], r["created_at"], r.get("invoice_number"),
        r.get("subtotal"), r.get("vat_amount"), r.get("vat_rate")
    ) for r in response.data]


def search_supplier(supplier: str) -> list[tuple]:
    client = _get_client()
    response = client.table("invoices").select(
        "id,supplier,invoice_date,amount,currency,confidence,image_path,created_at,invoice_number,subtotal,vat_amount,vat_rate"
    ).ilike("supplier", f"%{supplier}%").order("created_at", desc=True).execute()
    return [(
        r["id"], r["supplier"], r["invoice_date"], r["amount"], r["currency"],
        r["confidence"], r["image_path"], r["created_at"], r.get("invoice_number"),
        r.get("subtotal"), r.get("vat_amount"), r.get("vat_rate")
    ) for r in response.data]
