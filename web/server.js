/*
 * Plant Monitor Backend
 * ----------------------
 * Receives:
 *   POST /upload/image?device=plant-01   (raw JPEG body)
 *   POST /upload/data                    (JSON body: { device, soil_moisture_percent, ... })
 *
 * Serves:
 *   GET  /api/latest?device=plant-01     -> latest image URL + sensor reading
 *   GET  /api/history?device=plant-01    -> recent sensor readings (for a chart)
 *   GET  /images/<filename>              -> stored plant photos
 *   /                                    -> the dashboard website (public/)
 */

const express = require("express");
const fs = require("fs");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3000;

const IMAGES_DIR = path.join(__dirname, "data", "images");
const DATA_FILE = path.join(__dirname, "data", "readings.json");

// Ensure storage exists
fs.mkdirSync(IMAGES_DIR, { recursive: true });
if (!fs.existsSync(DATA_FILE)) {
  fs.writeFileSync(DATA_FILE, JSON.stringify({}));
}

// ---- middleware ----
app.use(express.json());
app.use(
  express.raw({ type: "image/jpeg", limit: "10mb" })
);
app.use("/images", express.static(IMAGES_DIR));
app.use(express.static(path.join(__dirname, "public")));

// ---- helpers ----
function loadStore() {
  try {
    return JSON.parse(fs.readFileSync(DATA_FILE, "utf8"));
  } catch (e) {
    return {};
  }
}

function saveStore(store) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(store, null, 2));
}

function getDeviceEntry(store, device) {
  if (!store[device]) {
    store[device] = {
      latestImage: null,
      latestImageTime: null,
      history: [], // { time, soil_moisture_percent, ... }
    };
  }
  return store[device];
}

// ---- routes: receiving data from ESP32-CAM ----

// Image upload
app.post("/upload/image", (req, res) => {
  const device = req.query.device || "unknown-device";

  if (!req.body || req.body.length === 0) {
    return res.status(400).json({ error: "No image data received" });
  }

  const filename = `${device}-${Date.now()}.jpg`;
  const filepath = path.join(IMAGES_DIR, filename);

  fs.writeFile(filepath, req.body, (err) => {
    if (err) {
      console.error("Failed to save image:", err);
      return res.status(500).json({ error: "Failed to save image" });
    }

    const store = loadStore();
    const entry = getDeviceEntry(store, device);
    entry.latestImage = filename;
    entry.latestImageTime = new Date().toISOString();
    saveStore(store);

    console.log(`[image] Saved ${filename} (${req.body.length} bytes)`);
    res.status(200).json({ ok: true, filename });
  });
});

// Sensor data upload
app.post("/upload/data", (req, res) => {
  const { device, soil_moisture_percent } = req.body || {};

  if (!device) {
    return res.status(400).json({ error: "Missing 'device' field" });
  }

  const store = loadStore();
  const entry = getDeviceEntry(store, device);

  const reading = {
    time: new Date().toISOString(),
    soil_moisture_percent: soil_moisture_percent ?? null,
    ...req.body, // capture any extra sensor fields (temperature_c, light_level, etc.)
  };

  entry.history.push(reading);
  // Keep only the most recent 200 readings per device
  if (entry.history.length > 200) {
    entry.history = entry.history.slice(-200);
  }

  saveStore(store);

  console.log(`[data] ${device} ->`, reading);
  res.status(200).json({ ok: true });
});

// ---- routes: serving data to the website ----

app.get("/api/devices", (req, res) => {
  const store = loadStore();
  res.json(Object.keys(store));
});

app.get("/api/latest", (req, res) => {
  const device = req.query.device;
  const store = loadStore();

  if (!device || !store[device]) {
    return res.status(404).json({ error: "Device not found" });
  }

  const entry = store[device];
  const latestReading = entry.history[entry.history.length - 1] || null;

  res.json({
    device,
    imageUrl: entry.latestImage ? `/images/${entry.latestImage}` : null,
    imageTime: entry.latestImageTime,
    latestReading,
  });
});

app.get("/api/history", (req, res) => {
  const device = req.query.device;
  const store = loadStore();

  if (!device || !store[device]) {
    return res.status(404).json({ error: "Device not found" });
  }

  res.json(store[device].history);
});

app.listen(PORT, () => {
  console.log(`Plant monitor server running at http://localhost:${PORT}`);
});
