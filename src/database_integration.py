"""Persist reviewed OCR5 invoice results and their source images."""

from __future__ import annotations

from .database import save_invoice
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
):
    """Store an approved invoice and, when supplied, its actual source image."""
    amount = None
    if invoice.amount.value:
        try:
            amount = float(invoice.amount.value)
        except ValueError:
            amount = None

    image_path = invoice.source_file
    if image_bytes is not None:
        try:
            image_path = upload_invoice_image(image_bytes, invoice.source_file, mime_type)
        except StorageError as exc:
            raise StorageError(f"Invoice image could not be stored: {exc}") from exc

    confidence = calculate_overall_confidence(invoice)
    save_invoice(
        supplier=invoice.supplier.value,
        invoice_date=invoice.date.value,
        amount=amount,
        currency=invoice.currency,
        confidence=confidence,
        image_path=image_path,
    )

    return {
        "status": "saved",
        "supplier": invoice.supplier.value,
        "amount": amount,
        "confidence": confidence,
        "image_path": image_path,
    }
