"""Collect one idempotent bronze batch of Velov and weather data."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from velov.ingest import (
    STATION_INFORMATION_URL,
    STATION_STATUS_URL,
    fetch_json,
    fetch_weather,
    write_raw_snapshot,
)


def run_microbatch(output_dir: Path = Path("data/bronze")) -> dict[str, int | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    information, info_inserted = write_raw_snapshot(
        fetch_json(STATION_INFORMATION_URL), output_dir, "station_information"
    )
    status, status_inserted = write_raw_snapshot(
        fetch_json(STATION_STATUS_URL), output_dir, "station_status"
    )
    weather_payload = fetch_weather()
    # Open-Meteo changes this processing-duration field on every identical request.
    # It is not a business observation and must not defeat idempotence.
    weather_payload.pop("generationtime_ms", None)
    weather, weather_inserted = write_raw_snapshot(weather_payload, output_dir, "weather")
    return {
        "collected_at": datetime.now(UTC).isoformat(),
        "information_snapshot": str(information),
        "status_snapshot": str(status),
        "weather_snapshot": str(weather),
        "information_inserted": int(info_inserted),
        "status_inserted": int(status_inserted),
        "weather_inserted": int(weather_inserted),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect an idempotent Velov bronze batch.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/bronze"))
    args = parser.parse_args()
    print(run_microbatch(args.output_dir))


if __name__ == "__main__":
    main()
