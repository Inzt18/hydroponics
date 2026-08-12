/*
 * ESP32-CAM Plant Health Monitor
 * -------------------------------
 * Captures a photo periodically, reads a soil moisture sensor,
 * and sends both to a backend server over WiFi.
 *
 * Board: AI-Thinker ESP32-CAM (adjust pin map below if using a different board)
 *
 * Wiring notes:
 *  - Soil moisture sensor analog output -> GPIO 33 (a safe ADC-capable pin on AI-Thinker boards)
 *  - Camera pins are fixed per board (see camera_pins section below)
 *
 * Libraries needed (Arduino IDE Library Manager):
 *  - "ArduinoJson" by Benoit Blanchon
 *  (esp_camera / WiFi / HTTPClient are included with the ESP32 board package)
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ============ USER CONFIG ============
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Base URL of your backend, e.g.:
//   Local testing:  "http://192.168.1.5:3000"
//   ngrok tunnel:    "https://xxxx-xx-xx.ngrok-free.app"
//   Hosted server:   "https://your-app.onrender.com"
const char* SERVER_BASE_URL = "http://192.168.1.5:3000";

// A unique name/ID for this plant/device (useful if you run several)
const char* DEVICE_ID = "plant-01";

// How often to capture + upload (milliseconds)
const unsigned long CAPTURE_INTERVAL_MS = 5UL * 60UL * 1000UL; // every 5 minutes

// Soil moisture sensor analog pin
#define SOIL_MOISTURE_PIN 33
// ======================================

// ---- AI-Thinker ESP32-CAM pin map ----
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
// ---------------------------------------

unsigned long lastCaptureTime = 0;

void setup() {
  Serial.begin(115200);
  Serial.println();

  setupCamera();
  connectWiFi();

  // Take + send the first reading immediately on boot
  captureAndSend();
  lastCaptureTime = millis();
}

void loop() {
  // Reconnect WiFi if it drops
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected, reconnecting...");
    connectWiFi();
  }

  if (millis() - lastCaptureTime >= CAPTURE_INTERVAL_MS) {
    captureAndSend();
    lastCaptureTime = millis();
  }

  delay(1000);
}

void setupCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_SVGA; // 800x600 - good balance for uploads
    config.jpeg_quality = 12;           // lower number = higher quality
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 15;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }
  Serial.println("Camera initialized");
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("WiFi connected. IP address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println();
    Serial.println("WiFi connection failed, will retry in loop()");
  }
}

int readSoilMoisturePercent() {
  // Raw ADC reading (0-4095 on ESP32's 12-bit ADC)
  int raw = analogRead(SOIL_MOISTURE_PIN);

  // Typical capacitive soil sensors: wetter soil = lower value.
  // Calibrate these two constants for YOUR specific sensor:
  //   dryValue = raw reading in completely dry air/soil
  //   wetValue = raw reading fully submerged in water
  const int dryValue = 3000;
  const int wetValue = 1200;

  int percent = map(raw, dryValue, wetValue, 0, 100);
  percent = constrain(percent, 0, 100);
  return percent;
}

void captureAndSend() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    return;
  }

  int moisture = readSoilMoisturePercent();

  // Send image first
  bool imageOk = sendImage(fb);

  esp_camera_fb_return(fb);

  // Then send sensor readings
  bool dataOk = sendSensorData(moisture);

  Serial.printf("Upload result -> image: %s, sensors: %s\n",
                imageOk ? "OK" : "FAILED",
                dataOk ? "OK" : "FAILED");
}

bool sendImage(camera_fb_t* fb) {
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  String url = String(SERVER_BASE_URL) + "/upload/image?device=" + DEVICE_ID;
  http.begin(url);
  http.addHeader("Content-Type", "image/jpeg");

  int code = http.POST(fb->buf, fb->len);
  Serial.printf("Image upload HTTP code: %d\n", code);
  http.end();

  return code == 200;
}

bool sendSensorData(int moisturePercent) {
  if (WiFi.status() != WL_CONNECTED) return false;

  HTTPClient http;
  String url = String(SERVER_BASE_URL) + "/upload/data";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> doc;
  doc["device"] = DEVICE_ID;
  doc["soil_moisture_percent"] = moisturePercent;
  // Add more sensors here as needed, e.g.:
  // doc["temperature_c"] = readTemperature();
  // doc["light_level"] = readLightSensor();

  String payload;
  serializeJson(doc, payload);

  int code = http.POST(payload);
  Serial.printf("Sensor data upload HTTP code: %d\n", code);
  http.end();

  return code == 200;
}
