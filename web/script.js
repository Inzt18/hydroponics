const deviceSelect = document.getElementById("deviceSelect");
const statusDot = document.getElementById("statusDot");
const latestImage = document.getElementById("latestImage");
const imageTime = document.getElementById("imageTime");
const moistureValue = document.getElementById("moistureValue");
const dataTime = document.getElementById("dataTime");
const gauge = document.querySelector(".gauge");
const canvas = document.getElementById("historyChart");
const ctx = canvas.getContext("2d");

const REFRESH_MS = 10000;
let currentDevice = null;

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

function formatTime(iso) {
  if (!iso) return "--";
  const d = new Date(iso);
  return d.toLocaleString();
}

async function loadDevices() {
  try {
    const devices = await fetchJSON("/api/devices");
    const prevSelection = deviceSelect.value;

    deviceSelect.innerHTML = "";
    devices.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.textContent = d;
      deviceSelect.appendChild(opt);
    });

    if (devices.length === 0) {
      const opt = document.createElement("option");
      opt.textContent = "No devices yet";
      deviceSelect.appendChild(opt);
      statusDot.className = "status-dot offline";
      return;
    }

    // Keep previous selection if it still exists, else default to first device
    currentDevice =
      devices.includes(prevSelection) && prevSelection
        ? prevSelection
        : devices[0];
    deviceSelect.value = currentDevice;
  } catch (e) {
    console.error(e);
    statusDot.className = "status-dot offline";
  }
}

async function refreshLatest() {
  if (!currentDevice) return;

  try {
    const latest = await fetchJSON(`/api/latest?device=${encodeURIComponent(currentDevice)}`);
    statusDot.className = "status-dot online";

    if (latest.imageUrl) {
      latestImage.src = latest.imageUrl + "?t=" + Date.now(); // cache-bust
      imageTime.textContent = "Captured: " + formatTime(latest.imageTime);
    } else {
      imageTime.textContent = "No image received yet";
    }

    if (latest.latestReading && latest.latestReading.soil_moisture_percent != null) {
      const pct = latest.latestReading.soil_moisture_percent;
      moistureValue.textContent = pct + "%";
      dataTime.textContent = "Updated: " + formatTime(latest.latestReading.time);
      updateGauge(pct);
    } else {
      moistureValue.textContent = "--%";
      dataTime.textContent = "No data received yet";
    }
  } catch (e) {
    console.error(e);
    statusDot.className = "status-dot offline";
  }
}

function updateGauge(percent) {
  const degrees = (percent / 100) * 360;
  gauge.style.background = `conic-gradient(var(--green) ${degrees}deg, var(--green-light) ${degrees}deg)`;
}

async function refreshHistory() {
  if (!currentDevice) return;

  try {
    const history = await fetchJSON(`/api/history?device=${encodeURIComponent(currentDevice)}`);
    drawChart(history);
  } catch (e) {
    console.error(e);
  }
}

function drawChart(history) {
  const points = history
    .filter((h) => h.soil_moisture_percent != null)
    .slice(-40); // last 40 readings

  const width = canvas.width = canvas.clientWidth;
  const height = canvas.height = 160;

  ctx.clearRect(0, 0, width, height);

  if (points.length < 2) {
    ctx.fillStyle = "#6b7a68";
    ctx.font = "14px sans-serif";
    ctx.fillText("Not enough data yet to draw a trend.", 10, height / 2);
    return;
  }

  const padding = 24;
  const maxVal = 100;
  const minVal = 0;
  const stepX = (width - padding * 2) / (points.length - 1);

  // grid lines
  ctx.strokeStyle = "#eaf5ee";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padding + ((height - padding * 2) / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding, y);
    ctx.lineTo(width - padding, y);
    ctx.stroke();
  }

  // line
  ctx.strokeStyle = "#3a8654";
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = padding + stepX * i;
    const y =
      height - padding - ((p.soil_moisture_percent - minVal) / (maxVal - minVal)) * (height - padding * 2);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // dots
  ctx.fillStyle = "#3a8654";
  points.forEach((p, i) => {
    const x = padding + stepX * i;
    const y =
      height - padding - ((p.soil_moisture_percent - minVal) / (maxVal - minVal)) * (height - padding * 2);
    ctx.beginPath();
    ctx.arc(x, y, 2.5, 0, Math.PI * 2);
    ctx.fill();
  });
}

deviceSelect.addEventListener("change", (e) => {
  currentDevice = e.target.value;
  refreshLatest();
  refreshHistory();
});

async function tick() {
  await loadDevices();
  await refreshLatest();
  await refreshHistory();
}

tick();
setInterval(tick, REFRESH_MS);
