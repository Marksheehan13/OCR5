"""Persist reviewed OCR5 invoice results and their source images."""

from __future__ import annotations

from .database import DatabaseError, save_invoice
from .models import InvoiceExtraction
from .storage import StorageError, upload_invoice_image
from supabase import create_client
import os


def _client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise DatabaseError("SUPABASE_URL and SUPABASE_KEY must be set.")
    return create_client(url, key)


def _number(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_overall_confidence(invoice: InvoiceExtraction) -> int:
    scores = [invoice.date.effective_confidence, invoice.supplier.effective_confidence, invoice.amount.effective_confidence]
    return round(sum(scores) / len(scores)) if scores else 0


def store_invoice_result(invoice: InvoiceExtraction, image_bytes: bytes | None = None, mime_type: str = "application/octet-stream"):
    image_path = invoice.source_file
    if image_bytes is not None:
        try:
            image_path = upload_invoice_image(image_bytes, invoice.source_file, mime_type)
        except StorageError as exc:
            raise DatabaseError(f"Invoice image could not be stored: {exc}") from exc

    confidence = calculate_overall_confidence(invoice)
    client = _client()
    response = client.table("invoices").insert({
        "supplier": invoice.supplier.value,
        "invoice_date": invoice.date.value,
        "amount": _number(invoice.amount.value),
        "currency": invoice.currency,
        "confidence": confidence,
        "image_path": image_path,
        "invoice_number": invoice.invoice_number.value,
        "subtotal": _number(invoice.subtotal.value),
        "vat_amount": _number(invoice.vat_amount.value),
        "vat_rate": _number(invoice.vat_rate.value),
    }).execute()

    if not response.data:
        raise DatabaseError("Invoice was not returned after saving.")
    invoice_id = response.data[0]["id"]

    if invoice.line_items:
        rows = []
        for item in invoice.line_items:
            rows.append({
                "invoice_id": invoice_id,
                "description": item.description,
                "quantity": _number(item.quantity),
                "unit_price": _number(item.unit_price),
                "vat_rate": _number(item.vat_rate),
                "line_total": _number(item.line_total),
                "confidence": max(0, min(100, int(item.confidence or 0))),
            })
        client.table("invoice_line_items").insert(rows).execute()

    return {"status": "saved", "invoice_id": invoice_id, "supplier": invoice.supplier.value, "amount": _number(invoice.amount.value), "confidence": confidence, "image_path": image_path, "line_items_saved": len(invoice.line_items)}
