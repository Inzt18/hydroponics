# ESP32-CAM Plant Health Monitor

A minimal end-to-end setup: **ESP32-CAM (firmware)** → **Node.js backend** → **live website dashboard**.

## What's included

```
plant-monitor/
├── esp32-firmware/
│   └── esp32_cam_plant_monitor.ino   # Arduino sketch for the ESP32-CAM
├── public/
│   ├── index.html                    # Dashboard page
│   ├── style.css
│   └── script.js                     # Polls the backend and updates the UI
├── server.js                         # Node/Express backend (receives image + sensor data)
├── package.json
└── README.md
```

## 1. Run the backend

Requires [Node.js](https://nodejs.org) installed.

```bash
cd plant-monitor
npm install
npm start
```

You should see:
```
Plant monitor server running at http://localhost:3000
```

Open `http://localhost:3000` in a browser — you'll see the dashboard (empty until the ESP32-CAM sends data).

## 2. Find your computer's local IP address

The ESP32-CAM needs to know where to send data. Find your machine's LAN IP:

- **Windows**: `ipconfig` → look for "IPv4 Address"
- **Mac/Linux**: `ifconfig` or `ip addr` → look for something like `192.168.x.x`

## 3. Configure and flash the ESP32-CAM

Open `esp32-firmware/esp32_cam_plant_monitor.ino` in the Arduino IDE and edit the top section:

```cpp
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_BASE_URL = "http://192.168.1.5:3000"; // your computer's IP + port
```

**Install required libraries** (Arduino IDE → Library Manager):
- `ArduinoJson` (by Benoit Blanchon)
- ESP32 board package (Boards Manager → search "esp32", install by Espressif)

**Board settings**: Select `AI Thinker ESP32-CAM` under Tools → Board (or the matching board if you're using a different ESP32-CAM variant).

**Upload**: ESP32-CAM boards need a USB-to-serial adapter (they have no onboard USB). Connect GPIO0 to GND before powering on to enter flashing mode, upload the sketch, then disconnect GPIO0 from GND and reset the board to run normally.

Once flashed, open the Serial Monitor (115200 baud) to confirm WiFi connects and uploads succeed.

## 4. Watch it work

Go back to `http://localhost:3000` — the dashboard auto-refreshes every 10 seconds and will show:
- The latest photo from the plant
- Current soil moisture %
- A trend chart of recent readings

## Testing over the real internet (not just local WiFi)

Once local testing works, you have two options:

**Quick test — ngrok tunnel:**
```bash
ngrok http 3000
```
Copy the `https://xxxx.ngrok-free.app` URL it gives you, and put that in `SERVER_BASE_URL` in the firmware instead of your local IP. Now the ESP32-CAM can reach your server from any WiFi network, not just your home LAN.

**Permanent — deploy the backend:**
Deploy the `plant-monitor` folder to a host like Render, Railway, or a VPS, then point `SERVER_BASE_URL` at your deployed domain (e.g. `https://your-app.onrender.com`). Note: on most free hosts, files written to disk (the `data/` folder) don't persist across restarts/redeploys — for a permanent deployment you'd eventually want to swap the JSON-file storage in `server.js` for a real database and cloud file storage (e.g. S3) for images.

## Adding more sensors

In the firmware, add readings to the JSON payload in `sendSensorData()`:
```cpp
doc["temperature_c"] = readTemperature();
doc["light_level"] = readLightSensor();
```
The backend already stores any extra fields you send — no backend changes needed. You'd just extend `public/script.js` to display them.

## Calibrating the soil moisture sensor

In the firmware's `readSoilMoisturePercent()`, adjust:
```cpp
const int dryValue = 3000; // raw ADC reading with sensor in dry air
const int wetValue = 1200; // raw ADC reading with sensor in water
```
Print `analogRead(SOIL_MOISTURE_PIN)` to Serial in both conditions to get your actual values — sensors vary between units.
