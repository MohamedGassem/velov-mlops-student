"""Génère le bronze de démonstration (data/fixtures) : 48 h d'instantanés GBFS 2.3 + la météo.

Sert à développer silver et gold sans attendre des jours de collecte, et quand le réseau
bloque le vrai flux. Les fichiers générés sont versionnés : ce script sert à les recréer
ou à en produire une variante. Graine fixe : on obtient toujours les mêmes fichiers.

Anomalies volontaires :
- instantanés relus deux fois (même last_updated) : le flux n'a pas changé entre deux appels ;
- station 10007 désinstallée pendant 3 h ;
- station 10012 figée à partir de la 20e heure (last_reported qui n'avance plus) ;
- une valeur aberrante (99 vélos à la station 10004).

Usage : python scripts/make_fixtures.py [--out data/fixtures]
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

START = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)
HOURS = 48
STEP_MIN = 5


def generate(out: Path) -> int:
    rng = np.random.default_rng(7)
    stations = []
    for i in range(20):
        sid = str(10001 + i)
        stations.append(
            {
                "station_id": sid,
                "name": f"Station {sid}",
                "lat": round(45.75 + 0.002 * i, 4),
                "lon": round(4.84 + 0.002 * i, 4),
                "capacity": int(rng.integers(15, 41)),
            }
        )

    (out / "snapshots").mkdir(parents=True, exist_ok=True)
    info = {"last_updated": int(START.timestamp()), "ttl": 3600, "version": "2.3", "data": {"stations": stations}}
    (out / "station_information.json").write_text(json.dumps(info))

    level = {s["station_id"]: 0.5 for s in stations}
    stale_from = START + timedelta(hours=20)
    t, n = START, 0
    while t < START + timedelta(hours=HOURS):
        rows = []
        for s in stations:
            sid, cap = s["station_id"], s["capacity"]
            h = t.hour + t.minute / 60
            target = 0.5 + 0.3 * math.sin((h - 8) / 24 * 2 * math.pi) * (1 if int(sid) % 2 else -1)
            level[sid] += 0.2 * (target - level[sid]) + rng.normal(0, 0.03)
            level[sid] = min(max(level[sid], 0), 1)
            bikes = int(round(level[sid] * cap))
            installed = not (sid == "10007" and START + timedelta(hours=30) <= t < START + timedelta(hours=33))
            reported = t - timedelta(seconds=int(rng.integers(0, 90)))
            if sid == "10012" and t >= stale_from:
                reported = stale_from
            rows.append(
                {
                    "station_id": sid,
                    "num_bikes_available": bikes if installed else 0,
                    "num_docks_available": cap - bikes if installed else 0,
                    "is_installed": int(installed),
                    "is_renting": int(installed),
                    "is_returning": int(installed),
                    "last_reported": int(reported.timestamp()),
                }
            )
        if t == START + timedelta(hours=26, minutes=35):
            rows[3]["num_bikes_available"] = 99  # aberration capteur
        snap = {"last_updated": int(t.timestamp()), "ttl": 60, "version": "2.3", "data": {"stations": rows}}
        (out / "snapshots" / f"{n:05d}.json").write_text(json.dumps(snap))
        n += 1
        if n % 50 == 0:  # même instantané relu : le flux n'a pas changé entre deux appels
            (out / "snapshots" / f"{n:05d}.json").write_text(json.dumps(snap))
            n += 1
        t += timedelta(minutes=STEP_MIN)

    hours = [START + timedelta(hours=i) for i in range(HOURS)]
    weather = {
        "latitude": 45.76,
        "longitude": 4.84,
        "timezone": "GMT",
        "hourly_units": {"time": "iso8601", "temperature_2m": "°C", "precipitation": "mm"},
        "hourly": {
            "time": [h.strftime("%Y-%m-%dT%H:%M") for h in hours],
            "temperature_2m": [round(13 + 5 * math.sin((h.hour - 9) / 24 * 2 * math.pi), 1) for h in hours],
            "precipitation": [round(float(rng.choice([0, 0, 0, 0, 0.4, 1.2])), 1) for _ in hours],
        },
    }
    (out / "weather.json").write_text(json.dumps(weather))
    return n


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/fixtures"))
    args = parser.parse_args()
    count = generate(args.out)
    print(f"{count} instantanés écrits dans {args.out / 'snapshots'}")
