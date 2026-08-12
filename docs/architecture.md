# System architecture

## Nodes

### Vision node (ESP32-CAM)
- Wakes on timer (or deep-sleep cycle)
- Captures QVGA RGB565 frame
- Downsamples to **40×40 RGB888** thumbnail (4800 bytes)
- Sends `META` + `CHUNK` packets over **ESP-NOW**
- Sleeps again to conserve solar energy

### Control node (ESP32)
- Stays awake as the always-on actuator brain (or light-sleep later)
- Reassembles thumbnail
- Runs leaf-color **nutrient deficiency heuristic**
- If severity ≥ threshold and cooldown elapsed → GPIO drives pump relay
- Optionally replies with `RESULT` packet

## Why ESP-NOW + thumbnail?
- No Wi‑Fi router / cloud required (good for remote solar plots)
- Low power vs streaming full JPEG over HTTP
- Fits ESP32 RAM without PSRAM on the controller
- Chunk size stays under ESP-NOW payload limits

## Detection model (v1 heuristic + optional Plant.id)

| Cue | Likely class | Pump blend suggestion |
|-----|--------------|------------------------|
| Yellow / pale leaf | Nitrogen (or Iron) | N-forward fertilizer mix |
| Purple / dark cast | Phosphorus | P-forward mix |
| Brown / scorched edge | Potassium | K-forward mix |
| Strong green dominance | Healthy | No dose |

This is a **prototype classifier** for learning IoT control loops.

### Optional cloud ML (integrated)
Use Plant.id health assessment via laptop bridge:

```text
photo → plantid/bridge.py → Plant.id API → POST ESP32 /dose → pump
```

See `docs/PLANTID_INTEGRATION.md`.

## Fertigation actuation

```
severity_pct → dose_ms = DOSE_MS_BASE + scale*(DOSE_MS_MAX - DOSE_MS_BASE)
relay HIGH for dose_ms → pump moves premixed nutrient solution into reservoir / drip line
```

Cooldown (`PUMP_COOLDOWN_MS`) prevents over-dosing.

## Power domain

```
Solar panel → MPPT/PWM charge controller → battery → 5V buck → ESP32-CAM + ESP32 + relay coil
Pump motor → separate 12V (or matched) rail switched by relay contacts
```

Never power the pump from the ESP32 3.3/5 V pin.
