# Plant.id API integration (camera + pump)

## Full flow (now includes camera)
```text
ESP32-CAM photo (JPEG)
        ↓  Wi-Fi HTTP POST /ingest
Laptop: python -m plantid.server
        ↓
Plant.id health assessment (cloud ML)
        ↓
Dose decision
        ↓  HTTP POST /dose
ESP32 controller → relay → water pump
```

## Dashboard (see detected values)
```powershell
python -m plantid.server
```
Open in browser: [http://127.0.0.1:8080/](http://127.0.0.1:8080/)

You can:
- See latest Plant.id healthy/issue/severity/dose/pump values
- View recent history
- Manually upload a leaf photo to test even before ESP32-CAM power is stable
```powershell
cd C:\xampp\htdocs\solar-esp32-smart-fertigation
copy .env.example .env
```
Edit `.env`:
- `PLANT_ID_API_KEY=...`
- `ESP32_CONTROLLER_URL=http://ESP32_IP`

### 2) Install deps
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r plantid\requirements.txt
```

### 3) Flash ESP32 controller (pump + /dose API)
In `firmware/esp32_controller/config.h` set Wi-Fi SSID/password, flash, note IP.

### 4) Start Plant.id bridge server on laptop
```powershell
python -m plantid.server
```
Find your laptop LAN IP (e.g. `192.168.1.20`).

### 5) Flash ESP32-CAM (upload mode)
In `firmware/esp32_cam/config.h`:
```cpp
ENABLE_PLANTID_UPLOAD = true
WIFI_SSID / WIFI_PASSWORD = your Wi-Fi
PLANTID_INGEST_URL = "http://192.168.1.20:8080/ingest"
```
Flash CAM, aim at plant.

### 6) Watch it work
- CAM Serial: `JPEG ... → ingest HTTP 200`
- Server console: decision + whether pumped
- Controller Serial: `[API] POST /dose` + pump ON

## Manual photo test (no CAM)
```powershell
python -m plantid.bridge --image leaf.jpg --trigger-pump
```

## Modes
| Mode | Config |
|------|--------|
| Camera → Plant.id → pump | `ENABLE_PLANTID_UPLOAD=true` on CAM |
| Camera → local color detect → pump | `ENABLE_PLANTID_UPLOAD=false`, `ENABLE_ESPNOW_THUMB=true` |

## Notes
- Laptop, CAM, and ESP32 controller must share the same Wi-Fi
- Keep `python -m plantid.server` running
- Plant.id uses API credits
- Captures save under `plantid/output/cam_uploads/`
