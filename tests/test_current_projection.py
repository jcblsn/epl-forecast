import pytest

from epl_forecast.research.current_projection import compare_forecasts, noise_flags, rank_distances


def team(team_id, probabilities, mean, interval, event):
    return {
        "team_id": team_id,
        "position_probabilities": probabilities,
        "mean_position": mean,
        "position_intervals": {"50": interval, "80": interval, "90": interval},
        "title_probability": event,
    }


def forecast(row):
    return {
        "competition_id": "eng-premier-league",
        "season_id": "2026-2027",
        "results_observed_at": "2026-09-10T14:42:02+00:00",
        "teams": [row],
    }


def test_projection_distances_and_noise_flags_are_team_matched():
    baseline = team("a", [0.5, 0.3, 0.2], 1.7, [1, 3], 0.5)
    candidate = team("a", [0.3, 0.4, 0.3], 2.0, [1, 3], 0.3)
    wasserstein, total_variation = rank_distances(candidate, baseline)
    assert wasserstein == pytest.approx(0.3)
    assert total_variation == pytest.approx(0.2)
    rows = compare_forecasts(forecast(candidate), forecast(baseline), {"a": "A"}, "switch")
    noise = compare_forecasts(
        forecast(team("a", [0.49, 0.31, 0.2], 1.71, [1, 3], 0.49)),
        forecast(baseline),
        {"a": "A"},
        "mc_replication",
    )
    noise_flags(rows, noise)
    assert rows[0]["rank_wasserstein_exceeds_mc_noise"]
    assert rows[0]["title_probability_change_exceeds_mc_noise"]
