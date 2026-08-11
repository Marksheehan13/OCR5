"""Shared data structures for OCR5 invoice extraction."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FieldResult:
    value: str | None
    confidence: int
    reasons: list[str] = field(default_factory=list)
    validation_confidence: int | None = None
    validation_issues: list[str] = field(default_factory=list)

    @property
    def effective_confidence(self) -> int:
        if self.validation_confidence is None:
            return self.confidence
        return min(self.confidence, self.validation_confidence)

    @property
    def level(self) -> str:
        confidence = self.effective_confidence
        if self.value is None or self.validation_issues:
            return "review"
        if confidence >= 90:
            return "high"
        if confidence >= 70:
            return "medium"
        return "review"


@dataclass
class InvoiceExtraction:
    source_file: str
    date: FieldResult
    supplier: FieldResult
    amount: FieldResult
    currency: str = "EUR"
    invoice_number: FieldResult = field(default_factory=lambda: FieldResult(None, 0))
    subtotal: FieldResult = field(default_factory=lambda: FieldResult(None, 0))
    vat_amount: FieldResult = field(default_factory=lambda: FieldResult(None, 0))
    vat_rate: FieldResult = field(default_factory=lambda: FieldResult(None, 0))
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""
    validation_warnings: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return (
            self.date.level == "review"
            or self.supplier.level == "review"
            or self.amount.level == "review"
            or bool(self.warnings)
        )

    @property
    def overall_confidence(self) -> int:
        vals = [self.date.effective_confidence, self.supplier.effective_confidence, self.amount.effective_confidence]
        return round(sum(vals) / len(vals))
