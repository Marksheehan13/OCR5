"""
database_integration.py

Connects OCR5 extraction results with the SQLite memory database.

After Claude extracts invoice information,
this module stores the result permanently.
"""

from __future__ import annotations

from .database import save_invoice
from .models import InvoiceExtraction


def calculate_overall_confidence(invoice: InvoiceExtraction) -> int:
    """
    Calculates an overall confidence score
    from extracted fields.
    """

    scores = []

    if invoice.date:
        scores.append(invoice.date.confidence)

    if invoice.supplier:
        scores.append(invoice.supplier.confidence)

    if invoice.amount:
        scores.append(invoice.amount.confidence)

    if not scores:
        return 0

    return round(sum(scores) / len(scores))


def store_invoice_result(
    invoice: InvoiceExtraction,
):
    """
    Saves an OCR5 extraction result into the database.
    """

    amount = None

    if invoice.amount.value:
        try:
            amount = float(invoice.amount.value)
        except ValueError:
            amount = None


    confidence = calculate_overall_confidence(invoice)


    save_invoice(
        supplier=invoice.supplier.value,
        invoice_date=invoice.date.value,
        amount=amount,
        currency=invoice.currency,
        confidence=confidence,
        image_path=invoice.source_file,
    )


    return {
        "status": "saved",
        "supplier": invoice.supplier.value,
        "amount": amount,
        "confidence": confidence,
    }
