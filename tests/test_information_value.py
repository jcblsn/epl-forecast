from copy import deepcopy

import numpy as np
import pytest

from epl_forecast.research.information_value import (
    correlated_sensor_calibration,
    fit_residual_sensor,
    information_report,
    predict_residual_sensor,
)


def test_residual_fit_uses_incremental_signal_and_does_not_double_count_duplicates():
    rng = np.random.default_rng(1)
    controls = rng.normal(size=(2000, 2))
    sensor = 3 * controls[:, 0] + rng.normal(size=2000)
    y = 2 * controls[:, 0] + 0.7 * sensor + rng.normal(size=2000)
    one = fit_residual_sensor(controls, sensor[:, None], y)
    duplicate = fit_residual_sensor(controls, np.column_stack((sensor, sensor)), y)
    assert one["beta"][0] == pytest.approx(0.7, abs=0.1)
    assert one["variance"] == pytest.approx(duplicate["variance"], abs=0.003)
    assert one["variance"] < one["baseline_variance"]
    assert np.isfinite(predict_residual_sensor(one, controls[:10], sensor[:10, None])).all()


def test_known_state_check_exposes_false_sensor_independence():
    result = correlated_sensor_calibration()
    joint, independent = result["results"]
    assert joint["known_state_coverage_90"] == pytest.approx(0.9, abs=0.015)
    assert independent["known_state_coverage_90"] < 0.8
    assert independent["posterior_variance"] < joint["posterior_variance"]


def test_future_sensor_targets_cannot_change_earlier_fitted_coefficients():
    rng = np.random.default_rng(9)
    rows = []
    for year in (2020, 2021, 2022):
        for i in range(300):
            signals = dict(
                zip(("goals", "xg", "shots", "shots_on_target"), rng.uniform(0, 10, 4), strict=True)
            )
            rows.append(
                {
                    "competition_id": "eng-premier-league",
                    "season_id": f"{year}-{year + 1}",
                    "match_id": f"{year}-{i}",
                    "team_id": f"team-{i % 20}",
                    "target_match_id": f"target-{year}-{i}",
                    "horizon": 1,
                    "information_available_on": f"{year}-08-02",
                    "target_available_on": f"{year}-08-09",
                    "controls": rng.normal(size=2).tolist(),
                    "signals": signals,
                    "target": float(np.log1p(signals["xg"]) + rng.normal()),
                }
            )
    before = information_report(rows)
    changed = deepcopy(rows)
    for row in changed:
        if row["season_id"] == "2022-2023":
            row["target"] += 100
    after = information_report(changed)
    assert before["coefficients"] == after["coefficients"]
    assert before["predictions"] != after["predictions"]
    assert all(
        r["training_last_target_available_on"] < r["test_first_information_available_on"]
        for r in before["coefficients"]
    )
    assert any(
        r["candidate"] == "goals+xg+shots+shots_on_target" and r["comparator"] == "goals+xg+shots"
        for r in before["comparisons"]
    )
