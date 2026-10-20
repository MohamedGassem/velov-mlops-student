"""Contrat Pandera de la table d'entraînement (S3, EX-12)."""

from __future__ import annotations

import pandas as pd
import pytest

pa = pytest.importorskip("pandera.pandas")

from velov.contract import StationHourly  # noqa: E402
from velov.data import simulate  # noqa: E402


@pytest.fixture
def gold() -> pd.DataFrame:
    """Une table au schéma du contrat : celle du simulateur, aux types de la table gold."""
    df = simulate(days=2, n_stations=3, seed=0)
    df["timestamp"] = df["timestamp"].dt.as_unit("us")
    return df


def failed_checks(df: pd.DataFrame) -> set[str]:
    with pytest.raises(pa.errors.SchemaErrors) as err:
        StationHourly.validate(df, lazy=True)
    return set(err.value.failure_cases["check"].astype(str))


def test_valid_table_passes(gold):
    assert len(StationHourly.validate(gold, lazy=True)) == len(gold)


def test_bikes_above_capacity_is_refused(gold):
    gold.loc[0, "bikes_available"] = gold.loc[0, "capacity"] + 1
    assert "bikes_le_capacity" in failed_checks(gold)


def test_duplicate_station_hour_is_refused(gold):
    doubled = pd.concat([gold, gold.iloc[[3]]], ignore_index=True)
    assert any("uniqueness" in c for c in failed_checks(doubled))


def test_timestamp_without_timezone_is_refused(gold):
    """Le piège de coerce=True : un horodatage sans fuseau doit être signalé, pas corrigé en silence."""
    gold["timestamp"] = gold["timestamp"].dt.tz_localize(None)
    assert any("datetime64[us, UTC]" in c for c in failed_checks(gold))


def test_extra_column_is_refused(gold):
    gold["bikes_next_hour"] = 0  # la cible n'a rien à faire dans la table source
    assert any("column_in_schema" in c for c in failed_checks(gold))
