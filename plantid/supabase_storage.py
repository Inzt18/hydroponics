"""
Supabase Storage + table helper for the plantid CAM bridge.

Replaces (or supplements) local disk storage of:
  - JPEG photos from the ESP32-CAM
  - Plant.id result JSON per photo

Env vars needed (see .env):
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY   (server-side key, keep secret, never on the ESP32)
  SUPABASE_BUCKET             (default: "plant-photos")
  SUPABASE_TABLE              (default: "photos")
"""

from __future__ import annotations

import os
from typing import Any

from supabase import Client, create_client

_client: Client | None = None


class SupabaseNotConfigured(RuntimeError):
    pass


def get_client() -> Client:
    """Lazily create and cache the Supabase client."""
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise SupabaseNotConfigured(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in environment/.env"
        )
    _client = create_client(url, key)
    return _client


def bucket_name() -> str:
    return os.getenv("SUPABASE_BUCKET", "plant-photos").strip()


def table_name() -> str:
    return os.getenv("SUPABASE_TABLE", "photos").strip()


def upload_photo(filename: str, image_bytes: bytes) -> str:
    """
    Upload JPEG bytes to Supabase Storage. Returns the public URL.
    `filename` should already be unique (e.g. cam_20260813_120500.jpg).
    """
    client = get_client()
    bucket = bucket_name()

    client.storage.from_(bucket).upload(
        path=filename,
        file=image_bytes,
        file_options={"content-type": "image/jpeg", "upsert": "true"},
    )
    return client.storage.from_(bucket).get_public_url(filename)


def insert_photo_record(
    filename: str,
    public_url: str,
    *,
    decision: dict[str, Any] | None = None,
    pumped: bool | None = None,
) -> dict[str, Any]:
    """
    Insert a row into the `photos` table so the dashboard/API can query
    latest results without listing the whole bucket.
    """
    client = get_client()
    row: dict[str, Any] = {
        "file_path": filename,
        "url": public_url,
    }
    if decision is not None:
        row["decision"] = decision
    if pumped is not None:
        row["pumped"] = pumped

    result = client.table(table_name()).insert(row).execute()
    return result.data[0] if result.data else row


def fetch_latest(limit: int = 20) -> list[dict[str, Any]]:
    """Fetch the most recent photo/result rows, newest first."""
    client = get_client()
    result = (
        client.table(table_name())
        .select("*")
        .order("captured_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []
