# Visual simulation options

Your terminal `simulate.py` run is correct — but it’s text-only.  
For something you can **see**, use one of these:

---

## Option A — Wokwi (recommended visual ESP32 demo)

Wokwi can show the **controller side** live: OLED text + relay + green pump LED.

> Full ESP32-CAM → ESP-NOW → second ESP32 is awkward in one Wokwi project, so this demo uses **buttons as the camera result** (N / P / K / Healthy leaf). Same detect → pump logic.

### Steps
1. Open [https://wokwi.com](https://wokwi.com) and sign in (free)
2. **New project** → choose **ESP32**
3. Open the `diagram.json` tab → replace everything with  
   `wokwi/diagram.json` from this repo
4. Open `sketch.ino` → replace everything with  
   `wokwi/sketch.ino`
5. **Add a new file** in Wokwi named `libraries.txt` and paste:

```text
Adafruit SSD1306
Adafruit GFX Library
```

   Or use **Library Manager** (book icon) → **+** → search/add both libraries above.
6. Press the green **Play** button
7. Click the buttons:
   - **N def** (yellow) → nitrogen → pump LED ON
   - **P def** (purple) → phosphorus → pump LED ON
   - **K def** (orange) → potassium → pump LED ON
   - **Healthy** (green) → no dose, pump stays OFF

### If you see `Adafruit_GFX.h: No such file or directory`
The libraries are missing. Do step 5, then click **Play** again (Wokwi will download them on build).

Watch:
- OLED lines: deficiency, severity, dose ms, pump state  
- Green LED / relay = nutrient pump running  
- Serial Monitor logs the same messages

---

## Option B — Local visual window (Python)

From `simulator/`:

```powershell
python visual_app.py
```

Shows a leaf image, detection result, and a pump indicator that turns on/off.

---

## Option C — Keep using text simulator

```powershell
python simulate.py --kind nitrogen
python simulate.py --all
```
