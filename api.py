"""OCR5 standalone web API with client-aware bookkeeping workflows."""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.client_database import archive_client, create_client, get_client, get_client_analytics, list_clients, restore_client, update_client
from src.database import DatabaseError, get_all_invoices, get_invoice_analytics
from src.database_integration import store_invoice_result
from src.duplicate_detector import find_duplicate_matches
from src.llm_extractor import DEFAULT_PROVIDER, PROVIDERS, ExtractionError, extract_invoice
from src.models import FieldResult, InvoiceExtraction, LineItem

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
app = FastAPI(title="OCR5 API", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
_pending_sources: dict[str, tuple[Path, str, int]] = {}


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
    source_token: str | None = None
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


class ClientPayload(BaseModel):
    name: str
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None


class ClientUpdatePayload(ClientPayload):
    active: bool | None = None


def _client_id(value: str | None) -> int:
    if not value:
        raise HTTPException(400, "Select a client before using this bookkeeping workflow.")
    try:
        client_id = int(value)
    except ValueError as exc:
        raise HTTPException(400, "Invalid client id.") from exc
    client = get_client(client_id)
    if not client:
        raise HTTPException(404, "Client not found.")
    if not client.get("active", False):
        raise HTTPException(409, "That client is archived.")
    return client_id


def _read_client_id(value: str | None) -> int:
    """Resolve a read-only client context; fall back to the legacy client while the UI bootstraps."""
    if value:
        return _client_id(value)
    active = list_clients()
    if not active:
        raise HTTPException(503, "No active client exists.")
    return int(active[0]["id"])


def _field(payload: FieldPayload) -> FieldResult:
    return FieldResult(value=payload.value, confidence=max(0, min(100, payload.confidence)), reasons=payload.reasons, validation_confidence=payload.validation_confidence, validation_issues=payload.validation_issues)


def _invoice(payload: InvoicePayload) -> InvoiceExtraction:
    return InvoiceExtraction(
        source_file=payload.source_file,
        date=_field(payload.date), supplier=_field(payload.supplier), amount=_field(payload.amount), currency=payload.currency or "EUR",
        invoice_number=_field(payload.invoice_number), subtotal=_field(payload.subtotal), vat_amount=_field(payload.vat_amount), vat_rate=_field(payload.vat_rate),
        line_items=[LineItem(**item.model_dump()) for item in payload.line_items], warnings=payload.warnings, raw_text=payload.raw_text, validation_warnings=payload.validation_warnings,
    )


def _field_json(field: FieldResult) -> dict[str, Any]:
    return {"value": field.value, "confidence": field.effective_confidence, "level": field.level, "reasons": field.reasons, "validation_issues": field.validation_issues}


def _invoice_json(invoice: InvoiceExtraction, source_token: str | None = None) -> dict[str, Any]:
    return {"source_file": invoice.source_file, "source_token": source_token, "date": _field_json(invoice.date), "supplier": _field_json(invoice.supplier), "amount": _field_json(invoice.amount), "currency": invoice.currency, "invoice_number": _field_json(invoice.invoice_number), "subtotal": _field_json(invoice.subtotal), "vat_amount": _field_json(invoice.vat_amount), "vat_rate": _field_json(invoice.vat_rate), "line_items": [{"description": x.description, "quantity": x.quantity, "unit_price": x.unit_price, "vat_rate": x.vat_rate, "line_total": x.line_total, "confidence": x.confidence, "warnings": x.warnings} for x in invoice.line_items], "warnings": invoice.warnings, "validation_warnings": invoice.validation_warnings, "needs_review": invoice.needs_review, "overall_confidence": invoice.overall_confidence}


@app.get("/api/health")
def health() -> dict[str, str]: return {"status": "ok", "service": "ocr5", "client_scoping": "enabled"}

@app.get("/api/providers")
def providers() -> dict[str, Any]: return {"default": DEFAULT_PROVIDER, "providers": [{"name": name, "model": config["model"]} for name, config in PROVIDERS.items()]}

@app.get("/api/clients")
def clients(include_inactive: bool = False) -> dict[str, Any]:
    try: return {"clients": list_clients(include_inactive=include_inactive)}
    except DatabaseError as exc: raise HTTPException(503, str(exc)) from exc

@app.post("/api/clients")
def add_client(payload: ClientPayload) -> dict[str, Any]:
    try: return {"client": create_client(payload.name, payload.company_name, payload.email, payload.phone, payload.address)}
    except DatabaseError as exc: raise HTTPException(400, str(exc)) from exc

@app.get("/api/clients/{client_id}")
def client_detail(client_id: int) -> dict[str, Any]:
    try:
        client = get_client(client_id)
        if not client: raise HTTPException(404, "Client not found.")
        return {"client": client, "analytics": get_client_analytics(client_id)}
    except DatabaseError as exc: raise HTTPException(503, str(exc)) from exc

@app.patch("/api/clients/{client_id}")
def edit_client(client_id: int, payload: ClientUpdatePayload) -> dict[str, Any]:
    try: return {"client": update_client(client_id, **payload.model_dump(exclude_none=True))}
    except DatabaseError as exc: raise HTTPException(400, str(exc)) from exc

@app.delete("/api/clients/{client_id}")
def delete_client(client_id: int) -> dict[str, Any]:
    try: return {"client": archive_client(client_id), "status": "archived"}
    except DatabaseError as exc: raise HTTPException(400, str(exc)) from exc

@app.post("/api/clients/{client_id}/restore")
def unarchive_client(client_id: int) -> dict[str, Any]:
    try: return {"client": restore_client(client_id), "status": "active"}
    except DatabaseError as exc: raise HTTPException(400, str(exc)) from exc

@app.post("/api/extract")
async def extract(file: UploadFile = File(...), x_ocr5_api_key: str | None = Header(default=None), x_ocr5_provider: str = Header(default=DEFAULT_PROVIDER), x_ocr5_client_id: str | None = Header(default=None)) -> dict[str, Any]:
    client_id = _client_id(x_ocr5_client_id)
    if x_ocr5_provider not in PROVIDERS: raise HTTPException(400, f"Unknown provider '{x_ocr5_provider}'.")
    api_key = x_ocr5_api_key or os.environ.get(PROVIDERS[x_ocr5_provider]["env_var"])
    if not api_key: raise HTTPException(400, "No AI API key supplied.")
    content = await file.read()
    if not content: raise HTTPException(400, "The uploaded file is empty.")
    suffix = Path(file.filename or "invoice.jpg").suffix or ".jpg"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp: tmp.write(content); tmp_path = Path(tmp.name)
        result = extract_invoice(str(tmp_path), api_key=api_key, provider=x_ocr5_provider); result.source_file = file.filename or "invoice"
        token = uuid.uuid4().hex; _pending_sources[token] = (tmp_path, file.content_type or "application/octet-stream", client_id); tmp_path = None
        payload = _invoice_json(result, token); payload["client_id"] = client_id; return {"invoice": payload}
    except ExtractionError as exc: raise HTTPException(422, str(exc)) from exc
    except Exception as exc: raise HTTPException(500, f"OCR5 extraction failed: {exc}") from exc
    finally:
        if tmp_path: tmp_path.unlink(missing_ok=True)

@app.get("/api/source/{token}")
def source_preview(token: str) -> Response:
    item = _pending_sources.get(token)
    if not item: raise HTTPException(404, "Source document is no longer available.")
    path, mime, _ = item
    if not path.exists(): _pending_sources.pop(token, None); raise HTTPException(404, "Source document is no longer available.")
    return Response(path.read_bytes(), media_type=mime)

@app.post("/api/invoices/check-duplicates")
def check_duplicates(payload: InvoicePayload, x_ocr5_client_id: str | None = Header(default=None)) -> dict[str, Any]:
    client_id = _client_id(x_ocr5_client_id)
    try: history = get_all_invoices(client_id)
    except DatabaseError as exc: raise HTTPException(503, str(exc)) from exc
    invoice = _invoice(payload); matches = find_duplicate_matches(invoice.supplier.value, invoice.date.value, invoice.amount.value, invoice.currency, history)
    return {"client_id": client_id, "matches": [{"invoice_id": m.invoice_id, "supplier": m.supplier, "invoice_date": m.invoice_date, "amount": m.amount, "currency": m.currency, "score": getattr(m, "score", None)} for m in matches]}

@app.post("/api/invoices/save")
def save_invoice(payload: InvoicePayload, x_ocr5_client_id: str | None = Header(default=None)) -> dict[str, Any]:
    client_id = _client_id(x_ocr5_client_id)
    try:
        invoice = _invoice(payload); source = _pending_sources.get(payload.source_token or "")
        if source and source[2] != client_id: raise HTTPException(409, "The selected client changed while this invoice was being reviewed. Please re-upload it under the correct client.")
        image_bytes = source[0].read_bytes() if source and source[0].exists() else None; mime_type = source[1] if source else "application/octet-stream"
        result = store_invoice_result(invoice, image_bytes=image_bytes, mime_type=mime_type, client_id=client_id)
        if payload.source_token:
            pending = _pending_sources.pop(payload.source_token, None)
            if pending: pending[0].unlink(missing_ok=True)
        return result
    except HTTPException: raise
    except DatabaseError as exc: raise HTTPException(503, str(exc)) from exc

@app.get("/api/invoices")
def invoices(x_ocr5_client_id: str | None = Header(default=None)) -> dict[str, Any]:
    client_id = _read_client_id(x_ocr5_client_id)
    try: rows = get_all_invoices(client_id)
    except DatabaseError as exc: raise HTTPException(503, str(exc)) from exc
    return {"client_id": client_id, "invoices": [{"id": r[0], "supplier": r[1], "date": r[2], "amount": r[3], "currency": r[4], "confidence": r[5], "image_path": r[6], "created_at": r[7], "invoice_number": r[8], "subtotal": r[9], "vat_amount": r[10], "vat_rate": r[11], "client_id": r[12]} for r in rows]}

@app.get("/api/analytics")
def analytics(x_ocr5_client_id: str | None = Header(default=None)) -> dict[str, Any]:
    client_id = _read_client_id(x_ocr5_client_id)
    try: return get_invoice_analytics(client_id)
    except DatabaseError as exc: raise HTTPException(503, str(exc)) from exc

if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")
    @app.get("/", response_class=HTMLResponse)
    def frontend() -> HTMLResponse:
        html = (FRONTEND / "index.html").read_text(encoding="utf-8")
        injection = '<script src="/assets/clients.js"></script><script src="/assets/client-actions.js"></script>'
        if injection not in html: html = html.replace("</body>", injection + "</body>")
        return HTMLResponse(content=html)
