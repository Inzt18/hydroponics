"""
Send dose command to ESP32 controller HTTP endpoint.
"""

from __future__ import annotations

import os
from typing import Any

import requests


def trigger_pump(
    dose_ms: int,
    *,
    esp_url: str | None = None,
    issue: str = "",
    severity_pct: int = 0,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """
    POST http://<esp-ip>/dose  JSON: {"dose_ms": N, "issue": "...", "severity_pct": N}
    """
    base = (esp_url or os.getenv("ESP32_CONTROLLER_URL", "")).rstrip("/")
    if not base:
        raise RuntimeError(
            "ESP32_CONTROLLER_URL not set (example: http://192.168.1.50)"
        )
    url = f"{base}/dose"
    payload = {
        "dose_ms": int(dose_ms),
        "issue": issue,
        "severity_pct": int(severity_pct),
    }
    resp = requests.post(url, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {"ok": True, "raw": resp.text}
