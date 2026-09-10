import math

import numpy as np
import pytest

from epl_forecast.research.score_law import (
    BASELINES,
    Quadrature,
    chronological_score_law,
    dependence_moments,
    dispersion_profile,
    distribution,
    event_calibration,
    fit_dispersion,
    predicted_tail_events,
    score_log_likelihood,
    state_moments,
    summarize,
    tail_events,
)


def row(day, home_goals=1, away_goals=0, model_id=BASELINES[2], **overrides):
    values = {
        "model_id": model_id,
        "match_id": f"m{day}",
        "season_id": "2024-2025",
        "match_date": f"2024-08-{day:02d}",
        "forecast_as_of": f"2024-08-{day:02d}",
        "home_goals": str(home_goals),
        "away_goals": str(away_goals),
        "outcome": "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D",
        "expected_home_goals": "1.6",
        "expected_away_goals": "1.1",
        "effective_specifications": "1.0",
        "log_home_rate_mean": "0.45",
        "log_away_rate_mean": "0.05",
        "log_home_rate_variance": "0.03",
        "log_away_rate_variance": "0.02",
        "log_rate_covariance": "-0.002",
    }
    return values | overrides


def test_m2_state_is_the_zero_variance_case():
    mean, covariance = state_moments(row(1, model_id=BASELINES[0]))
    assert np.allclose(np.exp(mean), [1.6, 1.1])
    assert np.allclose(covariance, 0.0)


def test_a_collapsed_mixture_is_rejected():
    with pytest.raises(ValueError, match="single effective Gaussian"):
        state_moments(row(1, effective_specifications="2.4"))


def test_quadrature_matches_the_per_case_distributions():
    rows = [row(day, day % 4, (day + 1) % 3) for day in range(1, 12)]
    cache = Quadrature(rows)
    for dispersion in (None, 4.0, 60.0):
        direct = sum(
            distribution(case, dispersion).log_probability(
                int(case["home_goals"]), int(case["away_goals"])
            )
            for case in rows
        )
        assert cache.log_likelihood(dispersion) == pytest.approx(direct, abs=1e-10)


def test_a_large_shape_returns_the_poisson_control():
    rows = [row(day, day % 3, day % 2) for day in range(1, 9)]
    assert score_log_likelihood(rows, 1e8) == pytest.approx(
        score_log_likelihood(rows, None), abs=1e-4
    )


def test_the_fitted_shape_recovers_a_planted_tempo():
    generator = np.random.default_rng(5)
    dispersion = 12.0
    tempo = generator.gamma(dispersion, 1 / dispersion, 4000)
    home = generator.poisson(tempo * 1.6)
    away = generator.poisson(tempo * 1.1)
    rows = [
        row(1, int(h), int(a), log_home_rate_variance="0.0", log_away_rate_variance="0.0")
        | {"log_home_rate_mean": str(math.log(1.6)), "log_away_rate_mean": str(math.log(1.1))}
        for h, a in zip(home, away, strict=True)
    ]
    rows = [case | {"log_rate_covariance": "0.0"} for case in rows]
    fit = fit_dispersion(rows)
    assert fit["dispersion"] == pytest.approx(dispersion, rel=0.35)
    assert not fit["at_boundary"]
    assert fit["gamma_log_likelihood"] > fit["poisson_log_likelihood"]


def test_independent_scores_push_the_shape_to_the_boundary():
    generator = np.random.default_rng(7)
    home = generator.poisson(1.6, 3000)
    away = generator.poisson(1.1, 3000)
    rows = [
        row(1, int(h), int(a))
        | {
            "log_home_rate_mean": str(math.log(1.6)),
            "log_away_rate_mean": str(math.log(1.1)),
            "log_home_rate_variance": "0.0",
            "log_away_rate_variance": "0.0",
            "log_rate_covariance": "0.0",
        }
        for h, a in zip(home, away, strict=True)
    ]
    fit = fit_dispersion(rows)
    assert fit["at_boundary"]
    assert fit["gamma_log_likelihood"] == pytest.approx(fit["poisson_log_likelihood"], abs=0.05)


def test_chronological_fits_use_only_earlier_fixtures():
    rows = [row(day, day % 3, day % 2) for day in range(1, 21)]
    block = chronological_score_law(rows, "2024-08-15", minimum_training=8)
    assert {fit["cutoff"] for fit in block["fits"]} == {f"2024-08-{day}" for day in range(15, 21)}
    assert [skipped["cutoff"] for skipped in block["skipped"]] == []
    assert all(fit["training_fixtures"] == int(fit["cutoff"][-2:]) - 1 for fit in block["fits"])
    variants = {prediction["variant"] for prediction in block["predictions"]}
    assert variants == {"poisson", "shared_gamma"}


