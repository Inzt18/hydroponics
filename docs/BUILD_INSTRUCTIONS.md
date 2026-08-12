# Build Instructions — Make It Work (Beginner)

Follow this **in order**. Do not skip ahead to the camera until Step 3 works.

**Project folder:** `C:\xampp\htdocs\solar-esp32-smart-fertigation`

---

## Before you start (safety)

- Keep water **away** from breadboard, ESP32, and laptop.
- Never power the pump from an ESP32 GPIO pin.
- Use the **relay** to switch pump power.
- If the pump has a wall plug already, you may not need a separate adapter.
- Work on a dry table with good light.

---

## Step 0 — Unpack and check parts

Put these on the table:

### Must have for first working system
- [ ] ESP32-CAM
- [ ] USB-TTL programmer (FTDI / CP2102 style)
- [ ] ESP32 DevKit
- [ ] 5 V relay module
- [ ] Water pump
- [ ] Jumper wires
- [ ] Breadboard (helpful)
- [ ] 5 V power bank / USB power for boards
- [ ] Pump power (wall plug on pump, or matching adapter)
- [ ] Tubing
- [ ] Water container (Tupperware/bucket)

### Optional now (ignore for first success)
- Solar panel / battery
- Soil moisture sensor
- Temp/humidity sensor
- Air pumps
- Extra LEDs

If **ESP32 DevKit** or **USB-TTL** is missing, stop and get those first.

---

## Step 1 — Install software on your laptop

1. Install **Arduino IDE**: https://www.arduino.cc/en/software
2. Open Arduino IDE → **File → Preferences**
3. In *Additional boards manager URLs* paste:

```text
https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
```

4. **Tools → Board → Boards Manager** → search **esp32** → install **esp32 by Espressif Systems**
5. Connect a data-capable USB cable (not charge-only)

---

## Step 2 — Flash the controller (ESP32 DevKit) first

### 2.1 Open the code
1. Arduino IDE → **File → Open**
2. Open:

```text
firmware\esp32_controller\esp32_controller.ino
```

### 2.2 Board settings
- **Board:** ESP32 Dev Module
- **Upload Speed:** 115200
- **Port:** the COM port of your DevKit

### 2.3 Upload
Click **Upload**. Wait until it says Done.

### 2.4 Get the MAC address
1. **Tools → Serial Monitor**
2. Set baud to **115200**
3. Press the DevKit **RESET** button
4. You should see something like:

```text
[CTL] STA MAC AA:BB:CC:DD:EE:FF
[CTL] Paste this MAC into esp32_cam/config.h as CONTROLLER_MAC
[CTL] waiting for camera frames...
```

5. **Write down that MAC** (example only: `24:6F:28:AA:BB:CC`)

Leave the controller powered for later.

---

## Step 3 — Wire relay + pump (no camera yet)

### 3.1 Logic side (low voltage)

| From | To |
|------|----|
| ESP32 **GPIO26** | Relay **IN** |
| ESP32 **GND** | Relay **GND** |
| ESP32 **5V** (or power bank 5V) | Relay **VCC** |

### 3.2 Pump side (switched power)

**If pump has bare wires / DC jack:**

| From | To |
|------|----|
| Pump PSU **+** | Relay **COM** |
| Relay **NO** | Pump **+** |
| Pump PSU **−** | Pump **−** |

**If pump already has a wall plug:**  
Use the relay on the low-voltage DC side only if accessible.  
If it is a sealed AC plug-in pump, ask before cutting mains wires — safer to use a **DC pump** for this prototype.

### 3.3 Quick relay test (optional)
For a first confidence check, you can temporarily upload a tiny blink-on-26 sketch, or wait until the camera path works.  
You should hear/feel the relay click when GPIO26 goes HIGH, and the pump should run only while relay is on.

### 3.4 Water path
1. Put clean water in the container (plain water first, nutrients later)
2. Put pump in water (or connect inlet tubing into water)
3. Outlet tubing to plant tray / empty catch cup
4. Keep electronics higher and dry

---

## Step 4 — Put controller MAC into CAM config

1. Open:

```text
firmware\esp32_cam\config.h
```

2. Change this line:

```cpp
static const uint8_t CONTROLLER_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
```

3. Replace with your real MAC.  
   Example: MAC `24:6F:28:AA:BB:CC` becomes:

```cpp
static const uint8_t CONTROLLER_MAC[6] = {0x24, 0x6F, 0x28, 0xAA, 0xBB, 0xCC};
```

4. For first testing, also set:

