"""One-shot: apply captures table + cam-uploads bucket using .env keys."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "supabase" / "migrations" / "20260813124900_init.sql"


def main() -> int:
    load_dotenv(ROOT / ".env")
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or "YOUR_PROJECT" in url or not key or key == "your_service_role_key":
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
        return 1

    sql = SQL_PATH.read_text(encoding="utf-8")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    applied = False
    for endpoint in (
        f"{url}/pg/query",
        f"{url}/pg-meta/default/query",
    ):
        try:
            resp = httpx.post(
                endpoint,
                headers=headers,
                json={"query": sql},
                timeout=30.0,
            )
            print(f"SQL {endpoint.split(url)[-1]} -> HTTP {resp.status_code}")
            if resp.status_code < 400:
                applied = True
                break
        except Exception as exc:
            print(f"SQL endpoint failed: {type(exc).__name__}")

    client = create_client(url, key)
    try:
        client.storage.create_bucket("cam-uploads", options={"public": True})
        print("bucket cam-uploads: created")
    except Exception as exc:
        print(f"bucket create: {type(exc).__name__}: {exc}")

    try:
        names = []
        for bucket in client.storage.list_buckets():
            names.append(getattr(bucket, "name", None) or str(bucket))
        print("buckets:", names)
    except Exception as exc:
        print(f"list buckets: {type(exc).__name__}: {exc}")

    try:
        client.table("captures").select("id").limit(1).execute()
        print("captures table: ready")
        applied = True
    except Exception as exc:
        print(f"captures table: {type(exc).__name__}: {exc}")

    if not applied:
        print("Could not apply SQL via API. Run supabase/migrations/20260813124900_init.sql in the SQL Editor.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
