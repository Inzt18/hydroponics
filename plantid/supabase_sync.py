"""Push camera stills + Plant.id results to Supabase (Storage + Postgres)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_client = None
_warned = False


def is_configured() -> bool:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return False
    if "YOUR_PROJECT" in url or key == "your_service_role_key":
        return False
    return True


def get_client():
    global _client, _warned
    if not is_configured():
        if not _warned:
            print("[SUPABASE] skipped - set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
            _warned = True
        return None
    if _client is None:
        from supabase import create_client

        _client = create_client(
            os.getenv("SUPABASE_URL", "").strip(),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        )
        print("[SUPABASE] connected")
    return _client


def sync_capture(
    image_path: Path,
    image_bytes: bytes,
    *,
    device: str = "esp32-cam",
    result: dict[str, Any] | None = None,
) -> None:
    client = get_client()
    if client is None:
        return

    filename = image_path.name
    storage_path = filename
    decision = (result or {}).get("decision") or {}

    try:
        client.storage.from_("cam-uploads").upload(
            storage_path,
            image_bytes,
            file_options={
                "content-type": "image/jpeg",
                "upsert": "true",
            },
        )
    except Exception as exc:
        print(f"[SUPABASE] storage upload failed: {exc}")
        return

    image_url = client.storage.from_("cam-uploads").get_public_url(storage_path)
    row = {
        "device": device,
        "filename": filename,
        "storage_path": storage_path,
        "bytes": len(image_bytes),
        "image_url": image_url,
        "is_healthy": decision.get("is_healthy"),
        "should_dose": decision.get("should_dose"),
        "severity_pct": decision.get("severity_pct"),
        "dose_ms": decision.get("dose_ms"),
        "top_issue": decision.get("top_issue"),
        "nutrient_deficient": decision.get("nutrient_deficient"),
        "pumped": (result or {}).get("pumped"),
        "decision": decision or None,
        "plant_id_access_token": (result or {}).get("plant_id_access_token"),
    }

    try:
        client.table("captures").upsert(row, on_conflict="filename").execute()
        print(f"[SUPABASE] synced {filename}")
    except Exception as exc:
        print(f"[SUPABASE] row upsert failed: {exc}")
