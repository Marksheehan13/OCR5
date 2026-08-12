"""Persistent invoice image storage backed by Supabase Storage."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from supabase import Client, create_client
from .db_context import get_bound_client

BUCKET_NAME = "invoice-images"


class StorageError(Exception):
    """Raised when an invoice image cannot be stored."""


def _get_client() -> Client:
    bound = get_bound_client()
    if bound is not None:
        return bound
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise StorageError("Supabase credentials are not configured.")
    return create_client(url, key)


def upload_invoice_image(image_bytes: bytes, source_file: str, mime_type: str = "application/octet-stream", client_id: int | None = None) -> str:
    if not image_bytes: raise StorageError("Invoice image is empty.")
    if client_id is None: raise StorageError("Client id is required for invoice image storage.")
    suffix = Path(source_file).suffix.lower() or ".bin"
    object_path = f"clients/{client_id}/invoices/{uuid.uuid4().hex}{suffix}"
    try:
        _get_client().storage.from_(BUCKET_NAME).upload(object_path, image_bytes, {"content-type": mime_type, "upsert": "false"})
    except Exception as exc:
        raise StorageError(f"Could not upload invoice image: {exc}") from exc
    return object_path


def create_invoice_image_url(image_path: str, expires_in: int = 3600) -> str:
    if not image_path or image_path.startswith("http"): return image_path
    try:
        response = _get_client().storage.from_(BUCKET_NAME).create_signed_url(image_path, expires_in)
        if isinstance(response, dict): return response.get("signedURL") or response.get("signedUrl") or ""
        return ""
    except Exception as exc:
        raise StorageError(f"Could not create invoice image URL: {exc}") from exc
