"""
tests/test_llm_extractor.py

Tests for llm_extractor.py's parsing/orchestration logic, using a
mocked litellm.completion() call so the test suite runs free and
offline -- it never makes a real API call to any provider. This tests
"does OCR5 correctly handle what the API gives it", not "is this
model good at reading invoices" (for that, run it against real images
with a real key and check results by eye, or benchmark against a
labeled dataset the way OCR4's tests/benchmark.py does).
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
    PROVIDERS,
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


# --- Provider config sanity check ----------------------------------------------

def test_all_providers_have_model_and_env_var():
    for name, cfg in PROVIDERS.items():
        assert "model" in cfg and cfg["model"], name
        assert "env_var" in cfg and cfg["env_var"], name


# --- extract_invoice orchestration (mocked litellm.completion) -----------------

def _mock_completion_response(payload: dict):
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@patch("src.llm_extractor.litellm.completion")
def test_extract_invoice_happy_path(mock_completion):
    mock_completion.return_value = _mock_completion_response(
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

    result = extract_invoice(str(SAMPLES_DIR / "sample_invoice_1.jpg"), api_key="fake-key-for-test")

    assert result.date.value == "04/08/2026"
    assert result.supplier.value == "Kerry Office Supplies Ltd"
    assert result.amount.value == "184.50"
    assert result.needs_review is False
    mock_completion.assert_called_once()

    # Confirm the image was actually sent as multimodal content, not just text.
    call_kwargs = mock_completion.call_args.kwargs
    user_message = call_kwargs["messages"][1]
    content_types = [block["type"] for block in user_message["content"]]
    assert "image_url" in content_types


@patch("src.llm_extractor.litellm.completion")
def test_extract_invoice_uses_correct_model_for_provider(mock_completion):
    mock_completion.return_value = _mock_completion_response(
        {"date": None, "date_confidence": 0, "supplier": None, "supplier_confidence": 0,
         "amount": None, "amount_confidence": 0, "currency": "EUR", "warnings": []}
    )

    extract_invoice(
        str(SAMPLES_DIR / "sample_invoice_1.jpg"),
        api_key="fake-key",
        provider="Google Gemini (free tier)",
    )
    assert mock_completion.call_args.kwargs["model"] == PROVIDERS["Google Gemini (free tier)"]["model"]


@patch("src.llm_extractor.litellm.completion")
def test_extract_invoice_flags_low_confidence_for_review(mock_completion):
    mock_completion.return_value = _mock_completion_response(
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

    result = extract_invoice(str(SAMPLES_DIR / "sample_invoice_1.jpg"), api_key="fake-key-for-test")

    assert result.needs_review is True
    assert result.supplier.value is None
    assert len(result.warnings) == 1


def test_extract_invoice_raises_without_api_key():
    with pytest.raises(ExtractionError, match="No API key provided"):
        extract_invoice(str(SAMPLES_DIR / "sample_invoice_1.jpg"), api_key=None)


def test_extract_invoice_raises_on_unknown_provider():
    with pytest.raises(ExtractionError, match="Unknown provider"):
        extract_invoice(str(SAMPLES_DIR / "sample_invoice_1.jpg"), api_key="fake-key", provider="NotAProvider")


def test_extract_invoice_raises_on_missing_file():
    with pytest.raises(ExtractionError):
        extract_invoice("/tmp/this_file_does_not_exist_12345.jpg", api_key="fake-key")


@patch("src.llm_extractor.litellm.completion")
def test_extract_invoice_raises_extraction_error_on_bad_json(mock_completion):
    message = MagicMock()
    message.content = "Sorry, I can't read this image clearly."
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    mock_completion.return_value = response

    with pytest.raises(ExtractionError):
        extract_invoice(str(SAMPLES_DIR / "sample_invoice_1.jpg"), api_key="fake-key-for-test")


@patch("src.llm_extractor.litellm.completion")
def test_extract_invoice_wraps_provider_errors(mock_completion):
    mock_completion.side_effect = RuntimeError("connection reset")
    with pytest.raises(ExtractionError):
        extract_invoice(str(SAMPLES_DIR / "sample_invoice_1.jpg"), api_key="fake-key-for-test")
