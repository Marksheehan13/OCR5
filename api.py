"""OCR5 standalone web API.

This module is a thin HTTP adapter around the existing OCR5 business logic.
It intentionally does not reimplement extraction, validation, duplicate detection,
or persistence. The existing modules remain the source of truth.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.database import DatabaseError, get_all_invoices, get_invoice_analytics
from src.database_integration import store_invoice_result
from src.duplicate_detector import find_duplicate_matches
from src.llm_extractor import DEFAULT_PROVIDER, PROVIDERS, ExtractionError, extract_invoice
from src.models import FieldResult, InvoiceExtraction, LineItem

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title="OCR5 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FieldPayload(BaseModel):
    value: str | None = None
    confidence: int = 0
    reasons: list[str] = Field(default_factory=list)
    validation_confidence: int | None = None
    validation_issues: list[str] = Field(default_factory=list)


class LineItemPayload(BaseModel):
    description: str = ""
    quantity: str | None = None
    unit_price: str | None = None
    vat_rate: str | None = None
    line_total: str | None = None
    confidence: int = 0
    warnings: list[str] = Field(default_factory=list)


class InvoicePayload(BaseModel):
    source_file: str
    date: FieldPayload
    supplier: FieldPayload
    amount: FieldPayload
    currency: str = "EUR"
    invoice_number: FieldPayload = Field(default_factory=FieldPayload)
    subtotal: FieldPayload = Field(default_factory=FieldPayload)
    vat_amount: FieldPayload = Field(default_factory=FieldPayload)
    vat_rate: FieldPayload = Field(default_factory=FieldPayload)
    line_items: list[LineItemPayload] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_text: str = ""
    validation_warnings: list[str] = Field(default_factory=list)


def _field(payload: FieldPayload) -> FieldResult:
    return FieldResult(
        value=payload.value,
        confidence=max(0, min(100, payload.confidence)),
        reasons=payload.reasons,
        validation_confidence=payload.validation_confidence,
        validation_issues=payload.validation_issues,
    )


def _invoice(payload: InvoicePayload) -> InvoiceExtraction:
    return InvoiceExtraction(
        source_file=payload.source_file,
        date=_field(payload.date),
        supplier=_field(payload.supplier),
        amount=_field(payload.amount),
        currency=payload.currency or "EUR",
        invoice_number=_field(payload.invoice_number),
        subtotal=_field(payload.subtotal),
        vat_amount=_field(payload.vat_amount),
        vat_rate=_field(payload.vat_rate),
        line_items=[LineItem(**item.model_dump()) for item in payload.line_items],
        warnings=payload.warnings,
        raw_text=payload.raw_text,
        validation_warnings=payload.validation_warnings,
    )


def _field_json(field: FieldResult) -> dict[str, Any]:
    return {
        "value": field.value,
        "confidence": field.effective_confidence,
        "level": field.level,
        "reasons": field.reasons,
        "validation_issues": field.validation_issues,
    }


def _invoice_json(invoice: InvoiceExtraction) -> dict[str, Any]:
    return {
        "source_file": invoice.source_file,
        "date": _field_json(invoice.date),
        "supplier": _field_json(invoice.supplier),
        "amount": _field_json(invoice.amount),
        "currency": invoice.currency,
        "invoice_number": _field_json(invoice.invoice_number),
        "subtotal": _field_json(invoice.subtotal),
        "vat_amount": _field_json(invoice.vat_amount),
        "vat_rate": _field_json(invoice.vat_rate),
        "line_items": [
            {
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "vat_rate": item.vat_rate,
                "line_total": item.line_total,
                "confidence": item.confidence,
                "warnings": item.warnings,
            }
            for item in invoice.line_items
        ],
        "warnings": invoice.warnings,
        "validation_warnings": invoice.validation_warnings,
        "needs_review": invoice.needs_review,
        "overall_confidence": invoice.overall_confidence,
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ocr5"}


@app.get("/api/providers")
def providers() -> dict[str, Any]:
    return {
        "default": DEFAULT_PROVIDER,
        "providers": [
            {"name": name, "model": config["model"]}
            for name, config in PROVIDERS.items()
        ],
    }


@app.post("/api/extract")
async def extract(
    file: UploadFile = File(...),
    x_ocr5_api_key: str | None = Header(default=None),
    x_ocr5_provider: str = Header(default=DEFAULT_PROVIDER),
) -> dict[str, Any]:
    if x_ocr5_provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{x_ocr5_provider}'.")
    api_key = x_ocr5_api_key or os.environ.get(PROVIDERS[x_ocr5_provider]["env_var"])
    if not api_key:
        raise HTTPException(status_code=400, detail="No AI API key supplied.")

    suffix = Path(file.filename or "invoice.jpg").suffix or ".jpg"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        result = extract_invoice(tmp_path, api_key=api_key, provider=x_ocr5_provider)
        result.source_file = file.filename or "invoice"
        return {"invoice": _invoice_json(result)}
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR5 extraction failed: {exc}") from exc
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass


@app.post("/api/invoices/check-duplicates")
def check_duplicates(payload: InvoicePayload) -> dict[str, Any]:
    try:
        history = get_all_invoices()
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    invoice = _invoice(payload)
    matches = find_duplicate_matches(
        invoice.supplier.value,
        invoice.date.value,
        invoice.amount.value,
        invoice.currency,
        history,
    )
    return {
        "matches": [
            {
                "invoice_id": match.invoice_id,
                "supplier": match.supplier,
                "invoice_date": match.invoice_date,
                "amount": match.amount,
                "currency": match.currency,
                "score": getattr(match, "score", None),
            }
            for match in matches
        ]
    }


@app.post("/api/invoices/save")
def save_invoice(payload: InvoicePayload) -> dict[str, Any]:
    try:
        return store_invoice_result(_invoice(payload))
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/invoices")
def invoices() -> dict[str, Any]:
    try:
        rows = get_all_invoices()
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "invoices": [
            {
                "id": row[0],
                "supplier": row[1],
                "date": row[2],
                "amount": row[3],
                "currency": row[4],
                "confidence": row[5],
                "image_path": row[6],
                "created_at": row[7],
                "invoice_number": row[8],
                "subtotal": row[9],
                "vat_amount": row[10],
                "vat_rate": row[11],
            }
            for row in rows
        ]
    }


@app.get("/api/analytics")
def analytics() -> dict[str, Any]:
    try:
        return get_invoice_analytics()
    except DatabaseError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")

    @app.get("/")
    def frontend() -> FileResponse:
        return FileResponse(FRONTEND / "index.html")
