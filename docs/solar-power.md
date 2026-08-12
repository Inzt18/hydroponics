# Solar power design (prototype)

## Goal
Run ESP32-CAM (burst capture) + ESP32 controller + relay coil from sunlight with overnight battery reserve. Pump motor uses the battery/PSU through the relay, not the ESP32 regulator.

## Suggested starter kit

| Part | Spec | Why |
|------|------|-----|
| Solar panel | 10 W, 6 V or 12 V | Enough headroom for ESP + occasional pump |
| Charge controller | PWM or small MPPT matched to battery | Protects battery |
| Battery | 1–2× 18650 (7.4 V pack) or 12 V LiFePO4 6–12 Ah | Night / cloudy buffer |
| Buck converter | Adjustable → **5.0 V** | Clean logic rail for both ESP32 boards |
| Fuse | Inline on battery + | Safety |

## Power budget (order-of-magnitude)

| Load | Current | Duty |
|------|---------|------|
| ESP32 controller idle | ~40–80 mA @ 5V | Continuous |
| ESP32-CAM capture burst | ~180–250 mA | Few seconds / interval |
| ESP32-CAM deep sleep | ~1–10 mA (module dependent) | Most of the time |
| Relay coil | ~20–70 mA | Only while dosing |
| DC pump | 0.5–2 A @ 12V | Only while dosing |

With **5-minute** capture intervals and short doses, a **10 W panel + 6–12 Ah** pack is a practical backyard starting point. Measure your real current with a USB meter before trusting outdoor autonomy.

## Firmware power features already included
- CAM `USE_DEEP_SLEEP = true` between captures  
- Thumbnail + ESP-NOW (no always-on Wi‑Fi AP)  
- Pump cooldown to avoid frequent motor starts  

## Commissioning checklist
1. Confirm buck output is 5.0 V under CAM capture load  
2. Common GND across CAM, controller, relay logic  
3. Pump supply fused and polarity correct  
4. Shade test: battery alone should cover overnight + morning dose  
5. Hot noon test: charge controller not overheating
