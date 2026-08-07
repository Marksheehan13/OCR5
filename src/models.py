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
    """The extracted value for one field, with the model's own confidence and reasoning."""

    value: str | None
    confidence: int             # 0-100, self-reported by the model
    reasons: list[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        if self.value is None:
            return "review"
        if self.confidence >= 90:
            return "high"
        if self.confidence >= 70:
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
        vals = [self.date.confidence, self.supplier.confidence, self.amount.confidence]
        return round(sum(vals) / len(vals))
