"""
models.py

Shared data structures. Much simpler than OCR4's models.py -- there's
no OcrPass / FieldCandidate pooling here, because extraction is one
LLM call per invoice rather than 16 heuristically-scored OCR passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FieldResult:
    """An extracted value with model confidence and independent validation."""

    value: str | None
    confidence: int             # raw, self-reported model confidence (0-100)
    reasons: list[str] = field(default_factory=list)
    validation_confidence: int | None = None
    validation_issues: list[str] = field(default_factory=list)

    @property
    def effective_confidence(self) -> int:
        """Confidence after deterministic validation has been applied."""
        if self.validation_confidence is None:
            return self.confidence
        return min(self.confidence, self.validation_confidence)

    @property
    def level(self) -> str:
        confidence = self.effective_confidence
        if self.value is None:
            return "review"
        if self.validation_issues:
            return "review"
        if confidence >= 90:
            return "high"
        if confidence >= 70:
            return "medium"
        return "review"


@dataclass
class InvoiceExtraction:
    """Full extraction result for one invoice image."""

    source_file: str
    date: FieldResult
    supplier: FieldResult
    amount: FieldResult
    currency: str = "EUR"
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""          # the model's full response, kept for debugging/export
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
        vals = [
            self.date.effective_confidence,
            self.supplier.effective_confidence,
            self.amount.effective_confidence,
        ]
        return round(sum(vals) / len(vals))
