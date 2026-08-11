"""Second-pass verification of LLM-extracted invoice fields."""

from __future__ import annotations

import json

import litellm

from .models import InvoiceExtraction

VERIFICATION_THRESHOLD = 90

VERIFIER_PROMPT = """You are an independent invoice verification system. Inspect the invoice image and independently verify the first-pass extraction.
Verify date (issue/transaction date), supplier (issuing business), amount (final total), and currency.
For each field return confirmed, corrected, or uncertain. Only correct a value when clearly readable. Do not guess.
Return ONLY JSON with date_status/date/date_reason, supplier_status/supplier/supplier_reason, amount_status/amount/amount_reason, and currency_status/currency/currency_reason."""


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
    return result.needs_review or result.overall_confidence < VERIFICATION_THRESHOLD


def verify_extraction(image_path: str, result: InvoiceExtraction, api_key: str, model: str) -> InvoiceExtraction:
    if not _verification_should_run(result):
        return result

    from .llm_extractor import _load_and_encode_image

    try:
        image_data, media_type = _load_and_encode_image(image_path)
        first_pass = {"date": result.date.value, "supplier": result.supplier.value, "amount": result.amount.value, "currency": result.currency}
        response = litellm.completion(
            model=model, api_key=api_key, max_tokens=768,
            messages=[
                {"role": "system", "content": VERIFIER_PROMPT},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_data}"}},
                    {"type": "text", "text": "First-pass extraction:\n" + json.dumps(first_pass)},
                ]},
            ],
        )
        data = _parse_verification(response.choices[0].message.content or "")
    except Exception as exc:
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
            field.reasons.append(f"Second-pass verifier corrected the value: {reason or 'image evidence'}")
            corrections.append(f"{field_name}: {old_value!r} → {verified_value!r}")
        elif status == "confirmed":
            field.confidence = max(field.effective_confidence, VERIFICATION_THRESHOLD)
            field.reasons.append(f"Second-pass verifier confirmed the value: {reason or 'image evidence'}")
        elif status == "uncertain":
            field.confidence = min(field.effective_confidence, 69)
            field.validation_confidence = min(field.effective_confidence, 69)
            field.validation_issues.append("Second-pass verifier could not confirm this field.")

    if data.get("currency_status") == "corrected" and data.get("currency"):
        result.currency = str(data["currency"]).upper()
        corrections.append(f"currency corrected to {result.currency}")

    if corrections:
        result.warnings.append("Second-pass verification made corrections: " + "; ".join(corrections))
    elif any(data.get(f"{name}_status") == "uncertain" for name in ("date", "supplier", "amount", "currency")):
        result.warnings.append("Second-pass verification could not confirm every field.")
    return result
