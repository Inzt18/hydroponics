"""Current weather for the dashboard. Uses Open-Meteo (no API key)."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

_CACHE_S = 600
_cache: dict = {"at": 0.0, "payload": None}

_WMO = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}


def _lat() -> float:
    return float(os.getenv("WEATHER_LAT", "14.5995"))


def _lon() -> float:
    return float(os.getenv("WEATHER_LON", "120.9842"))


def _place() -> str:
    return os.getenv("WEATHER_PLACE", "Manila").strip() or "Manila"


def _describe(code: object) -> str:
    try:
        return _WMO.get(int(code), "Unknown")
    except (TypeError, ValueError):
        return "Unknown"


def fetch_weather() -> dict:
    now = time.time()
    cached = _cache.get("payload")
    if cached and now - float(_cache.get("at") or 0) < _CACHE_S:
        return cached

    params = urllib.parse.urlencode(
        {
            "latitude": _lat(),
            "longitude": _lon(),
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
            "timezone": os.getenv("WEATHER_TZ", "Asia/Manila"),
            "forecast_days": 1,
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "hydroponics-dashboard"})
    with urllib.request.urlopen(request, timeout=12) as response:
        raw = json.loads(response.read().decode("utf-8"))

    current = raw.get("current") or {}
    daily = raw.get("daily") or {}
    payload = {
        "ok": True,
        "place": _place(),
        "temperature_c": current.get("temperature_2m"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "wind_kmh": current.get("wind_speed_10m"),
        "rain_mm": current.get("precipitation"),
        "condition": _describe(current.get("weather_code")),
        "today_high_c": (daily.get("temperature_2m_max") or [None])[0],
        "today_low_c": (daily.get("temperature_2m_min") or [None])[0],
        "today_rain_mm": (daily.get("precipitation_sum") or [None])[0],
        "updated": current.get("time"),
    }
    _cache["at"] = now
    _cache["payload"] = payload
    return payload