def test_a_short_history_is_skipped_rather_than_fitted():
    rows = [row(day, 1, 1) for day in range(1, 6)]
    block = chronological_score_law(rows, "2024-08-01", minimum_training=4)
    assert [skipped["cutoff"] for skipped in block["skipped"]] == [
        "2024-08-01",
        "2024-08-02",
        "2024-08-03",
        "2024-08-04",
    ]
    assert [fit["cutoff"] for fit in block["fits"]] == ["2024-08-05"]


def test_the_summary_pairs_both_variants_on_every_fixture():
    rows = [row(day, day % 3, day % 2) for day in range(1, 21)]
    block = chronological_score_law(rows, "2024-08-15", minimum_training=8)
    summary = summarize(block["predictions"], BASELINES[2])
    assert summary["fixtures"] == 6
    for metric in ("score_nll", "log_loss", "brier"):
        values = summary["metrics"][metric]
        assert values["interval"][0] <= values["difference"] <= values["interval"][1]


def test_tail_events_label_the_observed_scoreline():
    assert tail_events(row(1, 0, 0)) == {
        "draw": True,
        "scoreless": True,
        "total_at_least_six": False,
        "both_teams_score": False,
    }
    assert tail_events(row(1, 4, 2)) == {
        "draw": False,
        "scoreless": False,
        "total_at_least_six": True,
        "both_teams_score": True,
    }


def test_the_shared_tempo_lifts_both_scoreless_and_high_scoring_mass():
    case = row(1, 1, 1)
    poisson = predicted_tail_events(case, None)
    gamma = predicted_tail_events(case, 6.0)
    assert gamma["scoreless"] > poisson["scoreless"]
    assert gamma["total_at_least_six"] > poisson["total_at_least_six"]
    assert gamma["both_teams_score"] < poisson["both_teams_score"]


def test_event_calibration_scores_only_the_fixtures_that_were_forecast():
    rows = [row(day, day % 3, day % 2) for day in range(1, 21)]
    block = chronological_score_law(rows, "2024-08-15", minimum_training=8)
    calibration = event_calibration(rows, block["predictions"])[BASELINES[2]]
    assert calibration["fixtures"] == 6
    draw = calibration["events"]["draw"]
    assert 0.0 <= draw["poisson"] <= 1.0
    assert draw["observed"] == pytest.approx(
        np.mean([tail_events(case)["draw"] for case in rows[14:]])
    )


def planted(home, away, **overrides):
    return [
        row(1, int(h), int(a))
        | {
            "log_home_rate_mean": str(math.log(1.6)),
            "log_away_rate_mean": str(math.log(1.1)),
            "log_home_rate_variance": "0.0",
            "log_away_rate_variance": "0.0",
            "log_rate_covariance": "0.0",
        }
        | overrides
        for h, a in zip(home, away, strict=True)
    ]


def test_the_profile_peaks_at_the_planted_tempo():
    generator = np.random.default_rng(11)
    tempo = generator.gamma(20.0, 1 / 20.0, 6000)
    rows = planted(generator.poisson(tempo * 1.6), generator.poisson(tempo * 1.1))
    profile = dispersion_profile(rows, shapes=(5.0, 20.0, 100.0, 10000.0))
    best = max(profile["gain"], key=profile["gain"].get)
    assert best == "20"
    assert profile["gain"]["20"] > 0
    assert profile["gain"]["10000"] == pytest.approx(0.0, abs=0.2)


def test_the_profile_never_gains_on_independent_scores():
    generator = np.random.default_rng(13)
    rows = planted(generator.poisson(1.6, 6000), generator.poisson(1.1, 6000))
    profile = dispersion_profile(rows, shapes=(5.0, 20.0, 100.0))
    assert all(gain < 0 for gain in profile["gain"].values())


def test_moments_recover_a_planted_shared_tempo():
    generator = np.random.default_rng(17)
    tempo = generator.gamma(20.0, 1 / 20.0, 20000)
    rows = planted(generator.poisson(tempo * 1.6), generator.poisson(tempo * 1.1))
    poisson = dependence_moments(rows)
    assert poisson["predicted_covariance"] == pytest.approx(0.0, abs=1e-12)
    assert poisson["observed_covariance"] > 0.05
    assert poisson["observed_total_variance"] > poisson["predicted_total_variance"]
    gamma = dependence_moments(rows, 20.0)
    assert gamma["predicted_covariance"] == pytest.approx(poisson["observed_covariance"], abs=0.03)
    assert gamma["predicted_total_variance"] == pytest.approx(
        poisson["observed_total_variance"], rel=0.05
    )


def test_state_uncertainty_alone_predicts_positive_covariance():
    moments = dependence_moments([row(1, 1, 1) | {"log_rate_covariance": "0.02"}])
    assert moments["predicted_covariance"] == pytest.approx(
        math.exp(0.45 + 0.05 + 0.5 * (0.03 + 0.02) + 0.02)
        - math.exp(0.45 + 0.015) * math.exp(0.05 + 0.01),
        rel=1e-6,
    )
