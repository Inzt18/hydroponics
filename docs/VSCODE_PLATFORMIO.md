# Upload from VS Code (PlatformIO)

## 1) Install once
1. Install [VS Code](https://code.visualstudio.com/)
2. Extensions → install **PlatformIO IDE**
3. Restart VS Code if asked

## 2) Flash ESP32 DevKit (controller / pump)
1. Plug DevKit USB into PC
2. **File → Open Folder** →  
   `C:\xampp\htdocs\solar-esp32-smart-fertigation\firmware\esp32_controller`
3. Wait for PlatformIO to load
4. Bottom toolbar:
   - ✔ **Build**
   - → **Upload**
   - 🔌 **Serial Monitor** (115200)
5. Copy the printed **IP address** and MAC from Serial

## 3) Flash ESP32-CAM
1. Wire USB-TTL to CAM (5V, GND, TX↔RX, RX↔TX)
2. Jump **GPIO0 → GND** (flash mode)
3. **File → Open Folder** →  
   `C:\xampp\htdocs\solar-esp32-smart-fertigation\firmware\esp32_cam`
4. PlatformIO → **Upload**
5. Remove GPIO0 jumper, press RESET
6. Open Serial Monitor — should show Wi‑Fi + JPEG upload logs

## 4) Run Plant.id server (VS Code terminal)
```powershell
cd C:\xampp\htdocs\solar-esp32-smart-fertigation
.\.venv\Scripts\activate
python -m plantid.server
```

## Wi‑Fi / API already set
- Wi‑Fi is in both `config.h` files
- Plant.id key is in project `.env`
- CAM posts to `http://192.168.1.13:8080/ingest`

After controller connects, update `.env`:
```env
ESP32_CONTROLLER_URL=http://THE_IP_FROM_SERIAL
```
Then restart `python -m plantid.server`.

## If Upload fails
- Select correct COM port: PlatformIO → devices
- CAM: confirm GPIO0 grounded during upload; try swap TX/RX
- Close Serial Monitor before uploading
- Install USB-UART drivers (CP210x / CH340 / FTDI)
