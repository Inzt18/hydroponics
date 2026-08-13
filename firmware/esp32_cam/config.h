#pragma once

#include <stdint.h>

// ---- Mode ----
// true  = Wi-Fi JPEG upload to Plant.id bridge (recommended with API)
// false = ESP-NOW thumbnail to local ESP32 color detector
static const bool ENABLE_PLANTID_UPLOAD = true;

// Keep ESP-NOW local path as well (only used if ENABLE_PLANTID_UPLOAD=false,
// or set true if you want both — default false to save power/time).
static const bool ENABLE_ESPNOW_THUMB = false;

// Paste the controller STA MAC (only needed for ESP-NOW mode).
static const uint8_t CONTROLLER_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// Capture interval.
static const uint32_t CAPTURE_INTERVAL_MS = 60UL * 1000UL;  // 60s for API testing

// Deep sleep between captures (set false while debugging).
static const bool USE_DEEP_SLEEP = false;

// Wi-Fi for Plant.id bridge upload (same network as laptop).
static const char* WIFI_SSID = "PLDTHOMEFIBRB5ABD";
static const char* WIFI_PASSWORD = "PLDTWIFI98EMC";

// Website / Render bridge: POST JPEG here (saved to Supabase, analyzed later).
// Example local: "http://192.168.1.3:8080/upload"
static const char* PLANTID_INGEST_URL = "https://hydroponics-gmmj.onrender.com/upload";

// Camera model: AI Thinker ESP32-CAM
#define CAMERA_MODEL_AI_THINKER