```cpp
static const uint32_t CAPTURE_INTERVAL_MS = 30000UL;  // 30 seconds
static const bool USE_DEEP_SLEEP = false;
```

5. Save the file.

---

## Step 5 — Flash the ESP32-CAM

AI Thinker CAM needs USB-TTL and a boot jumper.

### 5.1 Wire USB-TTL → ESP32-CAM

| USB-TTL | ESP32-CAM |
|---------|-----------|
| 5V | 5V |
| GND | GND |
| TX | U0R (RX) |
| RX | U0T (TX) |

### 5.2 Enter flash mode
Connect **GPIO0 → GND** (jumper) before upload.

### 5.3 Arduino settings
- **Board:** AI Thinker ESP32-CAM
- **Port:** COM port of USB-TTL
- Open:

```text
firmware\esp32_cam\esp32_cam.ino
```

### 5.4 Upload
Click **Upload**.

If it fails:
- Hold **RESET** on CAM, click Upload, release RESET when compiling finishes / connecting
- Recheck TX/RX are not swapped
- Confirm GPIO0 is grounded during upload

### 5.5 Run mode
1. Remove **GPIO0 ↔ GND** jumper
2. Press **RESET**
3. Open Serial Monitor @ **115200**
4. You want lines like:

```text
[CAM] Solar fertigation camera node
[CAM] STA MAC ...
[CAM] capturing...
[CAM] frame ... sent
```

---

## Step 6 — First full test (camera → detect → pump)

1. Power **ESP32 DevKit** (USB)
2. Power **ESP32-CAM** (USB-TTL 5V or power bank)
3. Keep both boards close together (ESP-NOW range)
4. Aim CAM at a **green leaf** (healthy test)
5. Watch **controller Serial** @ 115200

Expected healthy-ish result:
- receives frame
- deficiency `NONE` or low severity
- pump stays OFF

6. Aim CAM at a **yellow / pale leaf** (or yellow paper for a crude demo)
7. Expected:
- deficiency like `NITROGEN`
- `[PUMP] ON for .... ms`
- relay clicks, pump runs briefly, then OFF

If pump runs on yellow and stays off on healthy green, **your prototype works**.

---

## Step 7 — Use it with hydroponics water

1. Mix nutrient solution in the tank **exactly per fertilizer label** (diluted)
2. Route tubing into your plant tray/reservoir
3. Mount CAM **20–40 cm** above leaves, steady, with decent daylight
4. Set capture interval back to normal when stable, e.g.:

```cpp
static const uint32_t CAPTURE_INTERVAL_MS = 5UL * 60UL * 1000UL;  // 5 minutes
static const bool USE_DEEP_SLEEP = true;
```

5. Re-upload CAM firmware after that change

### Your daily use
- Keep tank filled
- Keep power on
- System checks leaves and doses automatically when it thinks nutrients are low
- You refill water/nutrients and check for clogs

---

## Step 8 — Tune if needed

In `firmware\esp32_controller\config.h`:

| Setting | Meaning |
|---------|---------|
| `DOSE_MS_BASE` | Minimum pump time |
| `DOSE_MS_MAX` | Maximum pump time |
| `DOSE_SEVERITY_MIN` | How sensitive before dosing |
| `PUMP_COOLDOWN_MS` | Wait time between doses |

Start with **short doses** so you don’t flood plants.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| CAM upload fails | GPIO0→GND while flashing; swap TX/RX; use 5V not 3V3 on CAM power |
| No MAC on controller | Baud 115200; press RESET; correct COM port |
| CAM sends but controller silent | MAC wrong in `config.h`; boards too far; both powered |
| Relay clicks, pump dead | Pump power missing / wrong voltage / NO-COM wiring |
| Always doses | Lighting bad / camera blurry / threshold too low |
| Never doses | Aim at leaf, improve light, lower `DOSE_SEVERITY_MIN` carefully |
| Brownouts / reset | Use stronger 5V supply; don’t power pump from board |

---

## Success checklist

- [ ] Controller flashes and prints MAC
- [ ] CAM flashes and captures
- [ ] Controller receives frames
- [ ] Healthy leaf → little/no pump
- [ ] Stressed/yellow look → pump doses
- [ ] Water moves through tubing safely
- [ ] Electronics stay dry

When all boxes are checked, the physical prototype is working.

---

## What not to do yet
- Don’t add solar until USB prototype is stable
- Don’t use the Wokwi button sketch on the real boards
- Don’t skip MAC pairing

---

## Need help live?
Tell me which step you are on and paste your Serial Monitor output.
We will debug from there.
