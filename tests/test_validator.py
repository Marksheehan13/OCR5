from src.models import FieldResult, InvoiceExtraction
from src.validator import validate_amount, validate_date, validate_extraction


def test_valid_date_passes():
    result = validate_date(FieldResult("11/08/2026", 95))
    assert result.passed
    assert result.confidence_cap == 100


def test_invalid_date_is_capped():
    result = validate_date(FieldResult("2026-08-11", 99))
    assert not result.passed
    assert result.confidence_cap == 40


def test_valid_amount_passes():
    result = validate_amount(FieldResult("184.50", 96))
    assert result.passed


def test_invalid_amount_is_capped():
    result = validate_amount(FieldResult("not-a-number", 99))
    assert not result.passed
    assert result.confidence_cap == 40


def test_extraction_uses_validation_for_confidence_and_review():
    extraction = InvoiceExtraction(
        source_file="invoice.jpg",
        date=FieldResult("2026-08-11", 99),
        supplier=FieldResult("Tesco", 95),
        amount=FieldResult("184.50", 98),
    )

    validate_extraction(extraction)

    assert extraction.date.confidence == 40
    assert extraction.date.validation_issues
    assert extraction.needs_review
    assert extraction.overall_confidence < 90
