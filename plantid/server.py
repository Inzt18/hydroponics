#!/usr/bin/env python3
"""
HTTP ingest server for ESP32-CAM → Supabase → website picker → Plant.id.

ESP32-CAM POSTs JPEG to /upload (or /ingest). Photos are stored in
Supabase (and local disk). The dashboard lists them so you choose which
one to analyze via POST /analyze.
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

SUPABASE_ENABLED = os.getenv("SUPABASE_ENABLED", "1").strip() not in ("0", "false", "False")

OUT_DIR = Path(__file__).resolve().parent / "output" / "cam_uploads"
OUT_DIR.mkdir(parents=True, exist_ok=True)

AUTO_TRIGGER = os.getenv("PLANTID_AUTO_TRIGGER", "1").strip() not in ("0", "false", "False")
DOSE_BASE = int(os.getenv("DOSE_MS_BASE", "3000"))
DOSE_MAX = int(os.getenv("DOSE_MS_MAX", "12000"))
SEVERITY_MIN = int(os.getenv("DOSE_SEVERITY_MIN", "35"))
CAM_STILL_URL = os.getenv("ESP32_CAM_STILL_URL", "").strip()
CAM_PULL_INTERVAL_S = float(os.getenv("ESP32_CAM_PULL_INTERVAL_S", "10"))


@app.after_request
def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Device"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


def _device_name() -> str:
    return (request.headers.get("X-Device") or "esp32-cam").strip() or "esp32-cam"


def _stamp_from_name(filename: str) -> str:
    name = Path(filename).stem
    if name.startswith("cam_"):
        return name[4:]
    return name


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


def _item_from_local(jpg_path: Path) -> dict:
    stamp = _stamp_from_name(jpg_path.name)
    item = {
        "id": None,
        "stamp": stamp,
        "image_name": jpg_path.name,
        "image_url": f"/uploads/{jpg_path.name}",
        "analyzed": False,
        "pumped": False,
        "decision": {},
        "bytes": jpg_path.stat().st_size,
        "created_at": datetime.fromtimestamp(jpg_path.stat().st_mtime).isoformat(),
        "source": "render",
    }
    result_path = OUT_DIR / f"cam_{stamp}_result.json"
    if result_path.exists():
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        item["analyzed"] = True
        item["pumped"] = bool(data.get("pumped"))
        item["decision"] = _enrich_decision(data.get("decision") or {})
        item["plant_id_access_token"] = data.get("plant_id_access_token")
    return item


def _item_from_row(row: dict) -> dict:
    filename = row.get("filename") or row.get("storage_path") or ""
    decision = _enrich_decision(row.get("decision") or {})
    analyzed = bool(decision)
    return {
        "id": row.get("id"),
        "stamp": _stamp_from_name(filename),
        "image_name": filename,
        "image_url": row.get("image_url") or f"/uploads/{filename}",
        "analyzed": analyzed,
        "pumped": bool(row.get("pumped")),
        "decision": decision,
        "bytes": row.get("bytes"),
        "created_at": row.get("created_at"),
        "device": row.get("device") or "esp32-cam",
        "source": "supabase",
    }


def _load_results(limit: int = 40) -> list[dict]:
    by_name: dict[str, dict] = {}
    for path in sorted(OUT_DIR.glob("cam_*.jpg"), reverse=True):
        by_name[path.name] = _item_from_local(path)

    if SUPABASE_ENABLED and supabase_storage.is_configured():
        try:
            for row in supabase_storage.fetch_latest(max(limit, 40)):
                filename = row.get("filename") or ""
                if not filename:
                    continue
                remote = _item_from_row(row)
                local = by_name.get(filename)
                if local:
                    if remote.get("image_url") and str(remote["image_url"]).startswith("http"):
                        local["image_url"] = remote["image_url"]
                    if remote.get("analyzed"):
                        local["analyzed"] = True
                        local["decision"] = remote["decision"]
                        local["pumped"] = remote["pumped"]
                    local["id"] = remote.get("id") or local.get("id")
                else:
                    by_name[filename] = remote
        except Exception as exc:
            print(f"[SUPABASE] table list failed: {exc}")
        try:
            for obj in supabase_storage.list_bucket_files(max(limit, 40)):
                filename = obj.get("filename") or ""
                if not filename:
                    continue
                if filename not in by_name:
                    by_name[filename] = {
                        "id": None,
                        "stamp": _stamp_from_name(filename),
                        "image_name": filename,
                        "image_url": obj.get("image_url"),
                        "analyzed": False,
                        "pumped": False,
                        "decision": {},
                        "bytes": obj.get("bytes"),
                        "created_at": obj.get("created_at"),
                        "device": "esp32-cam",
                        "source": "supabase",
                    }
        except Exception as exc:
            print(f"[SUPABASE] storage list failed: {exc}")

    items = sorted(
        by_name.values(),
        key=lambda x: x.get("created_at") or x.get("stamp") or "",
        reverse=True,
    )
    return items[:limit]


@app.get("/")
def dashboard():
    return render_template("dashboard.html")


@app.get("/api/latest")
def api_latest():
    return jsonify({"ok": True, "items": _load_results(40)})


@app.get("/api/photos")
def api_photos():
    """ESP32-CAM stills from Supabase Storage (for the Choose File picker)."""
    items = _load_results(80)
    supabase_ok = SUPABASE_ENABLED and supabase_storage.is_configured()
    return jsonify(
        {
            "ok": True,
            "supabase": supabase_ok,
            "count": len(items),
            "items": items,
        }
    )


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
            "supabase": supabase_storage.is_configured(),
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
    device: str = "esp32-cam",
    decision: dict | None = None,
    pumped: bool | None = None,
    plant_id_access_token: str | None = None,
) -> str | None:
    if not SUPABASE_ENABLED or not supabase_storage.is_configured():
        return None
    try:
        public_url = supabase_storage.upload_photo(image_path.name, image_bytes)
        supabase_storage.upsert_capture(
            image_path.name,
            public_url,
            device=device,
            bytes_len=len(image_bytes),
            decision=decision,
            pumped=pumped,
            plant_id_access_token=plant_id_access_token,
        )
        print(f"[SUPABASE] stored {image_path.name}")
        return public_url
    except supabase_storage.SupabaseNotConfigured as exc:
        print(f"[SUPABASE] not configured, skipping upload: {exc}")
    except Exception as exc:
        print(f"[SUPABASE] upload failed for {image_path.name}: {exc}")
    return None


def _store_photo(image_bytes: bytes, device: str = "esp32-cam") -> tuple[Path, str | None]:
    image_path = _save_jpeg(image_bytes)
    public_url = _upload_to_supabase(image_path, image_bytes, device=device)
    return image_path, public_url


def _ensure_local_jpeg(filename: str, image_url: str | None = None) -> Path:
    safe = Path(filename).name
    if not safe or safe != filename or ".." in filename:
        raise ValueError("invalid filename")
    path = OUT_DIR / safe
    if path.exists() and path.stat().st_size >= 100:
        return path
    if image_url and str(image_url).startswith("http"):
        urllib.request.urlretrieve(image_url, path)
        if path.exists() and path.stat().st_size >= 100:
            return path
    raise FileNotFoundError(filename)


def _run_plantid(image_path: Path) -> dict:
    client = PlantIdClient()
    health_json = client.health_assessment(image_path)
    decision = decide_dose(
        health_json,
        dose_ms_base=DOSE_BASE,
        dose_ms_max=DOSE_MAX,
        severity_min=SEVERITY_MIN,
    )
    result = {
        "ok": True,
        "saved": str(image_path),
        "image_name": image_path.name,
        "stamp": _stamp_from_name(image_path.name),
        "decision": decision.to_dict(),
        "plant_id_access_token": health_json.get("access_token"),
        "analyzed": True,
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

    stamp = result["stamp"]
    (OUT_DIR / f"cam_{stamp}_result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    image_bytes = image_path.read_bytes()
    public_url = _upload_to_supabase(
        image_path,
        image_bytes,
        device="esp32-cam",
        decision=decision.to_dict(),
        pumped=result["pumped"],
        plant_id_access_token=result.get("plant_id_access_token"),
    )
    result["supabase_url"] = public_url
    result["image_url"] = public_url or f"/uploads/{image_path.name}"

    print(
        f"[ANALYZE] {image_path.name} -> healthy={decision.is_healthy} "
        f"nutrient={decision.nutrient_deficient} issue={decision.top_issue} "
        f"dose={decision.dose_ms}ms pumped={result['pumped']} "
        f"supabase={'ok' if public_url else 'skipped'}"
    )
    return result


def _save_only_response(image_bytes: bytes):
    if not image_bytes or len(image_bytes) < 100:
        return jsonify({"ok": False, "error": "empty/invalid image"}), 400
    image_path, public_url = _store_photo(image_bytes, _device_name())
    print(f"[UPLOAD] saved {image_path.name} ({len(image_bytes)} bytes)")
    return jsonify(
        {
            "ok": True,
            "saved": str(image_path),
            "image_name": image_path.name,
            "stamp": _stamp_from_name(image_path.name),
            "bytes": len(image_bytes),
            "analyzed": False,
            "supabase_url": public_url,
            "image_url": public_url or f"/uploads/{image_path.name}",
        }
    )


@app.route("/upload", methods=["POST", "OPTIONS"])
def upload():
    """Save JPEG to disk + Supabase. No Plant.id until /analyze."""
    if request.method == "OPTIONS":
        return ("", 204)
    return _save_only_response(_read_image_bytes())


@app.route("/ingest", methods=["POST", "OPTIONS"])
def ingest():
    """Same as /upload: store the still. Analysis is chosen on the website."""
    if request.method == "OPTIONS":
        return ("", 204)
    return _save_only_response(_read_image_bytes())


@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    """Run Plant.id on a stored photo (or a newly uploaded file)."""
    if request.method == "OPTIONS":
        return ("", 204)

    if request.files:
        image_bytes = _read_image_bytes()
        if not image_bytes or len(image_bytes) < 100:
            return jsonify({"ok": False, "error": "empty/invalid image"}), 400
        image_path, _public_url = _store_photo(image_bytes, _device_name())
        try:
            return jsonify(_run_plantid(image_path))
        except PlantIdError as exc:
            return jsonify({"ok": False, "error": str(exc), "saved": str(image_path)}), 502

    payload = request.get_json(silent=True) or {}
    filename = (payload.get("filename") or payload.get("image_name") or "").strip()
    image_url = (payload.get("image_url") or "").strip() or None

    if not filename:
        return jsonify({"ok": False, "error": "filename required"}), 400

    if SUPABASE_ENABLED and supabase_storage.is_configured() and not image_url:
        try:
            row = supabase_storage.get_by_filename(filename)
            if row:
                image_url = row.get("image_url")
        except Exception as exc:
            print(f"[SUPABASE] lookup failed: {exc}")

    try:
        image_path = _ensure_local_jpeg(filename, image_url)
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"ok": False, "error": f"photo not found: {exc}"}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": f"could not load photo: {exc}"}), 502

    try:
        return jsonify(_run_plantid(image_path))
    except PlantIdError as exc:
        return jsonify({"ok": False, "error": str(exc), "saved": str(image_path)}), 502


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
                    path, public_url = _store_photo(data, "esp32-cam")
                    last_hash = digest
                    print(
                        f"[PULL] saved {path.name} ({len(data)} bytes) "
                        f"supabase={'ok' if public_url else 'skipped'}"
                    )
        except Exception as exc:
            print(f"[PULL] failed: {exc}")
        time.sleep(CAM_PULL_INTERVAL_S)


def main() -> None:
    host = os.getenv("PLANTID_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("PLANTID_SERVER_PORT", "8080"))
    print("=== Plant.id CAM bridge + dashboard ===")
    print(f"Dashboard: http://127.0.0.1:{port}/")
    print(f"Listening on http://{host}:{port}")
    print("ESP32-CAM should POST JPEG to /upload (save to Supabase). Analyze from the website.")
    print(f"Auto pump trigger: {AUTO_TRIGGER}")
    print(f"ESP32_CONTROLLER_URL={os.getenv('ESP32_CONTROLLER_URL', '')}")
    if supabase_storage.is_configured():
        print("Supabase: connected (stills -> Storage + public.captures)")
    else:
        print("Supabase: not configured (photos stay on local disk until keys are set)")
    if CAM_STILL_URL:
        print(f"Pulling stills from {CAM_STILL_URL}")
        threading.Thread(target=_pull_cam_stills, daemon=True).start()
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
