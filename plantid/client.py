"""
Plant.id API v3 client (health assessment).
Docs: https://documenter.getpostman.com/view/24599534/2s93z5A4v2
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import requests

DEFAULT_BASE_URL = "https://api.plant.id/v3"


class PlantIdError(RuntimeError):
    pass


class PlantIdClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.getenv("PLANT_ID_API_KEY", "").strip()
        if not self.api_key or self.api_key == "your_api_key":
            raise PlantIdError(
                "Missing Plant.id API key. Set PLANT_ID_API_KEY in .env or environment."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        return {"Api-Key": self.api_key, "Content-Type": "application/json"}

    @staticmethod
    def image_to_base64(image_path: Path) -> str:
        data = image_path.read_bytes()
        return base64.b64encode(data).decode("ascii")

    def health_assessment(
        self,
        image_path: Path,
        details: str = "description,treatment,local_name,classification",
    ) -> dict[str, Any]:
        """
        POST /v3/health_assessment
        Returns raw JSON response from Plant.id.
        """
        payload = {"images": [self.image_to_base64(image_path)]}
        url = f"{self.base_url}/health_assessment"
        resp = requests.post(
            url,
            params={"details": details},
            headers=self._headers(),
            json=payload,
            timeout=self.timeout_s,
        )
        if resp.status_code == 401:
            raise PlantIdError("Invalid API key (401).")
        if resp.status_code == 429:
            raise PlantIdError("Not enough Plant.id credits (429).")
        if resp.status_code >= 400:
            raise PlantIdError(f"Plant.id HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json()
