"""Independent second-pass verification for invoice extraction."""
from __future__ import annotations
import json
import litellm
from .models import InvoiceExtraction
VERIFICATION_THRESHOLD = 90
VERIFIER_PROMPT = """You independently verify invoice extraction. Inspect the original image, do not trust the first pass, and verify date, supplier, amount (final total), and currency. For each field return confirmed, corrected, or uncertain. Correct only when clearly readable; never guess. Return ONLY JSON with *_status, value, and *_reason for date, supplier, amount, and currency."""
def _parse_verification(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    data = json.loads(cleaned.strip())
    if not isinstance(data, dict):
        raise RuntimeError("Verifier returned an unexpected response shape.")
    return data
def _verification_should_run(result: InvoiceExtraction) -> bool:
    return result.needs_review or result.overall_confidence < VERIFICATION_THRESHOLD
def verify_extraction(image_path: str, result: InvoiceExtraction, api_key: str, model: str) -> InvoiceExtraction:
    if not _verification_should_run(result): return result
    from .llm_extractor import _load_and_encode_image
    try:
        image_data, media_type = _load_and_encode_image(image_path)
        first_pass = {"date": result.date.value, "supplier": result.supplier.value, "amount": result.amount.value, "currency": result.currency}
        response = litellm.completion(model=model, api_key=api_key, max_tokens=768, messages=[{"role":"system","content":VERIFIER_PROMPT},{"role":"user","content":[{"type":"image_url","image_url":{"url":f"data:{media_type};base64,{image_data}"}},{"type":"text","text":"First-pass extraction:\n"+json.dumps(first_pass)}]}])
        data = _parse_verification(response.choices[0].message.content or "")
    except Exception as exc:
        result.warnings.append(f"Verification could not be completed: {exc}")
        return result
    corrections=[]
    for name in ("date","supplier","amount"):
        field=getattr(result,name); status=data.get(f"{name}_status"); value=data.get(name); reason=data.get(f"{name}_reason")
        if status=="corrected" and value not in (None,""):
            old=field.value; field.value=str(value); field.confidence=90; field.validation_confidence=None; field.validation_issues=[]; corrections.append(f"{name}: {old!r} → {value!r}")
        elif status=="confirmed": field.confidence=max(field.effective_confidence,VERIFICATION_THRESHOLD)
        elif status=="uncertain": field.confidence=min(field.effective_confidence,69); field.validation_confidence=min(field.effective_confidence,69); field.validation_issues.append("Second-pass verifier could not confirm this field.")
        if reason: field.reasons.append(f"Second-pass verifier: {reason}")
    if data.get("currency_status")=="corrected" and data.get("currency"):
        result.currency=str(data["currency"]).upper(); corrections.append(f"currency corrected to {result.currency}")
    if corrections: result.warnings.append("Second-pass verification made corrections: "+"; ".join(corrections))
    elif any(data.get(f"{name}_status")=="uncertain" for name in ("date","supplier","amount","currency")): result.warnings.append("Second-pass verification could not confirm every field.")
    return result
