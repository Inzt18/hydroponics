#!/usr/bin/env python3
"""
Offline digital twin for the solar ESP32 fertigation system.

Simulates: capture → thumbnail → deficiency detect → pump dose decision.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from deficiency_detector import DEF_NAMES, detect_nutrient_deficiency, thumbnail_from_image
from plant_sim import make_leaf


def load_image(path: Path) -> np.ndarray:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit("Install Pillow: pip install Pillow") from exc

    img = Image.open(path).convert("RGB")
    return np.asarray(img, dtype=np.uint8)


def save_preview(rgb: np.ndarray, path: Path) -> None:
    try:
        from PIL import Image
    except ImportError:
        return
    Image.fromarray(rgb).save(path)


def run_once(kind: str | None, image: Path | None, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    if image:
        full = load_image(image)
        source = str(image)
    else:
        kind = kind or "nitrogen"
        full = make_leaf(kind=kind)
        source = f"synthetic:{kind}"
        save_preview(full, out_dir / f"synthetic_{kind}.png")

    thumb = thumbnail_from_image(full, (40, 40))
    save_preview(thumb, out_dir / "thumbnail_40x40.png")

    t0 = time.perf_counter()
    result = detect_nutrient_deficiency(thumb)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    pump_action = "PUMP_ON" if result.dose_ms > 0 else "PUMP_SKIP"

    payload = {
        "source": source,
        "deficiency": DEF_NAMES[result.deficiency],
        "severity_pct": result.severity_pct,
        "dose_ms": result.dose_ms,
        "pump": pump_action,
        "metrics": {
            "green_ratio": round(result.green_ratio, 3),
            "yellow_index": round(result.yellow_index, 3),
            "purple_index": round(result.purple_index, 3),
            "brown_index": round(result.brown_index, 3),
        },
        "detect_ms": round(elapsed_ms, 2),
    }

    print("=== Solar ESP32 Fertigation Simulator ===")
    print(json.dumps(payload, indent=2))

    if result.dose_ms > 0:
        print(f"\n[SIM] Driving pump relay for {result.dose_ms} ms "
              f"(nutrient mix: {DEF_NAMES[result.deficiency]} blend)")
        # Non-blocking style progress for demo
        steps = max(1, result.dose_ms // 500)
        for i in range(steps):
            time.sleep(min(0.05, result.dose_ms / 10000))
            print(f"[SIM] pumping... {(i + 1) * 100 // steps}%", end="\r")
        print("\n[SIM] pump OFF — dose complete")
    else:
        print("\n[SIM] plant looks OK / below threshold — pump stays OFF")

    (out_dir / "last_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Fertigation system simulator")
    parser.add_argument(
        "--kind",
        choices=["healthy", "nitrogen", "phosphorus", "potassium", "iron"],
        default="nitrogen",
        help="Synthetic leaf condition (ignored if --image is set)",
    )
    parser.add_argument("--image", type=Path, help="Path to a real leaf photo")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all synthetic deficiency scenarios",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "output",
        help="Output folder for thumbnails/results",
    )
    args = parser.parse_args()

    if args.all:
        for kind in ["healthy", "nitrogen", "phosphorus", "potassium", "iron"]:
            print("\n" + "=" * 48)
            run_once(kind, None, args.out / kind)
        return

    run_once(args.kind, args.image, args.out)


if __name__ == "__main__":
    main()
