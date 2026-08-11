"""Vision-based invoice extraction with validation and verification."""

from __future__ import annotations

import base64
import json
from io import BytesIO

import litellm
from PIL import Image

from .models import FieldResult, InvoiceExtraction, LineItem
from .validator import validate_extraction

MAX_LONG_EDGE = 1568
PROVIDERS = {
    "Google Gemini (free tier)": {"model": "gemini/gemini-3.5-flash", "env_var": "GEMINI_API_KEY"},
    "Anthropic": {"model": "claude-sonnet-5", "env_var": "ANTHROPIC_API_KEY"},
    "OpenAI": {"model": "gpt-5-mini", "env_var": "OPENAI_API_KEY"},
    "Groq": {"model": "groq/meta-llama/llama-4-scout-17b-16e-instruct", "env_var": "GROQ_API_KEY"},
    "OpenRouter": {"model": "openrouter/openai/gpt-5-mini", "env_var": "OPENROUTER_API_KEY"},
}
DEFAULT_PROVIDER = "Google Gemini (free tier)"

SYSTEM_PROMPT = """You are an invoice/receipt data extraction system. Extract these fields from the image:
- invoice/transaction date (not due date)
- supplier/vendor/store name
- final total amount due/paid
- currency (3-letter code)
- invoice number/reference number if present
- subtotal if explicitly shown
- VAT/tax amount if explicitly shown
- VAT/tax rate if explicitly shown
- every visible invoice line item, excluding subtotal, VAT, discounts, shipping and final totals

For each line item extract description, quantity, unit price, VAT rate and line total when explicitly shown. Preserve the order in which items appear. Do not invent missing values.

Do not guess. If a field is absent or unreadable, return null with confidence 0. If there are no identifiable line items, return an empty array.
Respond with ONLY this JSON object:
{
  "date": "DD/MM/YYYY or null", "date_confidence": 0-100, "date_reasoning": "short reason",
  "supplier": "name or null", "supplier_confidence": 0-100, "supplier_reasoning": "short reason",
  "amount": "numeric string with 2 decimals or null", "amount_confidence": 0-100, "amount_reasoning": "short reason",
  "currency": "3-letter code",
  "invoice_number": "invoice/reference number or null", "invoice_number_confidence": 0-100, "invoice_number_reasoning": "short reason",
  "subtotal": "numeric string with 2 decimals or null", "subtotal_confidence": 0-100, "subtotal_reasoning": "short reason",
  "vat_amount": "numeric string with 2 decimals or null", "vat_amount_confidence": 0-100, "vat_amount_reasoning": "short reason",
  "vat_rate": "numeric percentage without % or null", "vat_rate_confidence": 0-100, "vat_rate_reasoning": "short reason",
  "line_items": [
    {"description": "string", "quantity": "numeric string or null", "unit_price": "numeric string or null", "vat_rate": "numeric percentage or null", "line_total": "numeric string or null", "confidence": 0-100, "warnings": []}
  ],
  "warnings": []
}"""

class ExtractionError(Exception):
    pass


def _load_and_encode_image(path: str) -> tuple[str, str]:
    try:
        img = Image.open(path).convert("RGB")
    except Exception as exc:
        raise ExtractionError(f"Could not open '{path}' as an image ({exc.__class__.__name__}).") from exc
    long_edge = max(img.size)
    if long_edge > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / long_edge
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    return base64.b64encode(buffer.getvalue()).decode("utf-8"), "image/jpeg"


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Model response wasn't valid JSON: {exc}. Raw response: {text[:500]}") from exc


def _field_result(data: dict, field_name: str) -> FieldResult:
    value = data.get(field_name)
    confidence = max(0, min(100, int(data.get(f"{field_name}_confidence", 0) or 0)))
    reasoning = data.get(f"{field_name}_reasoning", "")
    if value in (None, "null", ""):
        return FieldResult(None, 0, [reasoning] if reasoning else ["Not found in image"])
    return FieldResult(str(value), confidence, [reasoning] if reasoning else [])


def _line_items(data: dict) -> list[LineItem]:
    items = data.get("line_items") or []
    if not isinstance(items, list):
        return []
    parsed = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        description = str(raw.get("description") or "").strip()
        confidence = max(0, min(100, int(raw.get("confidence", 0) or 0)))
        warnings = [str(w) for w in (raw.get("warnings") or [])]
        if not description:
            warnings.append("Description was not readable")
        parsed.append(LineItem(
            description=description,
            quantity=None if raw.get("quantity") in (None, "", "null") else str(raw.get("quantity")),
            unit_price=None if raw.get("unit_price") in (None, "", "null") else str(raw.get("unit_price")),
            vat_rate=None if raw.get("vat_rate") in (None, "", "null") else str(raw.get("vat_rate")),
            line_total=None if raw.get("line_total") in (None, "", "null") else str(raw.get("line_total")),
            confidence=confidence,
            warnings=warnings,
        ))
    return parsed


def extract_invoice(image_path: str, api_key: str | None = None, provider: str = DEFAULT_PROVIDER, model: str | None = None) -> InvoiceExtraction:
    if provider not in PROVIDERS:
        raise ExtractionError(f"Unknown provider '{provider}'.")
    if not api_key:
        raise ExtractionError(f"No API key provided for {provider}.")
    resolved_model = model or PROVIDERS[provider]["model"]
    image_data, media_type = _load_and_encode_image(image_path)
    try:
        response = litellm.completion(
            model=resolved_model, api_key=api_key, max_tokens=1800,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_data}"}},
                    {"type": "text", "text": "Extract all requested invoice fields and every visible line item from this document."},
                ]},
            ],
        )
    except litellm.exceptions.AuthenticationError as exc:
        raise ExtractionError(f"{provider} authentication failed -- check your API key.") from exc
    except litellm.exceptions.RateLimitError as exc:
        raise ExtractionError(f"{provider} rate limit hit -- wait a moment and try again.") from exc
    except litellm.exceptions.APIConnectionError as exc:
        raise ExtractionError(f"Could not reach {provider}: {exc}") from exc
    except Exception as exc:
        raise ExtractionError(f"{provider} request failed: {exc}") from exc

    raw_text = response.choices[0].message.content or ""
    data = _parse_json_response(raw_text)
    result = InvoiceExtraction(
        source_file=image_path,
        date=_field_result(data, "date"), supplier=_field_result(data, "supplier"), amount=_field_result(data, "amount"),
        currency=data.get("currency") or "EUR",
        invoice_number=_field_result(data, "invoice_number"), subtotal=_field_result(data, "subtotal"),
        vat_amount=_field_result(data, "vat_amount"), vat_rate=_field_result(data, "vat_rate"),
        line_items=_line_items(data), warnings=list(data.get("warnings") or []), raw_text=raw_text,
    )
    result = validate_extraction(result)
    from .verifier import verify_extraction
    result = verify_extraction(image_path, result, api_key, resolved_model)
    return validate_extraction(result)
