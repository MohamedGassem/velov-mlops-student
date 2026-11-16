from velov.promotion import promotion_failures


def test_valid_run_can_be_promoted() -> None:
    assert promotion_failures(
        "FINISHED",
        {"mae_model": 1.2, "mae_baseline_persistence": 1.8},
        {"data_sha256": "a" * 64},
    ) == []


def test_promotion_requires_three_conditions() -> None:
    failures = promotion_failures("RUNNING", {"mae_model": 2.0, "mae_baseline_persistence": 1.8}, {})
    assert len(failures) == 3
