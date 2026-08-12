#!/usr/bin/env python3
"""
Simple visual fertigation simulator (no hardware / no Wokwi needed).

Shows:
  - synthetic leaf image
  - deficiency result
  - pump ON/OFF indicator
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path

import numpy as np
from PIL import Image, ImageTk

from deficiency_detector import DEF_NAMES, detect_nutrient_deficiency, thumbnail_from_image
from plant_sim import make_leaf


class FertigationVisualApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Solar ESP32 Fertigation — Visual Simulator")
        self.geometry("720x520")
        self.configure(bg="#1b2a1f")

        self.kind = tk.StringVar(value="nitrogen")
        self.status = tk.StringVar(value="Click a leaf type, then Run")
        self.pump_state = tk.StringVar(value="PUMP OFF")
        self._photo = None
        self._pump_job = None

        title = tk.Label(
            self,
            text="Smart Fertigation Visual Sim",
            font=("Segoe UI", 18, "bold"),
            fg="#e8f5e9",
            bg="#1b2a1f",
        )
        title.pack(pady=(14, 6))

        controls = tk.Frame(self, bg="#1b2a1f")
        controls.pack(pady=6)

        for label, value in [
            ("Healthy", "healthy"),
            ("Nitrogen", "nitrogen"),
            ("Phosphorus", "phosphorus"),
            ("Potassium", "potassium"),
            ("Iron", "iron"),
        ]:
            ttk.Radiobutton(controls, text=label, value=value, variable=self.kind).pack(
                side=tk.LEFT, padx=6
            )

        ttk.Button(controls, text="Run detection", command=self.run_once).pack(
            side=tk.LEFT, padx=12
        )

        body = tk.Frame(self, bg="#1b2a1f")
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        self.canvas = tk.Label(body, bg="#0f1a13")
        self.canvas.pack(side=tk.LEFT, padx=(0, 16))

        right = tk.Frame(body, bg="#243528", padx=16, pady=16)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.result_lbl = tk.Label(
            right,
            text="Deficiency: —\nSeverity: —\nDose: —",
            justify=tk.LEFT,
            font=("Consolas", 12),
            fg="#dcedc8",
            bg="#243528",
        )
        self.result_lbl.pack(anchor="w")

        self.pump_lbl = tk.Label(
            right,
            textvariable=self.pump_state,
            font=("Segoe UI", 20, "bold"),
            fg="#9e9e9e",
            bg="#243528",
            pady=18,
        )
        self.pump_lbl.pack(anchor="w", pady=12)

        self.meter = ttk.Progressbar(right, length=260, mode="determinate", maximum=100)
        self.meter.pack(anchor="w", pady=4)
        tk.Label(
            right, text="Pump progress", fg="#a5d6a7", bg="#243528", font=("Segoe UI", 9)
        ).pack(anchor="w")

        tk.Label(
            self,
            textvariable=self.status,
            fg="#c8e6c9",
            bg="#1b2a1f",
            font=("Segoe UI", 10),
        ).pack(pady=(0, 12))

        self.run_once()

    def run_once(self) -> None:
        if self._pump_job is not None:
            self.after_cancel(self._pump_job)
            self._pump_job = None

        kind = self.kind.get()
        full = make_leaf(kind)
        thumb = thumbnail_from_image(full, (40, 40))
        result = detect_nutrient_deficiency(thumb)

        preview = Image.fromarray(full).resize((280, 280), Image.NEAREST)
        self._photo = ImageTk.PhotoImage(preview)
        self.canvas.configure(image=self._photo)

        self.result_lbl.configure(
            text=(
                f"Deficiency: {DEF_NAMES[result.deficiency]}\n"
                f"Severity: {result.severity_pct}%\n"
                f"Dose: {result.dose_ms} ms\n"
                f"green={result.green_ratio:.2f}  yellow={result.yellow_index:.2f}"
            )
        )

        out = Path(__file__).resolve().parent / "output"
        out.mkdir(exist_ok=True)
        preview.save(out / "visual_last.png")

        if result.dose_ms > 0:
            self.status.set(
                f"Detected {DEF_NAMES[result.deficiency]} — pumping nutrient mix..."
            )
            self._animate_pump(result.dose_ms)
        else:
            self.pump_state.set("PUMP OFF")
            self.pump_lbl.configure(fg="#9e9e9e")
            self.meter["value"] = 0
            self.status.set("Plant looks OK — pump stays OFF")

    def _animate_pump(self, dose_ms: int) -> None:
        self.pump_state.set("PUMP ON")
        self.pump_lbl.configure(fg="#69f0ae")
        self.meter["value"] = 0
        steps = 40
        interval = max(20, dose_ms // steps)

        # Compress long doses for UI feel (max ~2.5s animation)
        interval = min(interval, 60)

        def tick(i: int = 0) -> None:
            pct = int((i + 1) * 100 / steps)
            self.meter["value"] = pct
            if i + 1 >= steps:
                self.pump_state.set("PUMP OFF")
                self.pump_lbl.configure(fg="#9e9e9e")
                self.status.set("Dose complete — pump OFF")
                self._pump_job = None
                return
            self._pump_job = self.after(interval, lambda: tick(i + 1))

        tick(0)


if __name__ == "__main__":
    app = FertigationVisualApp()
    app.mainloop()
