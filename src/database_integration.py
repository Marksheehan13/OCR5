"""Persist reviewed OCR5 invoice results and their source images."""

from __future__ import annotations

from .database import DatabaseError, save_invoice, save_invoice_line_items
from .models import InvoiceExtraction
from .storage import StorageError, upload_invoice_image


def calculate_overall_confidence(invoice: InvoiceExtraction) -> int:
    scores = [
        invoice.date.effective_confidence,
        invoice.supplier.effective_confidence,
        invoice.amount.effective_confidence,
    ]
    return round(sum(scores) / len(scores)) if scores else 0


def store_invoice_result(
    invoice: InvoiceExtraction,
    image_bytes: bytes | None = None,
    mime_type: str = "application/octet-stream",
    client_id: int | None = None,
):
    """Store an approved invoice and its reviewed line items for a client."""
    if client_id is None:
        raise DatabaseError("Select a client before saving an invoice.")

    image_path = invoice.source_file
    if image_bytes is not None:
        try:
            image_path = upload_invoice_image(image_bytes, invoice.source_file, mime_type)
        except StorageError as exc:
            raise DatabaseError(f"Invoice image could not be stored: {exc}") from exc

    confidence = calculate_overall_confidence(invoice)
    invoice_id = save_invoice(
        supplier=invoice.supplier.value,
        invoice_date=invoice.date.value,
        amount=_number(invoice.amount.value),
        currency=invoice.currency,
        confidence=confidence,
        image_path=image_path,
        invoice_number=invoice.invoice_number.value,
        subtotal=_number(invoice.subtotal.value),
        vat_amount=_number(invoice.vat_amount.value),
        vat_rate=_number(invoice.vat_rate.value),
        client_id=client_id,
    )
    line_items_saved = save_invoice_line_items(invoice_id, invoice.line_items)

    return {
        "status": "saved",
        "invoice_id": invoice_id,
        "client_id": client_id,
        "supplier": invoice.supplier.value,
        "amount": _number(invoice.amount.value),
        "confidence": confidence,
        "image_path": image_path,
        "line_items_saved": line_items_saved,
    }


def _number(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
