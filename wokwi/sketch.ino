/*
 * Wokwi VISUAL demo — Solar ESP32 Smart Fertigation (controller side)
 *
 * What you see:
 *  - Buttons act like "ESP32-CAM sent this leaf image"
 *  - OLED shows deficiency + dose time
 *  - Relay + green LED = water/nutrient pump ON
 *
 * How to run on Wokwi:
 *  1. Open https://wokwi.com
 *  2. New project → ESP32
 *  3. Replace diagram.json and sketch.ino with these files
 *  4. Press the green Play button
 *  5. Click N / P / K / Healthy buttons
 *
 * Libraries (Library Manager in Wokwi):
 *  - Adafruit SSD1306
 *  - Adafruit GFX
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <math.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

static const int PIN_PUMP = 26;
static const int PIN_BTN_N = 32;
static const int PIN_BTN_P = 33;
static const int PIN_BTN_K = 25;
static const int PIN_BTN_OK = 27;

static const uint16_t DOSE_MS_BASE = 2000;
static const uint16_t DOSE_MS_MAX = 6000;  // shorter for Wokwi demo
static const uint8_t DOSE_SEVERITY_MIN = 35;

enum DeficiencyType : uint8_t {
  DEF_NONE = 0,
  DEF_NITROGEN = 1,
  DEF_PHOSPHORUS = 2,
  DEF_POTASSIUM = 3,
  DEF_IRON = 4,
  DEF_UNKNOWN = 255
};

struct DetectionResult {
  DeficiencyType deficiency;
  uint8_t severity_pct;
  uint16_t dose_ms;
};

static bool pumpOn = false;
static uint32_t pumpOffAt = 0;
static DetectionResult lastDet = {DEF_NONE, 0, 0};
static const char* lastSource = "boot";

static const char* defName(uint8_t d) {
  switch (d) {
    case DEF_NONE: return "HEALTHY";
    case DEF_NITROGEN: return "NITROGEN";
    case DEF_PHOSPHORUS: return "PHOSPHORUS";
    case DEF_POTASSIUM: return "POTASSIUM";
    case DEF_IRON: return "IRON";
    default: return "UNKNOWN";
  }
}

// Tiny synthetic 8x8 RGB patches (stand-in for CAM thumbnail color stats)
static void fillPatch(uint8_t* rgb, uint8_t r, uint8_t g, uint8_t b) {
  for (int i = 0; i < 64; i++) {
    rgb[i * 3 + 0] = r;
    rgb[i * 3 + 1] = g;
    rgb[i * 3 + 2] = b;
  }
}

static DetectionResult analyzePatch(const uint8_t* rgb) {
  DetectionResult out = {DEF_NONE, 0, 0};
  double sr = 0, sg = 0, sb = 0;
  for (int i = 0; i < 64; i++) {
    sr += rgb[i * 3 + 0];
    sg += rgb[i * 3 + 1];
    sb += rgb[i * 3 + 2];
  }
  float ar = sr / 64.0f, ag = sg / 64.0f, ab = sb / 64.0f;

  // Same spirit as the full firmware heuristic, simplified for demo patches
  float yellow = (ar > 140 && ag > 140 && ab < 100) ? 1.0f : 0.0f;
  float purple = (ab > ag && ab > 120) ? 1.0f : 0.0f;
  float brown = (ar > 130 && ag < 120 && ab < 90) ? 1.0f : 0.0f;
  float green = (ag > ar && ag > ab && ag > 100) ? 1.0f : 0.0f;

  DeficiencyType def = DEF_NONE;
  float severity = 0.2f;
  if (yellow > 0.5f) { def = DEF_NITROGEN; severity = 0.95f; }
  else if (purple > 0.5f) { def = DEF_PHOSPHORUS; severity = 0.92f; }
  else if (brown > 0.5f) { def = DEF_POTASSIUM; severity = 0.90f; }
  else if (green > 0.5f) { def = DEF_NONE; severity = 0.15f; }
  else { def = DEF_UNKNOWN; severity = 0.0f; }

  out.deficiency = def;
  out.severity_pct = (uint8_t)(severity * 100);
  if (def != DEF_NONE && def != DEF_UNKNOWN && out.severity_pct >= DOSE_SEVERITY_MIN) {
    out.dose_ms = DOSE_MS_BASE + (uint16_t)(severity * (DOSE_MS_MAX - DOSE_MS_BASE));
  }
  return out;
}

static void drawUI() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("FERTIGATION CTL");
  display.println("----------------");
  display.print("Src: ");
  display.println(lastSource);
  display.print("Def: ");
  display.println(defName(lastDet.deficiency));
  display.print("Sev: ");
  display.print(lastDet.severity_pct);
  display.println("%");
  display.print("Dose:");
  display.print(lastDet.dose_ms);
  display.println("ms");
  display.print("Pump:");
  display.println(pumpOn ? "ON >>>" : "OFF");
  display.display();
}

static void startPump(uint16_t ms) {
  if (ms == 0) {
    digitalWrite(PIN_PUMP, LOW);
    pumpOn = false;
    return;
  }
  digitalWrite(PIN_PUMP, HIGH);
  pumpOn = true;
  pumpOffAt = millis() + ms;
  Serial.printf("[WOKWI] PUMP ON for %u ms\n", ms);
}

static void handleScenario(const char* name, uint8_t r, uint8_t g, uint8_t b) {
  uint8_t patch[64 * 3];
  fillPatch(patch, r, g, b);
  lastSource = name;
  lastDet = analyzePatch(patch);

  Serial.println("==============================");
  Serial.printf("[CAM->CTL] image scenario: %s\n", name);
  Serial.printf("[DETECT] %s severity=%u%% dose=%ums\n",
                defName(lastDet.deficiency), lastDet.severity_pct, lastDet.dose_ms);

  startPump(lastDet.dose_ms);
  drawUI();
}

static bool pressed(int pin) {
  // INPUT_PULLUP buttons: active LOW
  static uint32_t last[4] = {0, 0, 0, 0};
  int idx = (pin == PIN_BTN_N) ? 0 : (pin == PIN_BTN_P) ? 1 : (pin == PIN_BTN_K) ? 2 : 3;
  if (digitalRead(pin) == LOW) {
    if (millis() - last[idx] > 350) {
      last[idx] = millis();
      return true;
    }
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_PUMP, OUTPUT);
  digitalWrite(PIN_PUMP, LOW);

  pinMode(PIN_BTN_N, INPUT_PULLUP);
  pinMode(PIN_BTN_P, INPUT_PULLUP);
  pinMode(PIN_BTN_K, INPUT_PULLUP);
  pinMode(PIN_BTN_OK, INPUT_PULLUP);

  Wire.begin(21, 22);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("SSD1306 fail");
  }

  lastSource = "ready";
  lastDet = {DEF_NONE, 0, 0};
  drawUI();

  Serial.println("Wokwi Fertigation visual demo ready");
  Serial.println("Click buttons: N / P / K / Healthy");
}

void loop() {
  if (pressed(PIN_BTN_N)) handleScenario("N-yellow", 190, 185, 55);
  if (pressed(PIN_BTN_P)) handleScenario("P-purple", 110, 70, 140);
  if (pressed(PIN_BTN_K)) handleScenario("K-brown", 150, 95, 45);
  if (pressed(PIN_BTN_OK)) handleScenario("Healthy", 46, 140, 58);

  if (pumpOn && (int32_t)(millis() - pumpOffAt) >= 0) {
    digitalWrite(PIN_PUMP, LOW);
    pumpOn = false;
    Serial.println("[WOKWI] PUMP OFF");
    drawUI();
  }
}
