import numpy as np
import pytest

from epl_forecast.season_evaluation import points_metrics, rank_scores, summarize


def test_trps_perfect_worst_and_partial_rankings():
    assert rank_scores(np.eye(3), np.array([1, 2, 3])).mean() == 0
    assert rank_scores([[1, 0, 0]], np.array([3]))[0] == 1
    assert rank_scores([[0.5, 0.5]], np.array([2]))[0] == 0.25
    with pytest.raises(ValueError):
        rank_scores([[0.2, 0.2]], np.array([1]))


def test_discrete_pit_crps_and_coverage():
    distribution = {"0": 0.25, "2": 0.5, "4": 0.25}
    result = points_metrics(distribution, 2, 0.5)
    assert result["pit"] == 0.5
    assert result["points_crps"] == 0.25
    assert result["coverage_90"] == 1
    assert result["width_90"] == 4
    assert points_metrics(distribution, -1, 0.2)["pit"] == 0
    assert points_metrics(distribution, 5, 0.2)["pit"] == 1
    assert points_metrics({"7": 1}, 7, 0.3)["points_crps"] == 0


def test_crps_matches_pairwise_definition():
    p = np.array([0.2, 0.3, 0.5])
    x = np.array([-4, 2, 8])
    expected = np.abs(x - 3) @ p - 0.5 * np.sum(
        p[:, None] * p[None, :] * np.abs(x[:, None] - x[None, :])
    )
    assert points_metrics(dict(zip(map(str, x), p, strict=True)), 3, 0.1)[
        "points_crps"
    ] == pytest.approx(expected)


def test_pooling_and_boundary_bins():
    row = {
        "model_id": "M2",
        "origin": "preseason",
        "season_id": "2020-2021",
        "promoted": True,
        "trps": 0.2,
        **points_metrics({"3": 1}, 5, 0.1),
    }
    for event in ("title", "top_four", "relegation"):
        row.update({f"{event}_probability": 1, f"{event}_observed": 0, f"{event}_brier": 1})
    summary, calibration = summarize([row, row | {"season_id": "2021-2022"}])
    assert summary[0]["club_seasons"] == 2
    assert summary[0]["points_rmse"] == 2
    assert sum(r["count"] for r in calibration if r["event"] == "pit") == 2
    assert calibration[9]["count"] == 2
