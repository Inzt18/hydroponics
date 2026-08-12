# Wiring guide

## ESP32-CAM (AI Thinker)

| Function | Notes |
|----------|--------|
| 5V / GND | From solar buck (stable 5V) |
| GPIO0 → GND | Only while flashing |
| Onboard camera | FPC already connected |
| Antenna | Keep clear of metal enclosure walls |

No pump wiring on the CAM — vision only.

## ESP32 controller

| Signal | GPIO (default) | Connects to |
|--------|----------------|-------------|
| Pump relay IN | **26** | Relay module IN |
| Status LED | **2** | Onboard / external LED |
| 5V / GND | — | Shared logic supply with CAM (common GND) |

### Relay + pump (critical)

```
ESP32 GPIO26 ──► Relay IN
ESP32 GND    ──► Relay GND
5V           ──► Relay VCC  (for 5V relay modules)

Battery/PSU + ──► Pump +
Pump −       ──► Relay COM
Relay NO     ──► PSU − (or as module docs specify)

Nutrient mix tank ── pump ──► hydroponic reservoir / drip line
```

Use an opto-isolated relay module. Match relay contact rating to pump current.

## ESP-NOW pairing

1. Power controller, open Serial @ 115200  
2. Copy printed STA MAC into `firmware/esp32_cam/config.h` → `CONTROLLER_MAC`  
3. Optionally lock CAM MAC in `firmware/esp32_controller/config.h` → `CAM_PEER_MAC`  
4. Both boards must share the same Wi‑Fi channel context (ESP-NOW STA mode handles this when both are nearby)

## Nutrient mix plumbing (simple prototype)

1. Reservoir A: water  
2. Reservoir B: concentrated nutrient (follow label dilution)  
3. Prefer a **premixed dilute tank** for v1 (one pump)  
4. Advanced: second dosing pump for concentrate + main water pump

## Enclosure tips

- IP65 box, silica gel pack  
- Camera window: clear acrylic, anti-fog if humid  
- Cable glands; drip loop on every cable  
- Mount CAM 20–40 cm above canopy, diffuse daylight preferred
