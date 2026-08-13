"""Compatibility wrapper — storage + captures live in supabase_storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import supabase_storage


def is_configured() -> bool:
    return supabase_storage.is_configured()


def get_client():
    if not supabase_storage.is_configured():
        return None
    try:
        return supabase_storage.get_client()
    except supabase_storage.SupabaseNotConfigured:
        return None


def sync_capture(
    image_path: Path,
    image_bytes: bytes,
    *,
    device: str = "esp32-cam",
    result: dict[str, Any] | None = None,
) -> None:
    if not supabase_storage.is_configured():
        print("[SUPABASE] skipped - set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
        return

    filename = image_path.name
    decision = (result or {}).get("decision") or None
    pumped = (result or {}).get("pumped")
    token = (result or {}).get("plant_id_access_token")

    try:
        public_url = supabase_storage.upload_photo(filename, image_bytes)
    except Exception as exc:
        print(f"[SUPABASE] storage upload failed: {exc}")
        return

    try:
        supabase_storage.upsert_capture(
            filename,
            public_url,
            device=device,
            bytes_len=len(image_bytes),
            decision=decision,
            pumped=pumped,
            plant_id_access_token=token,
        )
        print(f"[SUPABASE] synced {filename}")
    except Exception as exc:
        print(f"[SUPABASE] row upsert failed: {exc}")
