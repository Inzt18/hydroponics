#!/usr/bin/env python3
"""
HTTP ingest server for ESP32-CAM → Plant.id → ESP32 pump.

ESP32-CAM POSTs JPEG to:
  POST http://<laptop-ip>:8080/ingest
  Content-Type: image/jpeg
  Body: raw JPEG bytes

Then this server:
  1) saves the image
  2) calls Plant.id health_assessment
  3) optionally POSTs /dose to ESP32 controller
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from .client import PlantIdClient, PlantIdError
from .decision import decide_dose
from .esp_trigger import trigger_pump

load_dotenv()

app = Flask(__name__)

OUT_DIR = Path(__file__).resolve().parent / "output" / "cam_uploads"
OUT_DIR.mkdir(parents=True, exist_ok=True)

AUTO_TRIGGER = os.getenv("PLANTID_AUTO_TRIGGER", "1").strip() not in ("0", "false", "False")
DOSE_BASE = int(os.getenv("DOSE_MS_BASE", "3000"))
DOSE_MAX = int(os.getenv("DOSE_MS_MAX", "12000"))
SEVERITY_MIN = int(os.getenv("DOSE_SEVERITY_MIN", "35"))


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "plantid-cam-bridge",
            "auto_trigger": AUTO_TRIGGER,
            "esp_url": os.getenv("ESP32_CONTROLLER_URL", ""),
        }
    )


@app.post("/ingest")
def ingest():
    """
    Accept raw JPEG body or multipart file field named 'image' / 'file'.
    """
    image_bytes = b""
    if request.files:
        f = request.files.get("image") or request.files.get("file")
        if f:
            image_bytes = f.read()
    if not image_bytes:
        image_bytes = request.get_data(cache=False)

    if not image_bytes or len(image_bytes) < 100:
        return jsonify({"ok": False, "error": "empty/invalid image"}), 400

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = OUT_DIR / f"cam_{stamp}.jpg"
    image_path.write_bytes(image_bytes)

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

    (OUT_DIR / f"cam_{stamp}_result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

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

    print(
        f"[INGEST] {image_path.name} → healthy={decision.is_healthy} "
        f"issue={decision.top_issue} dose={decision.dose_ms}ms pumped={result['pumped']}"
    )
    return jsonify(result)


def main() -> None:
    host = os.getenv("PLANTID_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("PLANTID_SERVER_PORT", "8080"))
    print("=== Plant.id CAM bridge server ===")
    print(f"Listening on http://{host}:{port}")
    print("ESP32-CAM should POST JPEG to /ingest")
    print(f"Auto pump trigger: {AUTO_TRIGGER}")
    print(f"ESP32_CONTROLLER_URL={os.getenv('ESP32_CONTROLLER_URL', '')}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
