"""Second-pass verification of LLM-extracted invoice fields."""

from __future__ import annotations

import json

import litellm

from .models import InvoiceExtraction

VERIFICATION_THRESHOLD = 90

VERIFIER_PROMPT = """You are an independent invoice verification system.

You will receive an invoice/receipt image and the first-pass extraction below.
Do NOT assume the first-pass values are correct. Inspect the original image and
independently verify each field.

Fields to verify:
- date: invoice/transaction issue date, not due date or expiry date
- supplier: business that issued the invoice/receipt
- amount: final total paid or owed, not subtotal, VAT, discount, or line item
- currency: three-letter currency code

For every field, return one of:
- confirmed: the first-pass value is clearly supported by the image
- corrected: the image clearly shows a different value
- uncertain: the image is too unclear to decide

Only provide a corrected value when it is clearly readable in the image.
Do not guess.

Return ONLY this JSON shape:
{
  "date_status": "confirmed|corrected|uncertain",
  "date": "DD/MM/YYYY or null",
  "date_reason": "short explanation",
  "supplier_status": "confirmed|corrected|uncertain",
  "supplier": "supplier name or null",
  "supplier_reason": "short explanation",
  "amount_status": "confirmed|corrected|uncertain",
  "amount": "numeric string with 2 decimals or null",
  "amount_reason": "short explanation",
  "currency_status": "confirmed|corrected|uncertain",
  "currency": "3-letter code or null",
  "currency_reason": "short explanation"
}
"""


def _parse_verification(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned.strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Verifier response wasn't valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Verifier returned an unexpected response shape.")
    return data


def _verification_should_run(result: InvoiceExtraction) -> bool:
    """Only spend a second model call when the first pass warrants scrutiny."""
    return result.needs_review or result.overall_confidence < VERIFICATION_THRESHOLD


def verify_extraction(
    image_path: str,
    result: InvoiceExtraction,
    api_key: str,
    model: str,
) -> InvoiceExtraction:
    """Verify and, when clearly supported, correct a first-pass extraction."""
    if not _verification_should_run(result):
        return result

    # Local import avoids a module-level cycle: llm_extractor imports this verifier.
    from .llm_extractor import _load_and_encode_image

    try:
        image_data, media_type = _load_and_encode_image(image_path)
    except Exception as exc:
        result.warnings.append(f"Verification could not read the invoice image: {exc}")
        return result

    first_pass = {
        "date": result.date.value,
        "supplier": result.supplier.value,
        "amount": result.amount.value,
        "currency": result.currency,
    }

    try:
        response = litellm.completion(
            model=model,
            api_key=api_key,
            max_tokens=768,
            messages=[
                {"role": "system", "content": VERIFIER_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{image_data}"},
                        },
                        {
                            "type": "text",
                            "text": "First-pass extraction:\n" + json.dumps(first_pass),
                        },
                    ],
                },
            ],
        )
        data = _parse_verification(response.choices[0].message.content or "")
    except Exception as exc:  # noqa: BLE001 - verifier failure must not destroy extraction
        result.warnings.append(f"Verification could not be completed: {exc}")
        return result

    corrections = []
    for field_name in ("date", "supplier", "amount"):
        status = data.get(f"{field_name}_status")
        verified_value = data.get(field_name)
        reason = data.get(f"{field_name}_reason")
        field = getattr(result, field_name)

        if status == "corrected" and verified_value not in (None, ""):
            old_value = field.value
            field.value = str(verified_value)
            field.confidence = 90
            field.validation_confidence = None
            field.validation_issues = []
            field.reasons.append(
                f"Second-pass verifier corrected the value: {reason or 'image evidence'}"
            )
            corrections.append(f"{field_name}: {old_value!r} → {verified_value!r}")
        elif status == "confirmed":
            field.confidence = max(field.effective_confidence, VERIFICATION_THRESHOLD)
            field.reasons.append(
                f"Second-pass verifier confirmed the value: {reason or 'image evidence'}"
            )
        elif status == "uncertain":
            field.confidence = min(field.effective_confidence, 69)
            field.validation_confidence = min(field.effective_confidence, 69)
            field.validation_issues.append("Second-pass verifier could not confirm this field.")

    verified_currency = data.get("currency")
    if data.get("currency_status") == "corrected" and verified_currency:
        result.currency = str(verified_currency).upper()
        corrections.append(f"currency corrected to {result.currency}")

    if corrections:
        result.warnings.append("Second-pass verification made corrections: " + "; ".join(corrections))
    elif any(
        data.get(f"{name}_status") == "uncertain"
        for name in ("date", "supplier", "amount", "currency")
    ):
        result.warnings.append("Second-pass verification could not confirm every field.")

    return result
