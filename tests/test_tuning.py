from copy import deepcopy

import pytest

from epl_forecast.evaluation import summarize
from epl_forecast.tuning import select_by_prior_seasons


def predictions():
    return [
        {
            "season_id": f"{year}-{year + 1}",
            "match_id": str(year),
            "model_id": model,
            "outcome": "H",
            "p_home": p,
            "p_draw": (1 - p) / 2,
            "p_away": (1 - p) / 2,
            "score_log_probability": None,
        }
        for year, values in ((2020, [0.8, 0.4]), (2021, [0.2, 0.8]), (2022, [0.5, 0.5]))
        for model, p in zip(("A", "B"), values, strict=True)
    ]


def test_hyperparameter_selection_cannot_see_test_season():
    rows = predictions()
    choices, selected = select_by_prior_seasons(rows, "2021-2022")
    assert [choice["selected_model_id"] for choice in choices] == ["A", "B"]
    changed = deepcopy(rows)
    for row in changed:
        if row["season_id"] == "2022-2023" and row["model_id"] == "B":
            row.update(p_home=0.01, p_draw=0.495, p_away=0.495)
    later_choices, _ = select_by_prior_seasons(changed, "2021-2022")
    assert [choice["selected_model_id"] for choice in later_choices] == ["A", "B"]
    assert all(choice["selection_through_season"] < choice["season_id"] for choice in choices)
    assert all(row["model_id"] == "M2-prior-season-selection" for row in selected)


def test_selection_requires_earlier_and_matched_data():
    with pytest.raises(ValueError, match="earlier season"):
        select_by_prior_seasons(predictions(), "2020-2021")
    rows = predictions()
    rows[-1]["match_id"] = "different fixture"
    with pytest.raises(ValueError, match="identical"):
        select_by_prior_seasons(rows, "2021-2022")


def test_exploration_can_skip_bootstrap_and_keep_scores():
    report = summarize(predictions(), [], {"calibration_bins": 10})
    assert len(report["overall"]) == 2
    assert len(report["by_season"]) == 6
    assert report["paired_comparisons"] == []
