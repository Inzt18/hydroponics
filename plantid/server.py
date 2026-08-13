#!/usr/bin/env python3
"""
HTTP ingest server for ESP32-CAM → Plant.id → ESP32 pump.

Also serves a simple local dashboard:
  http://127.0.0.1:8080/
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template, send_from_directory

from .client import PlantIdClient, PlantIdError
from .decision import classify_nutrient, decide_dose
from .esp_trigger import trigger_pump
from . import supabase_storage

load_dotenv()

app = Flask(__name__)

# When true, photos + results are pushed to Supabase Storage/table in addition
# to (or instead of) local disk. Set SUPABASE_ENABLED=0 to disable entirely.
SUPABASE_ENABLED = os.getenv("SUPABASE_ENABLED", "1").strip() not in ("0", "false", "False")


@app.after_request
def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Device"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

OUT_DIR = Path(__file__).resolve().parent / "output" / "cam_uploads"
OUT_DIR.mkdir(parents=True, exist_ok=True)

AUTO_TRIGGER = os.getenv("PLANTID_AUTO_TRIGGER", "1").strip() not in ("0", "false", "False")
DOSE_BASE = int(os.getenv("DOSE_MS_BASE", "3000"))
DOSE_MAX = int(os.getenv("DOSE_MS_MAX", "12000"))
SEVERITY_MIN = int(os.getenv("DOSE_SEVERITY_MIN", "35"))
CAM_STILL_URL = os.getenv("ESP32_CAM_STILL_URL", "").strip()
CAM_PULL_INTERVAL_S = float(os.getenv("ESP32_CAM_PULL_INTERVAL_S", "10"))


def _enrich_decision(decision: dict) -> dict:
    """Backfill nutrient labels on older saved results."""
    if not isinstance(decision, dict):
        return {}
    if decision.get("nutrient_deficient") and "nutrient_candidates" in decision:
        return decision

    suggestions = decision.get("raw_suggestions") or []
    candidates: list[dict] = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        blob = f"{s.get('name', '')} {s.get('description', '')}"
        label = classify_nutrient(blob)
        if label:
            candidates.append(
                {
                    "nutrient": label,
                    "source_issue": s.get("name") or "",
                    "probability": float(s.get("probability") or 0.0),
                }
            )

    best: dict[str, dict] = {}
    for c in candidates:
        key = c["nutrient"]
        if key not in best or c["probability"] > best[key]["probability"]:
            best[key] = c
    candidates = sorted(best.values(), key=lambda x: x["probability"], reverse=True)

    if not decision.get("nutrient_deficient"):
        if decision.get("is_healthy"):
            decision["nutrient_deficient"] = "None"
        elif candidates:
            decision["nutrient_deficient"] = candidates[0]["nutrient"]
        elif decision.get("top_issue") and decision["top_issue"] not in ("healthy",):
            decision["nutrient_deficient"] = (
                classify_nutrient(str(decision["top_issue"])) or "Not nutrient-specific"
            )
        else:
            decision["nutrient_deficient"] = "None"

    if "nutrient_candidates" not in decision:
        decision["nutrient_candidates"] = candidates
    return decision


def _load_results(limit: int = 20) -> list[dict]:
    items: list[dict] = []
    for path in sorted(OUT_DIR.glob("cam_*_result.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        stamp = path.name.replace("cam_", "").replace("_result.json", "")
        image_name = f"cam_{stamp}.jpg"
        data["stamp"] = stamp
        data["image_name"] = image_name
        data["image_url"] = f"/uploads/{image_name}"
        data["pumped"] = bool(data.get("pumped"))
        data["decision"] = _enrich_decision(data.get("decision") or {})
        items.append(data)
        if len(items) >= limit:
            break
    return items


@app.get("/")
def dashboard():
    return render_template("dashboard.html")


@app.get("/api/latest")
def api_latest():
    return jsonify({"ok": True, "items": _load_results(20)})


@app.get("/uploads/<path:filename>")
def uploads(filename: str):
    return send_from_directory(OUT_DIR, filename)


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "plantid-cam-bridge",
            "auto_trigger": AUTO_TRIGGER,
            "esp_url": os.getenv("ESP32_CONTROLLER_URL", ""),
            "cam_still_url": CAM_STILL_URL,
            "dashboard": "/",
        }
    )


def _read_image_bytes() -> bytes:
    image_bytes = b""
    if request.files:
        f = request.files.get("image") or request.files.get("file")
        if f:
            image_bytes = f.read()
    if not image_bytes:
        image_bytes = request.get_data(cache=False)
    return image_bytes


def _save_jpeg(image_bytes: bytes) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = OUT_DIR / f"cam_{stamp}.jpg"
    n = 1
    while image_path.exists():
        image_path = OUT_DIR / f"cam_{stamp}_{n}.jpg"
        n += 1
    image_path.write_bytes(image_bytes)
    return image_path


def _upload_to_supabase(
    image_path: Path,
    image_bytes: bytes,
    *,
    decision: dict | None = None,
    pumped: bool | None = None,
) -> str | None:
    """
    Push the photo (and optional decision/pumped info) to Supabase.
    Returns the public URL on success, or None if Supabase is disabled
    or upload fails (failure is logged, never raised — local save already
    succeeded so a Supabase hiccup shouldn't break the ESP32's request).
    """
    if not SUPABASE_ENABLED:
        return None
    try:
        public_url = supabase_storage.upload_photo(image_path.name, image_bytes)
        supabase_storage.insert_photo_record(
            image_path.name, public_url, decision=decision, pumped=pumped
        )
        return public_url
    except supabase_storage.SupabaseNotConfigured as exc:
        print(f"[SUPABASE] not configured, skipping upload: {exc}")
    except Exception as exc:
        print(f"[SUPABASE] upload failed for {image_path.name}: {exc}")
    return None


@app.route("/upload", methods=["POST", "OPTIONS"])
def upload():
    """Save JPEG only (no Plant.id, no pump). Used by the still-test sketch."""
    if request.method == "OPTIONS":
        return ("", 204)

    image_bytes = _read_image_bytes()
    if not image_bytes or len(image_bytes) < 100:
        return jsonify({"ok": False, "error": "empty/invalid image"}), 400

    image_path = _save_jpeg(image_bytes)
    print(f"[UPLOAD] saved {image_path.name} ({len(image_bytes)} bytes)")

    public_url = _upload_to_supabase(image_path, image_bytes)

    return jsonify(
        {
            "ok": True,
            "saved": str(image_path),
            "bytes": len(image_bytes),
            "supabase_url": public_url,
        }
    )


@app.post("/ingest")
def ingest():
    """
    Accept raw JPEG body or multipart file field named 'image' / 'file'.
    """
    image_bytes = _read_image_bytes()

    if not image_bytes or len(image_bytes) < 100:
        return jsonify({"ok": False, "error": "empty/invalid image"}), 400

    image_path = _save_jpeg(image_bytes)
    stamp = image_path.stem.replace("cam_", "", 1)

    try:
        client = PlantIdClient()
        health_json = client.health_assessment(image_path)
    except PlantIdError as exc:
        return jsonify({"ok": False, "error": str(exc), "saved": str(image_path)}), 502

    decision = decide_dose(
        health_json,
        dose_ms_base=DOSE_BASE,
        dose_ms_max=DOSE_MAX,
        severity_min=SEVERITY_MIN,
    )

    result = {
        "ok": True,
        "saved": str(image_path),
        "decision": decision.to_dict(),
        "plant_id_access_token": health_json.get("access_token"),
    }

    if decision.should_dose and AUTO_TRIGGER:
        try:
            esp_resp = trigger_pump(
                decision.dose_ms,
                issue=decision.top_issue,
                severity_pct=decision.severity_pct,
            )
            result["esp_trigger"] = esp_resp
            result["pumped"] = True
        except Exception as exc:
            result["esp_trigger_error"] = str(exc)
            result["pumped"] = False
    else:
        result["pumped"] = False
        result["pump_reason"] = (
            "below threshold/healthy"
            if not decision.should_dose
            else "auto_trigger disabled"
        )

    (OUT_DIR / f"cam_{stamp}_result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    public_url = _upload_to_supabase(
        image_path,
        image_bytes,
        decision=decision.to_dict(),
        pumped=result["pumped"],
    )
    result["supabase_url"] = public_url

    print(
        f"[INGEST] {image_path.name} → healthy={decision.is_healthy} "
        f"nutrient={decision.nutrient_deficient} issue={decision.top_issue} "
        f"dose={decision.dose_ms}ms pumped={result['pumped']} "
        f"supabase={'ok' if public_url else 'skipped'}"
    )
    return jsonify(result)


def _pull_cam_stills() -> None:
    """Laptop pulls /still from the ESP32. Avoids Windows firewall blocking CAM→PC POSTs."""
    if not CAM_STILL_URL:
        return
    print(f"[PULL] fetching {CAM_STILL_URL} every {CAM_PULL_INTERVAL_S:.0f}s")
    last_hash = ""
    while True:
        try:
            sep = "&" if "?" in CAM_STILL_URL else "?"
            url = f"{CAM_STILL_URL}{sep}t={int(time.time() * 1000)}"
            req = urllib.request.Request(url, headers={"Cache-Control": "no-store"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            if data and len(data) >= 100:
                digest = hashlib.md5(data).hexdigest()
                if digest != last_hash:
                    path = _save_jpeg(data)
                    last_hash = digest
                    print(f"[PULL] saved {path.name} ({len(data)} bytes)")
        except Exception as exc:
            print(f"[PULL] failed: {exc}")
        time.sleep(CAM_PULL_INTERVAL_S)


def main() -> None:
    host = os.getenv("PLANTID_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("PLANTID_SERVER_PORT", "8080"))
    print("=== Plant.id CAM bridge + dashboard ===")
    print(f"Dashboard: http://127.0.0.1:{port}/")
    print(f"Listening on http://{host}:{port}")
    print("ESP32-CAM should POST JPEG to /ingest (Plant.id) or /upload (save only)")
    print(f"Auto pump trigger: {AUTO_TRIGGER}")
    print(f"ESP32_CONTROLLER_URL={os.getenv('ESP32_CONTROLLER_URL', '')}")
    if CAM_STILL_URL:
        print(f"Pulling stills from {CAM_STILL_URL}")
        threading.Thread(target=_pull_cam_stills, daemon=True).start()
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
