/*
 * Solar ESP32 Smart Fertigation — Controller Node
 * Board: ESP32 DevKit (or similar)
 *
 * Receives 40x40 RGB thumbnails over ESP-NOW from ESP32-CAM,
 * detects likely nutrient deficiency, and runs the fertigation pump.
 */

#include <WiFi.h>
#include <esp_now.h>
#include <string.h>

#include "config.h"
#include "nutrient_detector.h"
#include "pump_control.h"
#include "protocol.h"

static uint8_t g_image[THUMB_BYTES];
static bool g_chunk_got[(THUMB_BYTES + CHUNK_DATA_MAX - 1) / CHUNK_DATA_MAX];
static uint16_t g_expect_chunks = 0;
static uint16_t g_frame_id = 0;
static bool g_receiving = false;
static uint32_t g_recv_started_ms = 0;

static PumpControl g_pump;

static bool macAllowed(const uint8_t* mac) {
  bool wildcard = true;
  for (int i = 0; i < 6; i++) {
    if (CAM_PEER_MAC[i] != 0xFF) wildcard = false;
  }
  if (wildcard) return true;
  return memcmp(mac, CAM_PEER_MAC, 6) == 0;
}

static void resetReceive() {
  g_receiving = false;
  g_expect_chunks = 0;
  memset(g_chunk_got, 0, sizeof(g_chunk_got));
}

static bool imageComplete() {
  if (!g_receiving || g_expect_chunks == 0) return false;
  for (uint16_t i = 0; i < g_expect_chunks; i++) {
    if (!g_chunk_got[i]) return false;
  }
  return true;
}

static void sendResult(const uint8_t* dest_mac, uint16_t frame_id,
                       const DetectionResult& det) {
  FertResultPacket pkt = {};
  pkt.magic0 = FERT_MAGIC0;
  pkt.magic1 = FERT_MAGIC1;
  pkt.type = PKT_TYPE_RESULT;
  pkt.frame_id = frame_id;
  pkt.deficiency = (uint8_t)det.deficiency;
  pkt.severity_pct = det.severity_pct;
  pkt.dose_ms = det.dose_ms;
  esp_now_send(dest_mac, (uint8_t*)&pkt, sizeof(pkt));
}

static void processImage(const uint8_t* mac) {
  DetectionResult det = detectNutrientDeficiency(
      g_image, THUMB_W, THUMB_H, DOSE_MS_BASE, DOSE_MS_MAX, DOSE_SEVERITY_MIN);

  Serial.printf(
      "[CTL] frame %u → %s severity=%u%% green=%.2f yellow=%.2f purple=%.2f "
      "brown=%.2f dose=%u ms\n",
      g_frame_id, deficiencyName(det.deficiency), det.severity_pct,
      det.green_ratio, det.yellow_index, det.purple_index, det.brown_index,
      det.dose_ms);

  digitalWrite(STATUS_LED_PIN, HIGH);
  delay(80);
  digitalWrite(STATUS_LED_PIN, LOW);

  sendResult(mac, g_frame_id, det);

  if (det.dose_ms > 0) {
    g_pump.runDose(det.dose_ms);
  } else {
    Serial.println("[CTL] no dose (healthy or below threshold / cooldown)");
  }

  resetReceive();
}

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
void onDataRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  const uint8_t* mac = info->src_addr;
#else
void onDataRecv(const uint8_t* mac, const uint8_t* data, int len) {
#endif
  if (!macAllowed(mac) || len < 4) return;
  if (data[0] != FERT_MAGIC0 || data[1] != FERT_MAGIC1) return;

  uint8_t type = data[2];

  if (type == PKT_TYPE_META && len >= (int)sizeof(FertMetaPacket)) {
    const FertMetaPacket* meta = (const FertMetaPacket*)data;
    if (meta->total_bytes != THUMB_BYTES || meta->width != THUMB_W ||
        meta->height != THUMB_H) {
      Serial.println("[CTL] unsupported image size");
      return;
    }
    g_frame_id = meta->frame_id;
    g_expect_chunks = meta->total_chunks;
    g_receiving = true;
    g_recv_started_ms = millis();
    memset(g_chunk_got, 0, sizeof(g_chunk_got));
    memset(g_image, 0, sizeof(g_image));
    Serial.printf("[CTL] receiving frame %u (%u chunks)\n", g_frame_id,
                  g_expect_chunks);
    return;
  }

  if (type == PKT_TYPE_CHUNK && len >= (int)offsetof(FertChunkPacket, data)) {
    if (!g_receiving) return;
    const FertChunkPacket* chunk = (const FertChunkPacket*)data;
    if (chunk->frame_id != g_frame_id) return;
    if (chunk->chunk_index >= g_expect_chunks) return;
    if (chunk->data_len > CHUNK_DATA_MAX) return;

    uint16_t offset = chunk->chunk_index * CHUNK_DATA_MAX;
    if (offset + chunk->data_len > THUMB_BYTES) return;

    memcpy(g_image + offset, chunk->data, chunk->data_len);
    g_chunk_got[chunk->chunk_index] = true;

    if (imageComplete()) {
      processImage(mac);
    }
  }
}

static void printMac() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  Serial.printf("[CTL] STA MAC %02X:%02X:%02X:%02X:%02X:%02X\n",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  Serial.println("[CTL] Paste this MAC into esp32_cam/config.h as CONTROLLER_MAC");
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(400);
  Serial.println("\n[CTL] Solar fertigation controller");

  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);
  g_pump.begin(PUMP_RELAY_PIN, PUMP_COOLDOWN_MS);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
  printMac();

  if (esp_now_init() != ESP_OK) {
    Serial.println("[CTL] esp_now_init failed");
    while (true) delay(1000);
  }
  esp_now_register_recv_cb(onDataRecv);

  // Add a broadcast peer so RESULT packets can be sent back if needed.
  esp_now_peer_info_t peer = {};
  memset(peer.peer_addr, 0xFF, 6);
  peer.channel = 0;
  peer.encrypt = false;
  esp_now_add_peer(&peer);

  Serial.println("[CTL] waiting for camera frames...");
}

void loop() {
  g_pump.update();

  // Drop incomplete transfers after 5s
  if (g_receiving && (millis() - g_recv_started_ms > 5000)) {
    Serial.println("[CTL] receive timeout — reset");
    resetReceive();
  }
}
