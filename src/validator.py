"""Deterministic validation for LLM-extracted invoice fields.

The LLM's self-reported confidence is useful context, but it is not an
independent measure of correctness. This module performs cheap structural
checks after extraction and produces an effective confidence cap plus
human-readable validation issues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re

from .models import FieldResult, InvoiceExtraction


@dataclass
class ValidationResult:
    """Result of deterministic validation for one extracted field."""

    confidence_cap: int = 100
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues


def validate_date(field: FieldResult) -> ValidationResult:
    if field.value is None:
        return ValidationResult(0, ["Date is missing."])

    value = field.value.strip()
    try:
        datetime.strptime(value, "%d/%m/%Y")
    except ValueError:
        return ValidationResult(40, ["Date is not in valid DD/MM/YYYY format."])

    return ValidationResult()


def validate_amount(field: FieldResult) -> ValidationResult:
    if field.value is None:
        return ValidationResult(0, ["Amount is missing."])

    value = field.value.strip().replace(",", "")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return ValidationResult(40, ["Amount is not a valid number."])

    if amount < 0:
        return ValidationResult(30, ["Amount cannot be negative."])

    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", value):
        return ValidationResult(80, ["Amount should contain at most two decimal places."])

    return ValidationResult()


def validate_supplier(field: FieldResult) -> ValidationResult:
    if field.value is None:
        return ValidationResult(0, ["Supplier is missing."])

    value = " ".join(field.value.split())
    if len(value) < 2:
        return ValidationResult(30, ["Supplier name is too short to be reliable."])
    if len(value) > 200:
        return ValidationResult(70, ["Supplier name is unusually long."])

    return ValidationResult()


def validate_currency(currency: str | None) -> ValidationResult:
    if not currency:
        return ValidationResult(50, ["Currency is missing."])
    if not re.fullmatch(r"[A-Z]{3}", currency):
        return ValidationResult(50, ["Currency is not a valid three-letter code."])
    return ValidationResult()


def _apply_validation(field: FieldResult, result: ValidationResult) -> None:
    """Attach validation information and cap, rather than replace, model confidence."""
    field.validation_confidence = min(field.confidence, result.confidence_cap)
    field.validation_issues = result.issues


def validate_extraction(result: InvoiceExtraction) -> InvoiceExtraction:
    """Run deterministic checks and update effective confidence on the result."""
    _apply_validation(result.date, validate_date(result.date))
    _apply_validation(result.supplier, validate_supplier(result.supplier))
    _apply_validation(result.amount, validate_amount(result.amount))

    currency_result = validate_currency(result.currency)
    result.validation_warnings = list(currency_result.issues)

    if result.validation_warnings:
        result.warnings.extend(result.validation_warnings)

    return result
