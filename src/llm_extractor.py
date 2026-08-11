"""Vision-based invoice extraction with independent validation and verification."""

from __future__ import annotations

import base64
import json
from io import BytesIO

import litellm
from PIL import Image

from .models import FieldResult, InvoiceExtraction
from .validator import validate_extraction

MAX_LONG_EDGE = 1568

PROVIDERS: dict[str, dict[str, str]] = {
    "Google Gemini (free tier)": {"model": "gemini/gemini-3.5-flash", "env_var": "GEMINI_API_KEY"},
    "Anthropic": {"model": "claude-sonnet-5", "env_var": "ANTHROPIC_API_KEY"},
    "OpenAI": {"model": "gpt-5-mini", "env_var": "OPENAI_API_KEY"},
    "Groq": {"model": "groq/meta-llama/llama-4-scout-17b-16e-instruct", "env_var": "GROQ_API_KEY"},
    "OpenRouter": {"model": "openrouter/openai/gpt-5-mini", "env_var": "OPENROUTER_API_KEY"},
}
DEFAULT_PROVIDER = "Google Gemini (free tier)"

SYSTEM_PROMPT = """You are an invoice/receipt data extraction system. You will be shown a photo of an invoice or receipt. Extract exactly three fields: the invoice/transaction date, the supplier/vendor/store name, and the total amount due.

Important distinctions:
- Supplier is the BUSINESS that issued the document, preferably the trading name printed at the top.
- Amount is the FINAL total paid or owed, not subtotal, VAT, discount, or line-item price.
- Date is the invoice/transaction date, not a due date or expiry date unless no issue date exists.

Respond with ONLY this JSON object:
{
  "date": "DD/MM/YYYY or null",
  "date_confidence": 0-100,
  "date_reasoning": "one short sentence",
  "supplier": "supplier name or null",
  "supplier_confidence": 0-100,
  "supplier_reasoning": "one short sentence",
  "amount": "numeric string with 2 decimals or null",
  "amount_confidence": 0-100,
  "amount_reasoning": "one short sentence",
  "currency": "3-letter code",
  "warnings": ["short warnings, empty if none"]
}

Use 90-100 only when clearly legible and unambiguous. Use lower confidence when there is ambiguity. If a field cannot be determined, use null and confidence 0 rather than guessing."""


class ExtractionError(Exception):
    """Raised for fatal, unrecoverable extraction problems."""


def _load_and_encode_image(path: str) -> tuple[str, str]:
    """Load an image, resize to a sensible max resolution, return base64 and media type."""
    try:
        img = Image.open(path).convert("RGB")
    except Exception as exc:
        raise ExtractionError(
            f"Could not open '{path}' as an image ({exc.__class__.__name__}). Check the file."
        ) from exc

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
    reasons = [reasoning] if reasoning else []
    if value in (None, "null", ""):
        return FieldResult(value=None, confidence=0, reasons=reasons or ["Not found in image"])
    return FieldResult(value=str(value), confidence=confidence, reasons=reasons)


def extract_invoice(
    image_path: str,
    api_key: str | None = None,
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
) -> InvoiceExtraction:
    """Extract an invoice, validate it, then verify uncertain results with a second pass."""
    if provider not in PROVIDERS:
        raise ExtractionError(f"Unknown provider '{provider}'. Choose one of: {', '.join(PROVIDERS)}")
    if not api_key:
        env_var = PROVIDERS[provider]["env_var"]
        raise ExtractionError(
            f"No API key provided for {provider}. Set {env_var} or enter one in the app."
        )

    resolved_model = model or PROVIDERS[provider]["model"]
    image_data, media_type = _load_and_encode_image(image_path)

    try:
        response = litellm.completion(
            model=resolved_model,
            api_key=api_key,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_data}"}},
                        {"type": "text", "text": "Extract the date, supplier, and total amount from this invoice/receipt."},
                    ],
                },
            ],
        )
    except litellm.exceptions.AuthenticationError as exc:
        raise ExtractionError(f"{provider} authentication failed -- check your API key.") from exc
    except litellm.exceptions.RateLimitError as exc:
        raise ExtractionError(f"{provider} rate limit hit -- wait a moment and try again.") from exc
    except litellm.exceptions.APIConnectionError as exc:
        raise ExtractionError(f"Could not reach {provider}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"{provider} request failed: {exc}") from exc

    raw_text = response.choices[0].message.content or ""
    data = _parse_json_response(raw_text)

    result = InvoiceExtraction(
        source_file=image_path,
        date=_field_result(data, "date"),
        supplier=_field_result(data, "supplier"),
        amount=_field_result(data, "amount"),
        currency=data.get("currency") or "EUR",
        warnings=list(data.get("warnings") or []),
        raw_text=raw_text,
    )
    result = validate_extraction(result)

    # Import locally to avoid a circular import: verifier reuses this module's image helper.
    from .verifier import verify_extraction

    result = verify_extraction(image_path, result, api_key, resolved_model)
    # Re-run deterministic validation after any verifier corrections.
    return validate_extraction(result)
