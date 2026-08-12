#pragma once

#include <stdint.h>

// Shared ESP-NOW protocol between ESP32-CAM and ESP32 controller.
// Thumbnail: 40x40 RGB888 = 4800 bytes → chunked into ESP-NOW frames.

static const uint8_t FERT_MAGIC0 = 0xFE;
static const uint8_t FERT_MAGIC1 = 0x32;

static const uint16_t THUMB_W = 40;
static const uint16_t THUMB_H = 40;
static const uint16_t THUMB_BYTES = THUMB_W * THUMB_H * 3;  // 4800

static const uint8_t PKT_TYPE_META = 0x01;
static const uint8_t PKT_TYPE_CHUNK = 0x02;
static const uint8_t PKT_TYPE_ACK = 0x03;
static const uint8_t PKT_TYPE_RESULT = 0x04;

// Keep payload under ESP-NOW practical limit (~240 usable after headers).
static const uint16_t CHUNK_DATA_MAX = 200;

enum DeficiencyType : uint8_t {
  DEF_NONE = 0,
  DEF_NITROGEN = 1,      // yellowing / pale green
  DEF_PHOSPHORUS = 2,    // dark / purplish cast
  DEF_POTASSIUM = 3,     // brown / scorched edges
  DEF_IRON = 4,          // chlorosis (yellow leaf, retained green cast)
  DEF_UNKNOWN = 255
};

#pragma pack(push, 1)
struct FertMetaPacket {
  uint8_t magic0;
  uint8_t magic1;
  uint8_t type;          // PKT_TYPE_META
  uint16_t frame_id;
  uint16_t width;
  uint16_t height;
  uint16_t total_bytes;
  uint16_t total_chunks;
  uint32_t capture_ms;
};

struct FertChunkPacket {
  uint8_t magic0;
  uint8_t magic1;
  uint8_t type;          // PKT_TYPE_CHUNK
  uint16_t frame_id;
  uint16_t chunk_index;
  uint16_t data_len;
  uint8_t data[CHUNK_DATA_MAX];
};

struct FertAckPacket {
  uint8_t magic0;
  uint8_t magic1;
  uint8_t type;          // PKT_TYPE_ACK
  uint16_t frame_id;
  uint8_t ok;            // 1 = received full image
};

struct FertResultPacket {
  uint8_t magic0;
  uint8_t magic1;
  uint8_t type;          // PKT_TYPE_RESULT
  uint16_t frame_id;
  uint8_t deficiency;    // DeficiencyType
  uint8_t severity_pct;  // 0–100
  uint16_t dose_ms;
};
#pragma pack(pop)

inline const char* deficiencyName(uint8_t d) {
  switch (d) {
    case DEF_NONE: return "NONE";
    case DEF_NITROGEN: return "NITROGEN";
    case DEF_PHOSPHORUS: return "PHOSPHORUS";
    case DEF_POTASSIUM: return "POTASSIUM";
    case DEF_IRON: return "IRON";
    default: return "UNKNOWN";
  }
}
