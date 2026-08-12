"""
Leaf color heuristic for nutrient deficiency (mirrors ESP32 C++ logic).
Educational prototype — not a substitute for lab tissue tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Tuple

import numpy as np


class DeficiencyType(IntEnum):
    NONE = 0
    NITROGEN = 1
    PHOSPHORUS = 2
    POTASSIUM = 3
    IRON = 4
    UNKNOWN = 255


DEF_NAMES = {
    DeficiencyType.NONE: "NONE",
    DeficiencyType.NITROGEN: "NITROGEN",
    DeficiencyType.PHOSPHORUS: "PHOSPHORUS",
    DeficiencyType.POTASSIUM: "POTASSIUM",
    DeficiencyType.IRON: "IRON",
    DeficiencyType.UNKNOWN: "UNKNOWN",
}


@dataclass
class DetectionResult:
    deficiency: DeficiencyType
    severity_pct: int
    dose_ms: int
    green_ratio: float
    yellow_index: float
    purple_index: float
    brown_index: float


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def detect_nutrient_deficiency(
    rgb: np.ndarray,
    dose_ms_base: int = 3000,
    dose_ms_max: int = 12000,
    severity_min: int = 35,
) -> DetectionResult:
    """
    rgb: HxWx3 uint8 array (RGB)
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be HxWx3")

    pixels = rgb.reshape(-1, 3).astype(np.int16)
    maxc = pixels.max(axis=1)
    minc = pixels.min(axis=1)
    mask = (maxc >= 30) & (minc <= 230)
    veg = pixels[mask]

    if len(veg) < 20:
        return DetectionResult(
            DeficiencyType.UNKNOWN, 0, 0, 0.0, 0.0, 0.0, 0.0
        )

    r, g, b = veg[:, 0], veg[:, 1], veg[:, 2]
    greenish = (g > r) & (g > b) & ((g - ((r + b) // 2)) > 18)
    yellowish = (r > 90) & (g > 90) & (b < 90) & ((r + g) > (2 * b + 40))
    purplish = (b > g) & (b > 70) & (r > 60) & (g < 110)
    brownish = (r > 100) & (g > 60) & (g < 140) & (b < 80) & (r > g) & ((r - b) > 40)

    n = float(len(veg))
    green_ratio = float(np.count_nonzero(greenish) / n)
    yellow_index = float(np.count_nonzero(yellowish) / n)
    purple_index = float(np.count_nonzero(purplish) / n)
    brown_index = float(np.count_nonzero(brownish) / n)

    avg_r, avg_g, avg_b = float(r.mean()), float(g.mean()), float(b.mean())

    score_n = yellow_index * 1.2 + _clamp((avg_r + avg_g) / 2.0 - avg_b, 0, 80) / 100.0
    # Iron chlorosis: yellow lamina with meaningful residual green (veins)
    score_fe = yellow_index * 0.8 + green_ratio * 1.1
    score_p = purple_index * 1.4 + _clamp(avg_b - avg_g, 0, 60) / 80.0
    score_k = brown_index * 1.5 + _clamp(avg_r - avg_g, 0, 60) / 80.0
    score_ok = green_ratio

    best = score_ok
    deficiency = DeficiencyType.NONE

    if score_n > best and score_n > 0.22:
        best, deficiency = score_n, DeficiencyType.NITROGEN
    if yellow_index > 0.18 and green_ratio > 0.10:
        vein_ratio = green_ratio / (yellow_index + 1e-3)
        if vein_ratio > 0.40 and score_fe > 0.20:
            best, deficiency = score_fe, DeficiencyType.IRON
    if score_p > best and score_p > 0.18:
        best, deficiency = score_p, DeficiencyType.PHOSPHORUS
    if score_k > best and score_k > 0.18:
        best, deficiency = score_k, DeficiencyType.POTASSIUM

    if deficiency == DeficiencyType.NONE:
        severity = int(_clamp((1.0 - score_ok) * 40.0, 0, 40))
        return DetectionResult(
            deficiency, severity, 0, green_ratio, yellow_index, purple_index, brown_index
        )

    severity_f = _clamp(best * 1.15, 0.0, 1.0)
    severity = int(severity_f * 100)
    dose = 0
    if severity >= severity_min:
        scale = severity / 100.0
        dose = int(dose_ms_base + scale * (dose_ms_max - dose_ms_base))
        dose = min(dose, dose_ms_max)

    return DetectionResult(
        deficiency, severity, dose, green_ratio, yellow_index, purple_index, brown_index
    )


def thumbnail_from_image(rgb: np.ndarray, size: Tuple[int, int] = (40, 40)) -> np.ndarray:
    """Nearest-neighbor resize to ESP32 thumbnail size."""
    h, w = rgb.shape[:2]
    tw, th = size
    ys = (np.arange(th) * h / th).astype(int)
    xs = (np.arange(tw) * w / tw).astype(int)
    return rgb[ys][:, xs]
