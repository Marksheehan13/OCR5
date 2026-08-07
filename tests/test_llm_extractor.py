"""
tests/test_llm_extractor.py

Tests for llm_extractor.py's parsing/orchestration logic, using a
mocked Anthropic client so the test suite runs free and offline --
it never makes a real API call. This tests "does OCR5 correctly
handle what the API gives it", not "is Claude good at reading
invoices" (that's what tests/manual_accuracy_check.py is for, run
separately with a real key against real images).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm_extractor import (
    ExtractionError,
    _field_result,
    _parse_json_response,
    extract_invoice,
)

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "sample_data" / "invoices"


# --- JSON parsing -------------------------------------------------------------

def test_parse_json_response_plain():
    text = '{"date": "04/08/2026", "amount": "184.50"}'
    data = _parse_json_response(text)
    assert data["date"] == "04/08/2026"


def test_parse_json_response_strips_markdown_fences():
    text = '```json\n{"date": "04/08/2026"}\n```'
    data = _parse_json_response(text)
    assert data["date"] == "04/08/2026"


def test_parse_json_response_raises_on_garbage():
    with pytest.raises(ExtractionError):
        _parse_json_response("this is not json at all")


# --- Field result construction -------------------------------------------------

def test_field_result_normal_value():
    data = {"amount": "184.50", "amount_confidence": 95, "amount_reasoning": "clearly printed"}
    result = _field_result(data, "amount")
    assert result.value == "184.50"
    assert result.confidence == 95
    assert result.level == "high"


def test_field_result_null_value():
    data = {"supplier": None, "supplier_confidence": 0, "supplier_reasoning": "illegible"}
    result = _field_result(data, "supplier")
    assert result.value is None
    assert result.level == "review"


def test_field_result_string_null():
    """Models sometimes literally emit the string "null" instead of JSON null."""
    data = {"date": "null", "date_confidence": 0}
    result = _field_result(data, "date")
    assert result.value is None


# --- extract_invoice orchestration (mocked API) --------------------------------

def _mock_response(payload: dict):
    text_block = MagicMock()
    text_block.text = json.dumps(payload)
    response = MagicMock()
    response.content = [text_block]
    return response


@patch("src.llm_extractor.Anthropic")
def test_extract_invoice_happy_path(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_response(
        {
            "date": "04/08/2026",
            "date_confidence": 97,
            "date_reasoning": "clearly printed near top",
            "supplier": "Kerry Office Supplies Ltd",
            "supplier_confidence": 98,
            "supplier_reasoning": "header line, ALL CAPS trading name",
            "amount": "184.50",
            "amount_confidence": 96,
            "amount_reasoning": "labeled Total Due at bottom",
            "currency": "EUR",
            "warnings": [],
        }
    )
    mock_anthropic_cls.return_value = mock_client

    result = extract_invoice(str(SAMPLES_DIR / "sample_invoice_1.jpg"), api_key="fake-key-for-test")

    assert result.date.value == "04/08/2026"
    assert result.supplier.value == "Kerry Office Supplies Ltd"
    assert result.amount.value == "184.50"
    assert result.needs_review is False
    mock_client.messages.create.assert_called_once()


@patch("src.llm_extractor.Anthropic")
def test_extract_invoice_flags_low_confidence_for_review(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_response(
        {
            "date": "04/08/2026",
            "date_confidence": 40,
            "date_reasoning": "partially obscured",
            "supplier": None,
            "supplier_confidence": 0,
            "supplier_reasoning": "not visible in frame",
            "amount": "184.50",
            "amount_confidence": 85,
            "amount_reasoning": "clear",
            "currency": "EUR",
            "warnings": ["Image is cropped, top of receipt not visible"],
        }
    )
    mock_anthropic_cls.return_value = mock_client

    result = extract_invoice(str(SAMPLES_DIR / "sample_invoice_1.jpg"), api_key="fake-key-for-test")

    assert result.needs_review is True
    assert result.supplier.value is None
    assert len(result.warnings) == 1


def test_extract_invoice_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ExtractionError, match="No Anthropic API key"):
        extract_invoice(str(SAMPLES_DIR / "sample_invoice_1.jpg"), api_key=None)


def test_extract_invoice_raises_on_missing_file():
    with pytest.raises(ExtractionError):
        extract_invoice("/tmp/this_file_does_not_exist_12345.jpg", api_key="fake-key")


@patch("src.llm_extractor.Anthropic")
def test_extract_invoice_raises_extraction_error_on_bad_json(mock_anthropic_cls):
    mock_client = MagicMock()
    text_block = MagicMock()
    text_block.text = "Sorry, I can't read this image clearly."
    response = MagicMock()
    response.content = [text_block]
    mock_client.messages.create.return_value = response
    mock_anthropic_cls.return_value = mock_client

    with pytest.raises(ExtractionError):
        extract_invoice(str(SAMPLES_DIR / "sample_invoice_1.jpg"), api_key="fake-key-for-test")
