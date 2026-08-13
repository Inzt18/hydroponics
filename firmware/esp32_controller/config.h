#pragma once

#include <stdint.h>

// Optional: only accept frames from this CAM MAC (all 0xFF = accept any).
static const uint8_t CAM_PEER_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// Pump relay pin (active HIGH through transistor/relay module).
static const int PUMP_RELAY_PIN = 26;

// Status LED (onboard often GPIO 2).
static const int STATUS_LED_PIN = 2;

// Base dose when deficiency is detected; scaled by severity.
static const uint16_t DOSE_MS_BASE = 3000;
static const uint16_t DOSE_MS_MAX = 12000;

// Minimum seconds between pump runs (protects pump + plants).
static const uint32_t PUMP_COOLDOWN_MS = 10UL * 60UL * 1000UL;

// Severity threshold (0–100) before dosing.
static const uint8_t DOSE_SEVERITY_MIN = 35;

// Serial baud.
static const uint32_t SERIAL_BAUD = 115200;

// ---- Plant.id / Wi-Fi HTTP bridge ----
// Set your Wi-Fi so laptop can POST http://<esp-ip>/dose
static const bool ENABLE_WIFI_API = true;
static const char* WIFI_SSID = "PLDTHOMEFIBRB5ABD";
static const char* WIFI_PASSWORD = "PLDTWIFI98EMC";

// Keep local ESP-NOW color detector (true) or rely only on Plant.id HTTP (false).
static const bool ENABLE_LOCAL_DETECT = true;
