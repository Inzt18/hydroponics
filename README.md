# Solar ESP32 Smart Automatic Fertigation System

Open-source prototype for a **solar-powered** fertigation loop:

1. **ESP32-CAM** captures a leaf/plant image  
2. Sends a compact thumbnail over **ESP-NOW** (no Wi‑Fi router required)  
3. **ESP32 controller** detects likely **nutrient deficiency** from leaf color  
4. Drives a **water + nutrient-mix pump** for a calculated dose  

No physical hardware? Use the included **Python simulator** to run the same control loop on a laptop.

---

## Architecture

```
┌─────────────┐   sunlight    ┌──────────────────────┐
│ Solar panel │──────────────►│ Charge controller +  │
└─────────────┘               │ battery → 5V buck    │
                              └──────────┬───────────┘
                                         │ 5V
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
            ┌──────────────┐      ┌─────────────┐      ┌────────────┐
            │  ESP32-CAM   │ESP-NOW│ ESP32 MCU  │ GPIO │ Pump relay │
            │  capture     │──────►│ detect +   │─────►│ + nutrient │
            │  thumbnail   │       │ dose logic │      │ mix tank   │
            └──────────────┘      └─────────────┘      └────────────┘
```

| Role | Board | Job |
|------|-------|-----|
| Vision node | ESP32-CAM | Capture JPEG, build 40×40 RGB thumbnail, send via ESP-NOW |
| Control node | ESP32 DevKit | Receive image, classify deficiency, run pump timer |
| Power | 6–12 V panel + Li-ion/LiFePO4 | Daytime harvest, battery for night/cloud |

Detection on the MCU is **lightweight leaf-color analysis** (practical on ESP32 without PSRAM). It is a teaching/prototype heuristic — not lab-grade tissue analysis. Swap in Edge Impulse / TFLite later if you need a trained model.

---

## Repository layout

```
firmware/
  shared/protocol.h          # ESP-NOW packet format (both boards)
  esp32_cam/                 # Camera node sketch
  esp32_controller/          # Detector + pump sketch
docs/
  architecture.md
  wiring.md
  solar-power.md
simulator/                   # Run without hardware
  simulate.py
hardware/bom.md
```

---

## Quick start (no hardware)

```bash
cd simulator
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
python simulate.py
```

### Want a visual simulation?

**Easiest on-screen UI (local):**
```powershell
python visual_app.py
```

**ESP32-style visual (Wokwi in browser):** see [`wokwi/README.md`](wokwi/README.md)  
Buttons act as the camera leaf result; OLED + green LED show detect → pump.
---

## Firmware (Arduino IDE / PlatformIO)

### 1. Pair MAC addresses

1. Flash `esp32_controller` once and open Serial Monitor @ 115200.  
2. Copy the printed **STA MAC**.  
3. Paste it into `firmware/esp32_cam/config.h` as `CONTROLLER_MAC`.  
4. Copy the CAM MAC from the CAM serial log into `firmware/esp32_controller/config.h` as `CAM_PEER_MAC` (optional filter).

### 2. Libraries

- **ESP32 board package** (Espressif)  
- **esp32-camera** (bundled with ESP32 Arduino core for CAM boards)

### 3. Flash

- CAM board → `firmware/esp32_cam/esp32_cam.ino`  
- DevKit → `firmware/esp32_controller/esp32_controller.ino`

### 4. Expected serial flow

```
[CAM] capture ok → thumbnail 4800 B → ESP-NOW send
[CTL] image complete → deficiency=N severity=0.72 → pump ON 4500 ms → pump OFF
```

---

## Safety notes

- Use a **relay + separate pump supply** — never power a pump from ESP32 GPIO.  
- Start with short dose times (`DOSE_MS_BASE` in config).  
- Keep nutrient concentrate **diluted**; follow fertilizer label rates.  
- Outdoor installs need IP65 boxes and drip loops on cable glands.

---

## Docs

- [**Build instructions (start here)**](docs/BUILD_INSTRUCTIONS.md)
- [Architecture](docs/architecture.md)  
- [Wiring](docs/wiring.md)  
- [Solar power](docs/solar-power.md)
- [Prototype wireframe](docs/prototype-wireframe.html)
- [Bill of materials](hardware/bom.md)

## License

MIT — use freely for learning and prototypes.
