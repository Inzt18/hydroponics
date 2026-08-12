"""Synthetic leaf image generator for offline fertigation demos."""

from __future__ import annotations

import numpy as np


def make_leaf(kind: str = "healthy", size: int = 160, seed: int = 7) -> np.ndarray:
    """
    kind: healthy | nitrogen | phosphorus | potassium | iron
    Returns HxWx3 uint8 RGB image.
    """
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size, 3), dtype=np.uint8)

    # Soft background
    img[:, :] = (30, 28, 24)

    yy, xx = np.mgrid[0:size, 0:size]
    cx, cy = size // 2, size // 2
    # Ellipse leaf mask
    leaf = ((xx - cx) / (size * 0.32)) ** 2 + ((yy - cy) / (size * 0.42)) ** 2 <= 1.0

    if kind == "healthy":
        base = np.array([46, 140, 58], dtype=np.float32)
    elif kind == "nitrogen":
        base = np.array([190, 185, 55], dtype=np.float32)  # yellowing
    elif kind == "iron":
        # Chlorosis: yellow lamina, greener veins (classic Fe cue)
        base = np.array([210, 200, 85], dtype=np.float32)
    elif kind == "phosphorus":
        base = np.array([110, 70, 140], dtype=np.float32)  # purple cast
    elif kind == "potassium":
        base = np.array([150, 95, 45], dtype=np.float32)  # brown/scorch
    else:
        raise ValueError(f"unknown kind: {kind}")

    noise = rng.normal(0, 8, size=(size, size, 3))
    leaf_rgb = np.clip(base + noise, 0, 255).astype(np.uint8)
    img[leaf] = leaf_rgb[leaf]

    if kind == "iron":
        # Retain greener veins against yellow tissue (wider for classifier cue)
        mid_wide = np.abs(xx - cx) < 4
        img[leaf & mid_wide] = (40, 130, 55)
        vein2 = np.abs((yy - cy) - (xx - cx) * 0.3) < 3
        img[leaf & vein2] = (50, 125, 60)
        vein3 = np.abs((yy - cy) + (xx - cx) * 0.25) < 3
        img[leaf & vein3] = (45, 128, 58)
    else:
        mid = np.abs(xx - cx) < 2
        img[leaf & mid] = np.clip(
            img[leaf & mid].astype(np.int16) - 20, 0, 255
        ).astype(np.uint8)

    # Edge burn accent for potassium
    if kind == "potassium":
        edge = leaf & (
            ((xx - cx) / (size * 0.32)) ** 2 + ((yy - cy) / (size * 0.42)) ** 2 > 0.72
        )
        img[edge] = (160, 80, 35)

    return img
