"""Reusable, idempotent bronze-ingestion helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GBFS_BASE_URL = "https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov"
STATION_INFORMATION_URL = f"{GBFS_BASE_URL}/station_information.json"
STATION_STATUS_URL = f"{GBFS_BASE_URL}/station_status.json"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
LYON_LATITUDE = 45.764043
LYON_LONGITUDE = 4.835659


def write_raw_snapshot(payload: dict[str, Any], directory: Path, feed: str) -> tuple[Path, bool]:
    """Store immutable raw JSON once, using a stable source-derived name."""
    source_key = payload.get("last_updated")
    if source_key is None:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        source_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    target = directory / feed / f"{source_key}.json"
    if target.exists():
        return target, False

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target, True


def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    """Fetch a JSON object from a public endpoint."""
    request = Request(url, headers={"User-Agent": "velov-mlops/1.0"})  # noqa: S310
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return payload


def fetch_weather() -> dict[str, Any]:
    """Fetch hourly weather for Lyon in UTC, without an API key."""
    params = {
        "latitude": LYON_LATITUDE,
        "longitude": LYON_LONGITUDE,
        "hourly": "temperature_2m,precipitation,rain",
        "timezone": "UTC",
        "past_days": 1,
        "forecast_days": 2,
    }
    return fetch_json(f"{OPEN_METEO_URL}?{urlencode(params)}")
