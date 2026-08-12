#!/usr/bin/env python3
"""
Plant.id → fertigation bridge

Flow:
  leaf image → Plant.id health_assessment → dose decision → optional ESP32 /dose

Usage:
  set PLANT_ID_API_KEY=...
  python -m plantid.bridge --image path\\to\\leaf.jpg
  python -m plantid.bridge --image leaf.jpg --trigger-pump
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .client import PlantIdClient, PlantIdError
from .decision import decide_dose
from .esp_trigger import trigger_pump


def main(argv: list[str] | None = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Plant.id fertigation bridge")
    parser.add_argument("--image", type=Path, required=True, help="Leaf/plant photo")
    parser.add_argument(
        "--trigger-pump",
        action="store_true",
        help="POST dose to ESP32_CONTROLLER_URL /dose",
    )
    parser.add_argument(
        "--esp-url",
        default=os.getenv("ESP32_CONTROLLER_URL", ""),
        help="ESP32 base URL, e.g. http://192.168.1.50",
    )
    parser.add_argument("--dose-base", type=int, default=3000)
    parser.add_argument("--dose-max", type=int, default=12000)
    parser.add_argument("--severity-min", type=int, default=35)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "output" / "last_plantid.json",
    )
    args = parser.parse_args(argv)

    if not args.image.exists():
        print(f"Image not found: {args.image}", file=sys.stderr)
        return 1

    try:
        client = PlantIdClient()
        print(f"[Plant.id] assessing {args.image} ...")
        health = client.health_assessment(args.image)
    except PlantIdError as exc:
        print(f"[Plant.id] ERROR: {exc}", file=sys.stderr)
        return 2

    decision = decide_dose(
        health,
        dose_ms_base=args.dose_base,
        dose_ms_max=args.dose_max,
        severity_min=args.severity_min,
    )

    payload = {
        "image": str(args.image),
        "decision": decision.to_dict(),
        "plant_id_access_token": health.get("access_token"),
        "is_healthy_raw": (health.get("result") or {}).get("is_healthy"),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("=== Plant.id Fertigation Decision ===")
    print(json.dumps(decision.to_dict(), indent=2))
    print(f"Saved: {args.out}")

    if decision.should_dose:
        print(
            f"\n[BRIDGE] Would dose {decision.dose_ms} ms "
            f"(issue={decision.top_issue})"
        )
        if args.trigger_pump:
            try:
                resp = trigger_pump(
                    decision.dose_ms,
                    esp_url=args.esp_url or None,
                    issue=decision.top_issue,
                    severity_pct=decision.severity_pct,
                )
                print(f"[ESP32] /dose response: {resp}")
            except Exception as exc:
                print(f"[ESP32] trigger failed: {exc}", file=sys.stderr)
                return 3
        else:
            print("[BRIDGE] Pump not triggered (pass --trigger-pump to send to ESP32)")
    else:
        print("\n[BRIDGE] Healthy / below threshold — pump stays OFF")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
