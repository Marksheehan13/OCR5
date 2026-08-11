"""
llm_extractor.py

The core of OCR5: instead of OCR + heuristic scoring (OCR4's approach),
this sends the invoice image directly to a vision-capable LLM and asks
it to read and extract the fields, with its own confidence and
reasoning per field. This trades "fully offline, free" for "actually
understands what it's looking at" -- see docs/comparison.md for the
full before/after rationale versus OCR4.

Multi-provider support (via litellm): you're not locked into a paid
Anthropic key. Google Gemini's Flash models have a genuinely free API
tier with native image/vision support, so that's the default here --
see PROVIDERS below for the full list and how to switch.

Design notes:
  - Images are resized so their longest edge is ~1568px before
    sending -- a good balance across providers; larger images cost
    more tokens/latency without reliably improving accuracy.
  - The prompt asks for strict JSON only (no markdown fences, no
    preamble) so the response can be parsed directly and reliably.
  - The model is asked for a confidence + short reasoning per field,
    same idea as OCR4's confidence layer, but now it's the model's own
    self-assessment of how legible/certain each field was, rather than
    a rule-based score.
"""

from __future__ import annotations

import base64
import json
from io import BytesIO

import litellm
from PIL import Image

from .models import FieldResult, InvoiceExtraction

MAX_LONG_EDGE = 1568

# Provider display name -> (litellm model string, env var litellm expects the key under).
# Gemini is the default because its Flash models have a genuinely free API
# tier (no credit card required) with native vision support -- see
# docs/comparison.md and README.md for the cost tradeoffs of each option.
#
# Both Google and Groq deprecate/rename specific model versions frequently
# (this file has already been updated once after gemini-2.5-flash and then
# gemini-3-flash-preview were both retired within the same year). If either
# option stops working with a "model not found" / 404-style error, check
# the provider's current model list and update PROVIDERS below:
#   Gemini: ai.google.dev/gemini-api/docs/models
#   Groq:   console.groq.com/docs/vision
PROVIDERS: dict[str, dict[str, str]] = {
    "Google Gemini (free tier)": {"model": "gemini/gemini-3.5-flash", "env_var": "GEMINI_API_KEY"},
    "Anthropic": {"model": "claude-sonnet-5", "env_var": "ANTHROPIC_API_KEY"},
    "OpenAI": {"model": "gpt-5-mini", "env_var": "OPENAI_API_KEY"},
    "Groq": {"model": "groq/meta-llama/llama-4-scout-17b-16e-instruct", "env_var": "GROQ_API_KEY"},
    "OpenRouter": {"model": "openrouter/openai/gpt-5-mini", "env_var": "OPENROUTER_API_KEY"},
}
DEFAULT_PROVIDER = "Google Gemini (free tier)"

SYSTEM_PROMPT = """You are an invoice/receipt data extraction system. You will be shown a photo \
of an invoice or receipt. Extract exactly three fields: the invoice/transaction date, the \
supplier/vendor/store name, and the total amount due.

Important distinctions to get right:
- The supplier is the BUSINESS that issued the invoice/receipt (the seller), not a customer \
name, not a cashier/staff name, not a "bill to" name, and not a registered proprietor's \
personal name if a separate trading name is shown. Prefer the trading name printed at the \
top of the document.
- The amount is the FINAL total the customer paid or owes -- not a subtotal, not a tax/VAT/GST \
line by itself, not a discount, not a line-item price. If multiple "total" labels appear \
(e.g. a pre-rounding subtotal vs a final rounded total), prefer the final one actually charged.
- The date is the invoice/transaction date, not a due date, not an expiry date, unless no \
issue date is present.

Respond with ONLY a single JSON object, no markdown code fences, no preamble, no explanation \
outside the JSON. Use exactly this shape:

{
  "date": "DD/MM/YYYY or null if not confidently legible",
  "date_confidence": 0-100,
  "date_reasoning": "one short sentence",
  "supplier": "supplier name or null if not confidently legible",
  "supplier_confidence": 0-100,
  "supplier_reasoning": "one short sentence",
  "amount": "numeric string with 2 decimals, e.g. 184.50, or null if not confidently legible",
  "amount_confidence": 0-100,
  "amount_reasoning": "one short sentence",
  "currency": "3-letter code, e.g. EUR, USD, GBP -- best guess from symbols/context",
  "warnings": ["list of strings -- e.g. note if the image is blurry, rotated, cropped, \
not actually an invoice/receipt, or any field could not be found at all. Empty list if none."]
}

Confidence should reflect your actual certainty: use 90-100 only when the text is clearly \
legible and unambiguous, 70-89 when reasonably confident but there's some ambiguity or \
partial illegibility, and below 70 when you're guessing or the text is unclear. If a field \
truly cannot be determined, set it to null and confidence to 0 rather than guessing."""


class ExtractionError(Exception):
    """Raised for fatal, unrecoverable problems (bad file, auth failure, etc)."""


def _load_and_encode_image(path: str) -> tuple[str, str]:
    """Load an image, resize to a sensible max resolution, return (base64_data, media_type)."""
    try:
        img = Image.open(path)
        img = img.convert("RGB")
    except Exception as exc:
        raise ExtractionError(
            f"Could not open '{path}' as an image ({exc.__class__.__name__}). "
            "Check the file isn't corrupted and is a supported format."
        ) from exc

    long_edge = max(img.size)
    if long_edge > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / long_edge
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return encoded, "image/jpeg"


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    # Defensive: strip markdown fences if the model adds them despite instructions.
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError as exc:
        raise ExtractionError(
            f"Model response wasn't valid JSON: {exc}. Raw response: {text[:500]}"
        ) from exc


def _field_result(data: dict, field_name: str) -> FieldResult:
    value = data.get(field_name)
    confidence = int(data.get(f"{field_name}_confidence", 0) or 0)
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
    """
    Send one invoice image to a vision-capable LLM and return the
    extracted fields.

    provider: one of the keys in PROVIDERS (defaults to Gemini's free tier).
    model: overrides the default model string for the chosen provider,
    if you want to point at a specific/newer model.
    api_key: required -- the key for whichever provider you selected.
    Callers (app.py, main.py) are responsible for sourcing this from
    an env var or Streamlit secrets matching PROVIDERS[provider]['env_var'].
    """
    if provider not in PROVIDERS:
        raise ExtractionError(
            f"Unknown provider '{provider}'. Choose one of: {', '.join(PROVIDERS)}"
        )
    if not api_key:
        env_var = PROVIDERS[provider]["env_var"]
        raise ExtractionError(
            f"No API key provided for {provider}. Set the {env_var} environment variable "
            f"(CLI) or enter one in the app sidebar / Streamlit secrets (web UI)."
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
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{image_data}"},
                        },
                        {
                            "type": "text",
                            "text": "Extract the date, supplier, and total amount from this invoice/receipt.",
                        },
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
    except Exception as exc:  # noqa: BLE001 - surface any other provider-side failure clearly
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
    return result
