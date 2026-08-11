"""Detect likely duplicate invoices against approved invoice history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re


@dataclass(frozen=True)
class DuplicateMatch:
    invoice_id: int | str | None
    supplier: str | None
    invoice_date: str | None
    amount: float | None
    currency: str | None
    confidence: int | None
    score: int
    reasons: tuple[str, ...]


def _normalise_supplier(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _normalise_date(value: str | None) -> str:
    return (value or "").strip()


def _amount(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def find_duplicate_matches(
    supplier: str | None,
    invoice_date: str | None,
    amount: object,
    currency: str | None,
    existing_invoices: list[tuple],
) -> list[DuplicateMatch]:
    """Return likely duplicates, strongest matches first.

    A duplicate is only flagged when supplier, date, amount and currency all
    agree. Amounts are compared within one cent to tolerate numeric formatting.
    """
    new_supplier = _normalise_supplier(supplier)
    new_date = _normalise_date(invoice_date)
    new_amount = _amount(amount)
    new_currency = (currency or "").upper().strip()

    if not new_supplier or not new_date or new_amount is None or not new_currency:
        return []

    matches: list[DuplicateMatch] = []
    for row in existing_invoices:
        if len(row) < 8:
            continue
        row_id, row_supplier, row_date, row_amount, row_currency, row_confidence = row[:6]
        reasons: list[str] = []
        score = 0

        if _normalise_supplier(row_supplier) == new_supplier:
            score += 40
            reasons.append("supplier matches")
        else:
            continue

        if _normalise_date(row_date) == new_date:
            score += 30
            reasons.append("date matches")
        else:
            continue

        old_amount = _amount(row_amount)
        if old_amount is not None and abs(old_amount - new_amount) <= 0.01:
            score += 20
            reasons.append("amount matches")
        else:
            continue

        if (row_currency or "").upper().strip() == new_currency:
            score += 10
            reasons.append("currency matches")
        else:
            continue

        matches.append(
            DuplicateMatch(
                invoice_id=row_id,
                supplier=row_supplier,
                invoice_date=row_date,
                amount=old_amount,
                currency=row_currency,
                confidence=row_confidence,
                score=score,
                reasons=tuple(reasons),
            )
        )

    return sorted(matches, key=lambda match: match.score, reverse=True)
