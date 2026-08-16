/*
 * ESP32-CAM sample test — auto "Get Still" every 10 seconds
 *
 * Flash, open Serial Monitor (115200), copy the IP, then open it in a browser.
 * Each still is POSTed to the laptop (python -m plantid.server) and saved in
 * plantid/output/cam_uploads. The page also refreshes every 10 seconds.
 *
 * Board: AI-Thinker ESP32-CAM
 */

#include <Arduino.h>
#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>

// ===========================
// WiFi + laptop receiver
// ===========================
const char *ssid = "ISABELLA";
const char *password = "121311IA";

// Laptop running: python -m plantid.server
// Saves each JPEG to plantid/output/cam_uploads
const char *UPLOAD_URL = "http://192.168.1.3:8080/upload";

static const unsigned long STILL_INTERVAL_MS = 60000;

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

WebServer server(80);

static uint8_t *g_jpeg = nullptr;
static size_t g_jpeg_len = 0;
static size_t g_jpeg_cap = 0;
static unsigned long g_last_capture_ms = 0;
static uint32_t g_capture_count = 0;
static uint32_t g_upload_count = 0;
static bool g_last_upload_ok = false;

static const char INDEX_HTML[] PROGMEM = R"HTML(
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ESP32-CAM still test</title>
  <style>
    body { font-family: sans-serif; background:#111; color:#eee; text-align:center; margin:0; padding:16px; }
    img { max-width:100%; height:auto; border:1px solid #333; background:#000; }
    button { padding:10px 16px; margin:8px; font-size:16px; cursor:pointer; }
    .meta { color:#bbb; }
  </style>
</head>
<body>
  <h1>ESP32-CAM auto still</h1>
  <p>Captures a still every 10 seconds and uploads each JPEG to plantid/output/cam_uploads.</p>
  <p class="meta" id="meta">Waiting for first capture...</p>
  <p><button onclick="captureNow()">Get Still now</button></p>
  <img id="still" alt="Latest still">
  <script>
    const INTERVAL_MS = 10000;
    async function refresh() {
      try {
        const s = await (await fetch('/status')).json();
        document.getElementById('meta').textContent =
          'Captures: ' + s.count + '  |  uploaded: ' + s.uploaded +
          '  |  last upload: ' + (s.upload_ok ? 'OK' : 'FAILED') +
          '  |  ' + s.bytes + ' bytes  |  last ' + s.age_s + 's ago';
        if (s.bytes > 0) {
          document.getElementById('still').src = '/still?t=' + Date.now();
        }
      } catch (e) {
        document.getElementById('meta').textContent = 'Waiting for camera...';
      }
    }
    async function captureNow() {
      await fetch('/capture');
      await refresh();
    }
    refresh();
    setInterval(refresh, INTERVAL_MS);
  </script>
</body>
</html>
)HTML";

static bool saveJpeg(camera_fb_t *fb) {
  if (!fb || !fb->buf || fb->len == 0) {
    return false;
  }

  if (fb->len > g_jpeg_cap) {
    size_t next_cap = fb->len + 4096;
    uint8_t *next = (uint8_t *)ps_malloc(next_cap);
    if (!next) {
      next = (uint8_t *)malloc(next_cap);
    }
    if (!next) {
      Serial.println("JPEG buffer alloc failed");
      return false;
    }
    if (g_jpeg) {
      free(g_jpeg);
    }
    g_jpeg = next;
    g_jpeg_cap = next_cap;
  }

  memcpy(g_jpeg, fb->buf, fb->len);
  g_jpeg_len = fb->len;
  return true;
}

static bool uploadStill() {
  if (!g_jpeg || g_jpeg_len == 0) {
    return false;
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Upload skipped: WiFi down");
    g_last_upload_ok = false;
    return false;
  }

  WiFiClient client;
  HTTPClient http;
  http.setTimeout(8000);
  http.setReuse(false);
  bool ok = false;

  if (http.begin(client, UPLOAD_URL)) {
    http.addHeader("Content-Type", "image/jpeg");
    http.addHeader("X-Device", "esp32-cam-still-test");
    int code = http.POST(g_jpeg, g_jpeg_len);
    if (code < 0) {
      Serial.printf("Upload failed %d (%s)\n", code, http.errorToString(code).c_str());
    } else {
      Serial.printf("Upload HTTP %d → cam_uploads (%u bytes)\n", code, (unsigned)g_jpeg_len);
    }
    ok = (code >= 200 && code < 300);
    http.end();
  } else {
    Serial.println("Upload begin failed (is plantid.server running?)");
  }

  g_last_upload_ok = ok;
  if (ok) {
    g_upload_count++;
  }
  return ok;
}

static bool captureStill() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Get Still failed");
    return false;
  }

  bool ok = saveJpeg(fb);
  esp_camera_fb_return(fb);

  if (ok) {
    g_capture_count++;
    g_last_capture_ms = millis();
    Serial.printf("Get Still #%u  %u bytes\n", g_capture_count, (unsigned)g_jpeg_len);
    uploadStill();
  }
  return ok;
}

