"""
Supabase Storage + captures table for ESP32-CAM stills.

CAM photos are stored first (no Plant.id). The website later analyzes
a selected photo and this helper updates the same row.

Env vars (see .env):
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  SUPABASE_BUCKET   (default: plant-photos)
  SUPABASE_TABLE    (default: captures)
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

from supabase import Client, create_client

_client: Client | None = None
_warned = False


def _jwt_claim(token: str, claim: str) -> str | None:
    if not token.startswith("eyJ"):
        return None
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        value = data.get(claim)
        return str(value) if value is not None else None
    except Exception:
        return None


def key_kind() -> str:
    """Safe label for logs/health. Never returns the secret itself."""
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if key.startswith(("sb_publishable_", "sb_anon_")):
        return "publishable"
    if key.startswith("sb_secret_"):
        return "secret"
    if key.startswith("eyJ"):
        return _jwt_claim(key, "role") or "jwt"
    return "unrecognized"


def _key_info() -> str:
    kind = key_kind()
    if kind == "publishable":
        return "publishable/anon — Storage RLS applies"
    if kind == "secret":
        return "secret"
    if kind in ("service_role", "anon", "authenticated"):
        return f"jwt role={kind}"
    if kind == "jwt":
        return "jwt role=unknown"
    return kind


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
        print(f"[SUPABASE] connected ({_key_info()}) bucket={bucket_name()}")
    return _client


def bucket_name() -> str:
    return os.getenv("SUPABASE_BUCKET", "plant-photos").strip() or "plant-photos"


def table_name() -> str:
    return os.getenv("SUPABASE_TABLE", "captures").strip() or "captures"


def upload_photo(filename: str, image_bytes: bytes) -> str:
    """Upload JPEG bytes via Storage REST. Returns the public URL."""
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise SupabaseNotConfigured(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in environment/.env"
        )
    bucket = bucket_name()
    object_url = f"{url}/storage/v1/object/{quote(bucket, safe='')}/{quote(filename, safe='')}"
    request = urllib.request.Request(
        object_url,
        data=image_bytes,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "image/jpeg",
            "x-upsert": "true",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"storage HTTP {exc.code}: {body}") from exc
    return f"{url}/storage/v1/object/public/{bucket}/{filename}"


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


def _rest_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise SupabaseNotConfigured(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in environment/.env"
        )
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{url}{path}",
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"rest HTTP {exc.code}: {err_body}") from exc
    return json.loads(raw) if raw else None


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
    name = quote(table_name(), safe="")
    try:
        result = _rest_json(
            "POST",
            f"/rest/v1/{name}?on_conflict=filename",
            row,
            extra_headers={
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
        )
        if isinstance(result, list) and result:
            return result[0]
        if isinstance(result, dict):
            return result
        return row
    except Exception as rest_exc:
        client = get_client()
        try:
            result = client.table(table_name()).upsert(row, on_conflict="filename").execute()
            return result.data[0] if result.data else row
        except Exception:
            raise rest_exc from None


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
    name = table_name()
    for column in ("created_at", "captured_at", "id"):
        try:
            result = (
                client.table(name)
                .select("*")
                .order(column, desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            continue
    result = client.table(name).select("*").limit(limit).execute()
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


def list_bucket_files(limit: int = 80) -> list[dict[str, Any]]:
    """List JPEG objects in the CAM storage bucket (newest first)."""
    client = get_client()
    bucket = bucket_name()
    entries = client.storage.from_(bucket).list(
        "",
        {
            "limit": limit,
            "offset": 0,
            "sortBy": {"column": "created_at", "order": "desc"},
        },
    )
    photos: list[dict[str, Any]] = []
    for entry in entries or []:
        name = str(entry.get("name") or "")
        lower = name.lower()
        if not lower.endswith((".jpg", ".jpeg", ".png")):
            continue
        photos.append(
            {
                "filename": name,
                "storage_path": name,
                "image_url": client.storage.from_(bucket).get_public_url(name),
                "created_at": entry.get("created_at") or entry.get("updated_at"),
                "bytes": ((entry.get("metadata") or {}).get("size")),
            }
        )
    return photos
