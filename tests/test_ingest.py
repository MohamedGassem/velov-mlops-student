"""Ingestion bronze (S3) : idempotence et rangement, sur un extrait du bronze de démonstration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from velov.ingest import ingest, replay

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"


@pytest.fixture
def small_fixtures(tmp_path) -> Path:
    """Les 60 premiers instantanés (dont un relu deux fois), le référentiel et la météo."""
    if not (FIXTURES / "snapshots").exists():
        pytest.skip("bronze de démonstration absent : python scripts/make_fixtures.py")
    out = tmp_path / "fixtures"
    (out / "snapshots").mkdir(parents=True)
    for snap in sorted((FIXTURES / "snapshots").glob("*.json"))[:60]:
        shutil.copy(snap, out / "snapshots" / snap.name)
    for name in ("station_information.json", "weather.json"):
        shutil.copy(FIXTURES / name, out / name)
    return out


def test_replay_is_idempotent(small_fixtures, tmp_path):
    """EX-10 au niveau bronze : un second passage n'écrit rien."""
    bronze = tmp_path / "bronze"
    first = replay(small_fixtures, bronze)
    second = replay(small_fixtures, bronze)
    assert first == (59, 1)  # l'instantané n°50 est relu : même last_updated, même fichier
    assert second == (0, 60)
    assert len(list((bronze / "station_status").rglob("*.json"))) == 59


def test_file_name_comes_from_the_data(small_fixtures, tmp_path):
    snap = sorted((small_fixtures / "snapshots").glob("*.json"))[0]
    payload = json.loads(snap.read_text())
    target, written = ingest(snap.resolve().as_uri(), tmp_path, "station_status")
    assert written
    assert target.name == f"{payload['last_updated']}.json"  # pas l'heure du run
    assert target.parent.name == "dt=2026-10-05"
    assert not list(tmp_path.rglob("*.tmp"))  # écriture atomique : aucun fichier temporaire laissé


def test_weather_without_timestamp_uses_content_hash(small_fixtures, tmp_path):
    url = (small_fixtures / "weather.json").resolve().as_uri()
    first, _ = ingest(url, tmp_path, "weather")
    again, written = ingest(url, tmp_path, "weather")
    assert again == first and not written
    assert len(first.stem) == 16


def test_unexpected_status_payload_is_refused(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"data": {"stations": []}}))
    with pytest.raises(ValueError, match="last_updated"):
        ingest(bad.resolve().as_uri(), tmp_path / "bronze", "station_status")


def test_only_https_or_local_files(tmp_path):
    with pytest.raises(ValueError, match="refusée"):
        ingest("http://example.com/station_status.json", tmp_path, "station_status")
