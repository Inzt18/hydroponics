"""
Supabase Storage + captures table for ESP32-CAM stills.

CAM photos are stored first (no Plant.id). The website later analyzes
a selected photo and this helper updates the same row.

Env vars (see .env):
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  SUPABASE_BUCKET   (default: cam-uploads)
  SUPABASE_TABLE    (default: captures)
"""

from __future__ import annotations

import os
from typing import Any

from supabase import Client, create_client

_client: Client | None = None
_warned = False


class SupabaseNotConfigured(RuntimeError):
    pass


def is_configured() -> bool:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return False
    if "YOUR_PROJECT" in url or key in ("your_service_role_key", ""):
        return False
    return True


def get_client() -> Client:
    global _client, _warned
    if not is_configured():
        if not _warned:
            print("[SUPABASE] skipped — set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
            _warned = True
        raise SupabaseNotConfigured(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in environment/.env"
        )
    if _client is None:
        _client = create_client(
            os.getenv("SUPABASE_URL", "").strip(),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        )
        print("[SUPABASE] connected")
    return _client


def bucket_name() -> str:
    return os.getenv("SUPABASE_BUCKET", "cam-uploads").strip() or "cam-uploads"


def table_name() -> str:
    return os.getenv("SUPABASE_TABLE", "captures").strip() or "captures"


def upload_photo(filename: str, image_bytes: bytes) -> str:
    """Upload JPEG bytes. Returns the public URL."""
    client = get_client()
    bucket = bucket_name()
    client.storage.from_(bucket).upload(
        path=filename,
        file=image_bytes,
        file_options={"content-type": "image/jpeg", "upsert": "true"},
    )
    return client.storage.from_(bucket).get_public_url(filename)


def _row_from_decision(
    filename: str,
    public_url: str,
    *,
    device: str = "esp32-cam",
    bytes_len: int | None = None,
    decision: dict[str, Any] | None = None,
    pumped: bool | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "device": device,
        "filename": filename,
        "storage_path": filename,
        "image_url": public_url,
    }
    if bytes_len is not None:
        row["bytes"] = bytes_len
    if decision:
        row["decision"] = decision
        row["is_healthy"] = decision.get("is_healthy")
        row["should_dose"] = decision.get("should_dose")
        row["severity_pct"] = decision.get("severity_pct")
        row["dose_ms"] = decision.get("dose_ms")
        row["top_issue"] = decision.get("top_issue")
        row["nutrient_deficient"] = decision.get("nutrient_deficient")
    if pumped is not None:
        row["pumped"] = pumped
    return row


def upsert_capture(
    filename: str,
    public_url: str,
    *,
    device: str = "esp32-cam",
    bytes_len: int | None = None,
    decision: dict[str, Any] | None = None,
    pumped: bool | None = None,
    plant_id_access_token: str | None = None,
) -> dict[str, Any]:
    """Insert or update a captures row keyed by filename."""
    client = get_client()
    row = _row_from_decision(
        filename,
        public_url,
        device=device,
        bytes_len=bytes_len,
        decision=decision,
        pumped=pumped,
    )
    if plant_id_access_token:
        row["plant_id_access_token"] = plant_id_access_token
    result = client.table(table_name()).upsert(row, on_conflict="filename").execute()
    return result.data[0] if result.data else row


def insert_photo_record(
    filename: str,
    public_url: str,
    *,
    decision: dict[str, Any] | None = None,
    pumped: bool | None = None,
    device: str = "esp32-cam",
    bytes_len: int | None = None,
) -> dict[str, Any]:
    return upsert_capture(
        filename,
        public_url,
        device=device,
        bytes_len=bytes_len,
        decision=decision,
        pumped=pumped,
    )


def fetch_latest(limit: int = 40) -> list[dict[str, Any]]:
    client = get_client()
    result = (
        client.table(table_name())
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_by_filename(filename: str) -> dict[str, Any] | None:
    client = get_client()
    result = (
        client.table(table_name())
        .select("*")
        .eq("filename", filename)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None
