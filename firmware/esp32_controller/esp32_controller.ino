/*
 * Solar ESP32 Smart Fertigation — Controller Node
 *
 * Modes:
 *  1) ESP-NOW from ESP32-CAM + local color detect (optional)
 *  2) Wi-Fi HTTP API for Plant.id bridge:
 *       GET  /health
 *       POST /dose   {"dose_ms":5000,"issue":"...","severity_pct":80}
 */

#include <WiFi.h>
#include <WebServer.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <string.h>
#include <stdlib.h>

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
static WebServer g_server(80);

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
  if (!ENABLE_LOCAL_DETECT) {
    Serial.println("[CTL] local detect disabled — ignoring ESP-NOW frame");
    resetReceive();
    return;
  }

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

static uint16_t parseDoseMsFromBody(const String& body) {
  // Minimal JSON parse for {"dose_ms":1234,...}
  int idx = body.indexOf("dose_ms");
  if (idx < 0) return 0;
  int colon = body.indexOf(':', idx);
  if (colon < 0) return 0;
  long v = body.substring(colon + 1).toInt();
  if (v < 0) v = 0;
  if (v > DOSE_MS_MAX) v = DOSE_MS_MAX;
  return (uint16_t)v;
}

static void handleHealth() {
  String ip = WiFi.localIP().toString();
  String json = "{";
  json += "\"ok\":true,";
  json += "\"service\":\"fertigation-controller\",";
  json += "\"ip\":\"" + ip + "\",";
  json += "\"pump_running\":";
  json += g_pump.isRunning() ? "true" : "false";
  json += ",\"wifi_api\":true";
  json += ",\"local_detect\":";
  json += ENABLE_LOCAL_DETECT ? "true" : "false";
  json += "}";
  g_server.send(200, "application/json", json);
}

static void handleDose() {
  if (g_server.method() != HTTP_POST) {
    g_server.send(405, "application/json", "{\"ok\":false,\"error\":\"POST only\"}");
    return;
  }

  String body = g_server.arg("plain");
  if (body.length() == 0) body = g_server.arg(0);
  uint16_t dose_ms = parseDoseMsFromBody(body);

  Serial.println("[API] POST /dose");
  Serial.println(body);
  Serial.printf("[API] parsed dose_ms=%u\n", dose_ms);

  if (dose_ms == 0) {
    g_server.send(200, "application/json",
                  "{\"ok\":true,\"pumped\":false,\"reason\":\"dose_ms=0\"}");
    return;
  }

  if (!g_pump.canRun()) {
    g_server.send(200, "application/json",
                  "{\"ok\":true,\"pumped\":false,\"reason\":\"cooldown\"}");
    return;
  }

  g_pump.runDose(dose_ms);
  digitalWrite(STATUS_LED_PIN, HIGH);
  delay(60);
  digitalWrite(STATUS_LED_PIN, LOW);

  String json = "{\"ok\":true,\"pumped\":true,\"dose_ms\":";
  json += String(dose_ms);
  json += "}";
  g_server.send(200, "application/json", json);
}

static void handleNotFound() {
  g_server.send(404, "application/json", "{\"ok\":false,\"error\":\"not found\"}");
}

static bool connectWifi() {
  if (!ENABLE_WIFI_API) return false;
  if (String(WIFI_SSID) == "YOUR_WIFI_SSID") {
    Serial.println("[WIFI] Set WIFI_SSID/WIFI_PASSWORD in config.h");
    return false;
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WIFI] connecting to %s", WIFI_SSID);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] connect failed — HTTP API disabled");
    return false;
  }
  Serial.print("[WIFI] connected IP=");
  Serial.println(WiFi.localIP());
  return true;
}

static void startHttpApi() {
  g_server.on("/health", HTTP_GET, handleHealth);
  g_server.on("/dose", HTTP_POST, handleDose);
  g_server.onNotFound(handleNotFound);
  g_server.begin();
  Serial.println("[API] HTTP server on :80");
  Serial.println("[API] GET  /health");
  Serial.println("[API] POST /dose  {\"dose_ms\":5000}");
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(400);
  Serial.println("\n[CTL] Solar fertigation controller");

  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, LOW);
  g_pump.begin(PUMP_RELAY_PIN, PUMP_COOLDOWN_MS);

  bool wifi_ok = connectWifi();
  if (!wifi_ok) {
    // ESP-NOW still needs STA mode
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(false, false);
    delay(100);
  }
  printMac();

  if (wifi_ok) {
    startHttpApi();
  }

  if (esp_now_init() != ESP_OK) {
    Serial.println("[CTL] esp_now_init failed");
    while (true) delay(1000);
  }
  esp_now_register_recv_cb(onDataRecv);

  esp_now_peer_info_t peer = {};
  memset(peer.peer_addr, 0xFF, 6);
  peer.channel = 0;
  peer.encrypt = false;
  // Keep ESP-NOW on same channel as Wi-Fi soft association when possible
  if (wifi_ok) {
    peer.channel = WiFi.channel();
  }
  esp_now_add_peer(&peer);

  Serial.println("[CTL] ready (ESP-NOW + optional Plant.id HTTP)");
}

void loop() {
  g_pump.update();
  if (ENABLE_WIFI_API && WiFi.status() == WL_CONNECTED) {
    g_server.handleClient();
  }

  if (g_receiving && (millis() - g_recv_started_ms > 5000)) {
    Serial.println("[CTL] receive timeout — reset");
    resetReceive();
  }
}
