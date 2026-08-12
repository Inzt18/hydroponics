#pragma once

#include <stdint.h>

// Paste the controller STA MAC printed on Serial after boot.
// Example: {0x24, 0x6F, 0x28, 0xAA, 0xBB, 0xCC}
static const uint8_t CONTROLLER_MAC[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// Capture interval (also used after deep-sleep wake).
static const uint32_t CAPTURE_INTERVAL_MS = 5UL * 60UL * 1000UL;  // 5 minutes

// Use deep sleep between captures to save solar budget.
static const bool USE_DEEP_SLEEP = true;

// Camera model: AI Thinker ESP32-CAM
#define CAMERA_MODEL_AI_THINKER
