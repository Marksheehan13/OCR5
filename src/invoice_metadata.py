"""Helpers for invoice number and VAT metadata."""

from __future__ import annotations


def to_float(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
