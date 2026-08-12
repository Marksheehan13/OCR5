"""Persistent invoice image storage backed by Supabase Storage."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from supabase import Client, create_client

BUCKET_NAME = "invoice-images"


class StorageError(Exception):
    """Raised when an invoice image cannot be stored."""


def _get_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise StorageError("Supabase credentials are not configured.")
    return create_client(url, key)


def upload_invoice_image(
    image_bytes: bytes,
    source_file: str,
    mime_type: str = "application/octet-stream",
    client_id: int | None = None,
) -> str:
    """Upload an invoice image into a client-specific storage namespace."""
    if not image_bytes:
        raise StorageError("Invoice image is empty.")
    if client_id is None:
        raise StorageError("Client id is required for invoice image storage.")

    suffix = Path(source_file).suffix.lower() or ".bin"
    object_path = f"clients/{client_id}/invoices/{uuid.uuid4().hex}{suffix}"

    try:
        client = _get_client()
        client.storage.from_(BUCKET_NAME).upload(
            object_path,
            image_bytes,
            {"content-type": mime_type, "upsert": "false"},
        )
    except Exception as exc:  # noqa: BLE001
        raise StorageError(f"Could not upload invoice image: {exc}") from exc

    return object_path


def create_invoice_image_url(image_path: str, expires_in: int = 3600) -> str:
    """Create a temporary signed URL for a private invoice image."""
    if not image_path or image_path.startswith("http"):
        return image_path

    try:
        client = _get_client()
        response = client.storage.from_(BUCKET_NAME).create_signed_url(image_path, expires_in)
        if isinstance(response, dict):
            return response.get("signedURL") or response.get("signedUrl") or ""
        return ""
    except Exception as exc:  # noqa: BLE001
        raise StorageError(f"Could not create invoice image URL: {exc}") from exc


def get_storage_client() -> Client:
    """Return the application storage client for server-side operations."""
    return _get_client()
