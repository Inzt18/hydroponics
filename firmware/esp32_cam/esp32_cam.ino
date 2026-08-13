/*
 * Solar ESP32 Smart Fertigation — Camera Node
 * Board: AI Thinker ESP32-CAM
 *
 * Modes (config.h):
 *  - ENABLE_PLANTID_UPLOAD: capture JPEG → HTTP POST to Plant.id bridge
 *  - ENABLE_ESPNOW_THUMB:   40x40 RGB thumb → ESP-NOW local detector
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <esp_now.h>
#include <esp_wifi.h>

#include "config.h"
#include "protocol.h"

#if defined(CAMERA_MODEL_AI_THINKER)
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
#endif

static uint16_t g_frame_id = 1;
static uint8_t g_thumb[THUMB_BYTES];

static bool initCameraJpeg() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
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
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;  // 320x240 keeps upload small
  config.jpeg_quality = 12;
  config.fb_count = 2;
#if defined(CAMERA_GRAB_LATEST)
  config.grab_mode = CAMERA_GRAB_LATEST;
#endif

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] camera init failed: 0x%x\n", err);
    return false;
  }
  return true;
}

static bool connectWifi() {
  if (String(WIFI_SSID) == "YOUR_WIFI_SSID") {
    Serial.println("[WIFI] Set WIFI_SSID / WIFI_PASSWORD in config.h");
    return false;
  }
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  // Drop a leftover join so WiFi.begin() is not called while STA is connecting.
  WiFi.disconnect(true);
  delay(200);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WIFI] connecting to %s", WIFI_SSID);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 25000) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] failed");
    WiFi.disconnect(true);
    return false;
  }
  Serial.print("[WIFI] OK IP=");
  Serial.println(WiFi.localIP());
  return true;
}

static bool uploadJpegToPlantIdBridge() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAM] fb_get failed");
    return false;
  }
  if (fb->format != PIXFORMAT_JPEG) {
    Serial.println("[CAM] expected JPEG frame");
    esp_camera_fb_return(fb);
    return false;
  }

  Serial.printf("[CAM] JPEG %u bytes → %s\n", fb->len, PLANTID_INGEST_URL);

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[CAM] WiFi not connected");
    esp_camera_fb_return(fb);
    return false;
  }

  HTTPClient http;
  http.setTimeout(60000);
  bool ok = false;

  if (http.begin(PLANTID_INGEST_URL)) {
    http.addHeader("Content-Type", "image/jpeg");
    http.addHeader("X-Device", "esp32-cam");
    int code = http.POST(fb->buf, fb->len);
    String body = http.getString();
    Serial.printf("[CAM] upload HTTP %d\n", code);
    if (body.length() > 0) {
      Serial.println(body.substring(0, min((int)body.length(), 240)));
    }
    ok = (code >= 200 && code < 300);
    http.end();
  } else {
    Serial.println("[CAM] http.begin failed");
  }

  esp_camera_fb_return(fb);
  return ok;
}

static bool captureThumbnail(uint8_t* out_rgb, uint32_t* capture_ms) {
  sensor_t* s = esp_camera_sensor_get();
  if (!s) return false;

  s->set_pixformat(s, PIXFORMAT_RGB565);
  s->set_framesize(s, FRAMESIZE_QVGA);

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAM] fb_get failed");
    s->set_pixformat(s, PIXFORMAT_JPEG);
    return false;
  }

  *capture_ms = millis();
  const int src_w = fb->width;
  const int src_h = fb->height;
  const uint16_t* src = (const uint16_t*)fb->buf;

  for (int ty = 0; ty < THUMB_H; ty++) {
    for (int tx = 0; tx < THUMB_W; tx++) {
      int sx = (tx * src_w) / THUMB_W;
      int sy = (ty * src_h) / THUMB_H;
      uint16_t p = src[sy * src_w + sx];
      uint8_t r = ((p >> 11) & 0x1F) << 3;
      uint8_t g = ((p >> 5) & 0x3F) << 2;
      uint8_t b = (p & 0x1F) << 3;
      int idx = (ty * THUMB_W + tx) * 3;
      out_rgb[idx + 0] = r;
      out_rgb[idx + 1] = g;
      out_rgb[idx + 2] = b;
    }
  }

  esp_camera_fb_return(fb);
  s->set_pixformat(s, PIXFORMAT_JPEG);
  s->set_framesize(s, FRAMESIZE_QVGA);
  return true;
}

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
static void onDataSent(const wifi_tx_info_t* info, esp_now_send_status_t status) {
  (void)info;
#else
static void onDataSent(const uint8_t* mac, esp_now_send_status_t status) {
  (void)mac;
#endif
  if (status != ESP_NOW_SEND_SUCCESS) {
    Serial.println("[CAM] ESP-NOW send fail");
  }
}

static bool initEspNow() {
  if (WiFi.getMode() == WIFI_OFF) {
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);
  }
  if (esp_now_init() != ESP_OK) {
    Serial.println("[CAM] esp_now_init failed");
    return false;
  }
  esp_now_register_send_cb(onDataSent);

  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, CONTROLLER_MAC, 6);
  peer.channel = 0;
  peer.encrypt = false;
  esp_now_add_peer(&peer);
  return true;
}

static bool sendThumbnail(const uint8_t* rgb, uint32_t capture_ms) {
  const uint16_t total_chunks =
      (THUMB_BYTES + CHUNK_DATA_MAX - 1) / CHUNK_DATA_MAX;

  FertMetaPacket meta = {};
  meta.magic0 = FERT_MAGIC0;
  meta.magic1 = FERT_MAGIC1;
  meta.type = PKT_TYPE_META;
  meta.frame_id = g_frame_id;
  meta.width = THUMB_W;
  meta.height = THUMB_H;
  meta.total_bytes = THUMB_BYTES;
  meta.total_chunks = total_chunks;
  meta.capture_ms = capture_ms;

  if (esp_now_send(CONTROLLER_MAC, (uint8_t*)&meta, sizeof(meta)) != ESP_OK) {
    Serial.println("[CAM] meta send failed");
    return false;
  }
  delay(20);

  for (uint16_t i = 0; i < total_chunks; i++) {
    FertChunkPacket chunk = {};
    chunk.magic0 = FERT_MAGIC0;
    chunk.magic1 = FERT_MAGIC1;
    chunk.type = PKT_TYPE_CHUNK;
    chunk.frame_id = g_frame_id;
    chunk.chunk_index = i;

    uint16_t offset = i * CHUNK_DATA_MAX;
    uint16_t remain = THUMB_BYTES - offset;
    chunk.data_len = remain > CHUNK_DATA_MAX ? CHUNK_DATA_MAX : remain;
    memcpy(chunk.data, rgb + offset, chunk.data_len);

    size_t pkt_len = offsetof(FertChunkPacket, data) + chunk.data_len;
    if (esp_now_send(CONTROLLER_MAC, (uint8_t*)&chunk, pkt_len) != ESP_OK) {
      Serial.printf("[CAM] chunk %u send failed\n", i);
      return false;
    }
    delay(8);
  }

  Serial.printf("[CAM] ESP-NOW frame %u sent\n", g_frame_id);
  g_frame_id++;
  return true;
}

static void printMac() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  Serial.printf("[CAM] STA MAC %02X:%02X:%02X:%02X:%02X:%02X\n",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n[CAM] Solar fertigation camera node");

  if (!initCameraJpeg()) {
    while (true) delay(1000);
  }

  if (ENABLE_PLANTID_UPLOAD) {
    if (!connectWifi()) {
      Serial.println("[CAM] Plant.id upload mode needs WiFi");
    }
  } else if (ENABLE_ESPNOW_THUMB) {
    if (!initEspNow()) {
      while (true) delay(1000);
    }
  }

  printMac();
  Serial.printf("[CAM] plantid_upload=%d espnow=%d\n",
                ENABLE_PLANTID_UPLOAD ? 1 : 0,
                ENABLE_ESPNOW_THUMB ? 1 : 0);
}

void loop() {
  if (ENABLE_PLANTID_UPLOAD) {
    if (WiFi.status() != WL_CONNECTED) {
      connectWifi();
    }
    Serial.println("[CAM] capturing JPEG for Plant.id ...");
    if (!uploadJpegToPlantIdBridge()) {
      Serial.println("[CAM] Plant.id upload failed");
    }
  } else if (ENABLE_ESPNOW_THUMB) {
    uint32_t capture_ms = 0;
    Serial.println("[CAM] capturing thumbnail for ESP-NOW ...");
    if (captureThumbnail(g_thumb, &capture_ms)) {
      sendThumbnail(g_thumb, capture_ms);
    }
  } else {
    Serial.println("[CAM] no mode enabled in config.h");
    delay(5000);
    return;
  }

  if (USE_DEEP_SLEEP) {
    Serial.printf("[CAM] deep sleep %lu ms\n", CAPTURE_INTERVAL_MS);
    Serial.flush();
    esp_sleep_enable_timer_wakeup((uint64_t)CAPTURE_INTERVAL_MS * 1000ULL);
    esp_deep_sleep_start();
  }

  delay(CAPTURE_INTERVAL_MS);
}
