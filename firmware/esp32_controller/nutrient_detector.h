#pragma once

#include <stdint.h>
#include "protocol.h"

struct DetectionResult {
  DeficiencyType deficiency;
  uint8_t severity_pct;  // 0–100
  uint16_t dose_ms;
  float green_ratio;
  float yellow_index;
  float purple_index;
  float brown_index;
};

// Analyze RGB888 thumbnail (width*height*3 bytes).
DetectionResult detectNutrientDeficiency(const uint8_t* rgb,
                                         uint16_t width,
                                         uint16_t height,
                                         uint16_t dose_ms_base,
                                         uint16_t dose_ms_max,
                                         uint8_t severity_min);