static void handleIndex() {
  server.sendHeader("Cache-Control", "no-store");
  server.send_P(200, "text/html", INDEX_HTML);
}

static void handleStatus() {
  unsigned long age_s = 0;
  if (g_capture_count > 0) {
    age_s = (millis() - g_last_capture_ms) / 1000UL;
  }
  String json = "{";
  json += "\"count\":" + String(g_capture_count);
  json += ",\"uploaded\":" + String(g_upload_count);
  json += ",\"upload_ok\":";
  json += g_last_upload_ok ? "true" : "false";
  json += ",\"bytes\":" + String((unsigned)g_jpeg_len);
  json += ",\"age_s\":" + String(age_s);
  json += "}";
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", json);
}

static void handleStill() {
  if (!g_jpeg || g_jpeg_len == 0) {
    server.send(503, "text/plain", "No still captured yet");
    return;
  }

  WiFiClient client = server.client();
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: image/jpeg");
  client.println("Cache-Control: no-store");
  client.println("Access-Control-Allow-Origin: *");
  client.print("Content-Length: ");
  client.println(g_jpeg_len);
  client.println("Connection: close");
  client.println();
  client.write(g_jpeg, g_jpeg_len);
}

static void handleCapture() {
  bool ok = captureStill();
  server.send(ok ? 200 : 500, "text/plain", ok ? "ok" : "capture failed");
}

static void startStillServer() {
  server.on("/", HTTP_GET, handleIndex);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/still", HTTP_GET, handleStill);
  server.on("/capture", HTTP_GET, handleCapture);
  server.begin();
}

void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

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
  config.frame_size = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  if (config.pixel_format == PIXFORMAT_JPEG) {
    if (psramFound()) {
      config.jpeg_quality = 10;
      config.fb_count = 2;
      config.grab_mode = CAMERA_GRAB_LATEST;
    } else {
      config.frame_size = FRAMESIZE_SVGA;
      config.fb_location = CAMERA_FB_IN_DRAM;
    }
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);
    s->set_brightness(s, 1);
    s->set_saturation(s, -2);
  }
  if (config.pixel_format == PIXFORMAT_JPEG) {
    s->set_framesize(s, FRAMESIZE_QVGA);
  }

  WiFi.begin(ssid, password);
  WiFi.setSleep(false);

  Serial.print("WiFi connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.println("WiFi connected");

  startStillServer();
  captureStill();

  Serial.print("Camera Ready! Open http://");
  Serial.print(WiFi.localIP());
  Serial.println(" in a browser");
  Serial.println("Auto Get Still every 60 seconds");
  Serial.print("Each JPEG POSTs to ");
  Serial.println(UPLOAD_URL);
}

void loop() {
  server.handleClient();

  if (g_last_capture_ms == 0 || (millis() - g_last_capture_ms) >= STILL_INTERVAL_MS) {
    captureStill();
  }
}
