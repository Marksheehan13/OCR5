from src.models import FieldResult, InvoiceExtraction
from src.verifier import _parse_verification, _verification_should_run


def make_extraction(confidence=95):
    return InvoiceExtraction(
        source_file="invoice.jpg",
        date=FieldResult("11/08/2026", confidence),
        supplier=FieldResult("Tesco", confidence),
        amount=FieldResult("184.50", confidence),
    )


def test_high_confidence_clean_extraction_skips_verification():
    extraction = make_extraction(95)
    assert not extraction.needs_review
    assert not _verification_should_run(extraction)


def test_low_confidence_extraction_triggers_verification():
    extraction = make_extraction(80)
    assert _verification_should_run(extraction)


def test_review_flag_triggers_verification_even_at_high_confidence():
    extraction = make_extraction(95)
    extraction.amount.validation_issues.append("Amount needs review")
    assert extraction.needs_review
    assert _verification_should_run(extraction)


def test_verifier_json_is_parsed():
    data = _parse_verification('{"date_status":"confirmed","date":"11/08/2026"}')
    assert data["date_status"] == "confirmed"
    assert data["date"] == "11/08/2026"
