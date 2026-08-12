#include "nutrient_detector.h"
#include <math.h>

static inline float clampf(float v, float lo, float hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

DetectionResult detectNutrientDeficiency(const uint8_t* rgb,
                                         uint16_t width,
                                         uint16_t height,
                                         uint16_t dose_ms_base,
                                         uint16_t dose_ms_max,
                                         uint8_t severity_min) {
  DetectionResult out = {};
  out.deficiency = DEF_NONE;
  out.severity_pct = 0;
  out.dose_ms = 0;

  const uint32_t n = (uint32_t)width * (uint32_t)height;
  if (n == 0 || !rgb) return out;

  double sum_r = 0, sum_g = 0, sum_b = 0;
  uint32_t yellowish = 0, purplish = 0, brownish = 0, greenish = 0;
  uint32_t veg_pixels = 0;

  for (uint32_t i = 0; i < n; i++) {
    uint8_t r = rgb[i * 3 + 0];
    uint8_t g = rgb[i * 3 + 1];
    uint8_t b = rgb[i * 3 + 2];

    // Skip near-black / near-white background
    int maxc = r > g ? (r > b ? r : b) : (g > b ? g : b);
    int minc = r < g ? (r < b ? r : b) : (g < b ? g : b);
    if (maxc < 30 || minc > 230) continue;

    veg_pixels++;
    sum_r += r;
    sum_g += g;
    sum_b += b;

    // Rough leaf-health buckets (heuristic, not lab diagnostics)
    if (g > r && g > b && (g - ((r + b) / 2)) > 18) {
      greenish++;
    }
    // Yellow / chlorosis (N or Fe)
    if (r > 90 && g > 90 && b < 90 && (r + g) > (2 * b + 40)) {
      yellowish++;
    }
    // Purple / dark (P stress cue)
    if (b > g && b > 70 && r > 60 && g < 110) {
      purplish++;
    }
    // Brown / edge burn (K stress cue)
    if (r > 100 && g > 60 && g < 140 && b < 80 && r > g && (r - b) > 40) {
      brownish++;
    }
  }

  if (veg_pixels < 20) {
    out.deficiency = DEF_UNKNOWN;
    out.severity_pct = 0;
    return out;
  }

  float inv = 1.0f / (float)veg_pixels;
  float avg_r = (float)(sum_r * inv);
  float avg_g = (float)(sum_g * inv);
  float avg_b = (float)(sum_b * inv);

  out.green_ratio = (float)greenish * inv;
  out.yellow_index = (float)yellowish * inv;
  out.purple_index = (float)purplish * inv;
  out.brown_index = (float)brownish * inv;

  // Score candidates
  float score_n = out.yellow_index * 1.2f + clampf((avg_r + avg_g) / 2.0f - avg_b, 0, 80) / 100.0f;
  // Iron chlorosis: yellow lamina with meaningful residual green (veins)
  float score_fe = out.yellow_index * 0.8f + out.green_ratio * 1.1f;
  float score_p = out.purple_index * 1.4f + clampf(avg_b - avg_g, 0, 60) / 80.0f;
  float score_k = out.brown_index * 1.5f + clampf(avg_r - avg_g, 0, 60) / 80.0f;
  float score_ok = out.green_ratio;

  float best = score_ok;
  DeficiencyType def = DEF_NONE;

  if (score_n > best && score_n > 0.22f) { best = score_n; def = DEF_NITROGEN; }
  // Prefer iron when yellowing coexists with retained green vein fraction
  if (out.yellow_index > 0.18f && out.green_ratio > 0.10f) {
    float vein_ratio = out.green_ratio / (out.yellow_index + 1e-3f);
    if (vein_ratio > 0.40f && score_fe > 0.20f) {
      best = score_fe;
      def = DEF_IRON;
    }
  }
  if (score_p > best && score_p > 0.18f) { best = score_p; def = DEF_PHOSPHORUS; }
  if (score_k > best && score_k > 0.18f) { best = score_k; def = DEF_POTASSIUM; }

  out.deficiency = def;
  if (def == DEF_NONE) {
    out.severity_pct = (uint8_t)clampf((1.0f - score_ok) * 40.0f, 0, 40);
    out.dose_ms = 0;
    return out;
  }

  float severity = clampf(best, 0.0f, 1.0f);
  // Amplify mid-range for clearer dosing decisions
  severity = clampf(severity * 1.15f, 0.0f, 1.0f);
  out.severity_pct = (uint8_t)(severity * 100.0f);

  if (out.severity_pct >= severity_min) {
    float scale = (float)out.severity_pct / 100.0f;
    uint16_t dose = (uint16_t)(dose_ms_base + scale * (dose_ms_max - dose_ms_base));
    if (dose > dose_ms_max) dose = dose_ms_max;
    out.dose_ms = dose;
  } else {
    out.dose_ms = 0;
  }

  return out;
}
