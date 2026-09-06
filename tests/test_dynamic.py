from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest
from scipy.optimize import minimize

from epl_forecast.cli import fitted_model
from epl_forecast.evaluation import rolling_predictions
from epl_forecast.models.dynamic import DynamicAttackDefense
from epl_forecast.models.gaussian import poisson_laplace_update
from epl_forecast.models.poisson import IndependentPoisson, PoissonMixture
from epl_forecast.models.promotion import CHAMPIONSHIP, PL, PromotionBridge
from epl_forecast.schema import Fixture, Match, fixture_id


def season_matches(year, competition, teams, seed):
    rng = np.random.default_rng(seed)
    strengths = np.linspace(-0.3, 0.3, len(teams))
    pairs = [(h, a) for h in range(len(teams)) for a in range(len(teams)) if h != a]
    matches = []
    for index, (h, a) in enumerate(pairs):
        season = f"{year}-{year + 1}"
        fixture = Fixture(
            fixture_id(competition, season, teams[h], teams[a]),
            competition,
            season,
            date(year, 8, 1) + timedelta(days=index // 10),
            teams[h],
            teams[a],
        )
        matches.append(
            Match(
                fixture,
                int(rng.poisson(np.exp(0.4 + strengths[h] - strengths[a]))),
                int(rng.poisson(np.exp(0.2 + strengths[a] - strengths[h]))),
            )
        )
    return matches


@pytest.fixture
def bridge_history():
    return (
        season_matches(
            2018, CHAMPIONSHIP, [f"e{i}" for i in range(3)] + [f"c{i}" for i in range(21)], 1
        )
        + season_matches(2019, PL, [f"e{i}" for i in range(3)] + [f"p{i}" for i in range(17)], 2)
        + season_matches(
            2019, CHAMPIONSHIP, [f"e{i}" for i in range(3, 6)] + [f"c{i}" for i in range(21)], 3
        )
    )


def test_laplace_update_matches_full_posterior_optimization():
    mean = np.array([0.1, -0.2, 0.3])
    covariance = np.array([[0.2, 0.02, 0.01], [0.02, 0.3, -0.04], [0.01, -0.04, 0.25]])
    design = np.array([[1, 1, 0], [1, 0, -1], [1, 1, 0]])
    goals = np.array([3, 0, 2])
    precision = np.linalg.inv(covariance)

    def objective(x):
        eta, diff = design @ x, x - mean
        return 0.5 * (diff @ precision @ diff) + np.sum(np.exp(eta) - goals * eta)

    result = minimize(objective, mean, method="BFGS", tol=1e-8)
    actual_mean, actual_covariance = poisson_laplace_update(mean, covariance, design, goals)
    assert actual_mean == pytest.approx(result.x, abs=1e-7)
    expected_covariance = np.linalg.inv(precision + (design.T * np.exp(design @ result.x)) @ design)
    assert actual_covariance == pytest.approx(expected_covariance, abs=1e-7)
    reordered = poisson_laplace_update(mean, covariance, design[::-1], goals[::-1])
    assert reordered[0] == pytest.approx(actual_mean)
    assert reordered[1] == pytest.approx(actual_covariance)


def test_poisson_mixture_integrates_uncertainty_and_keeps_score_tails():
    mean = np.log([1.8, 0.9])
    covariance = np.array([[0.15, 0.06], [0.06, 0.12]])
    scores = PoissonMixture(mean, covariance, order=15)
    assert scores.home_rate == pytest.approx(np.exp(mean[0] + covariance[0, 0] / 2))
    assert scores.away_rate == pytest.approx(np.exp(mean[1] + covariance[1, 1] / 2))
    grid, tail = scores.grid(30)
    assert sum(scores.outcome_probabilities()) == pytest.approx(1)
    assert scores.outcome_probabilities() == pytest.approx(
        [np.tril(grid, -1).sum(), np.trace(grid), np.triu(grid, 1).sum()], abs=1e-6
    )
    assert grid.sum() + tail == pytest.approx(1)
    assert np.isfinite(scores.log_probability(35, 25))
    deterministic = PoissonMixture(mean, np.zeros((2, 2)))
    assert deterministic.outcome_probabilities() == pytest.approx(
        IndependentPoisson(1.8, 0.9).outcome_probabilities()
    )
    home, away = scores.sample(np.random.default_rng(5), 100000)
    assert home.mean() == pytest.approx(scores.home_rate, abs=0.02)
    assert np.cov(home, away)[0, 1] > 0.08


def test_bridge_uses_only_completed_past_cohorts(bridge_history):
    cutoff = date(2020, 8, 1)
    bridge = PromotionBridge(bridge_history, cutoff, "2020-2021")
    assert len(bridge.cohorts) == 3
    assert bridge.diagnostics()["last_target_season"] == "2019-2020"
    prior = bridge.prior("e3")
    assert prior is not None and np.linalg.eigvalsh(prior.covariance).min() > 0
    later = season_matches(
        2020, PL, [f"e{i}" for i in range(3, 6)] + [f"p{i}" for i in range(17)], 4
    )
    changed = [replace(m, home_goals=20) for m in later]
    second = PromotionBridge(bridge_history + changed, cutoff, "2020-2021")
    assert second.prior("e3").mean == pytest.approx(prior.mean)
    assert second.prior("e3").covariance == pytest.approx(prior.covariance)
    incomplete = bridge_history[:-1]
    assert PromotionBridge(incomplete, cutoff, "2020-2021").prior("e3") is None


def test_promoted_prior_is_used_before_first_pl_result_and_replaces_stale_pl(bridge_history):
    cutoff = date(2020, 8, 1)
    old = season_matches(2017, PL, ["e3"] + [f"p{i}" for i in range(19)], 5)
    model = DynamicAttackDefense().fit(old + bridge_history, cutoff)
    expected = PromotionBridge(old + bridge_history, cutoff, "2020-2021").prior("e3")
    state = model.team_state("e3", "2020-2021")
    assert state.mean == pytest.approx(expected.mean)
    assert state.covariance == pytest.approx(expected.covariance)
    assert model.team_summary("e3", "2020-2021")["season_pl_matches"] == 0


def test_dynamic_incremental_fit_and_changed_history_replay(small_history):
    model = DynamicAttackDefense().fit(small_history[:5], date(2020, 8, 6))
    model.fit(small_history, date(2020, 8, 20))
    fresh = DynamicAttackDefense().fit(small_history, date(2020, 8, 20))
    assert model.mean == pytest.approx(fresh.mean, abs=1e-8)
    assert model.covariance == pytest.approx(fresh.covariance, abs=1e-8)
    changed = [replace(small_history[0], home_goals=8)] + small_history[1:]
    model.fit(changed, date(2020, 8, 20))
    fresh.fit(changed, date(2020, 8, 20))
    assert model.mean == pytest.approx(fresh.mean)
    assert np.linalg.eigvalsh(model.covariance).min() > 0
    with pytest.raises(ValueError, match="unavailable"):
        model.fit(small_history, date(2020, 8, 12))


def test_dynamics_increase_uncertainty_during_a_gap_and_respond_to_results(small_history):
    model = DynamicAttackDefense().fit(small_history, date(2020, 8, 20))
    variance = np.diag(model.covariance).copy()
    model.fit(small_history, date(2021, 1, 1))
    assert np.all(np.diag(model.covariance) > variance)
    stronger = [
        replace(m, home_goals=5, away_goals=0)
        if m.fixture.home_team_id == "a"
        else replace(m, away_goals=5, home_goals=0)
        if m.fixture.away_team_id == "a"
        else m
        for m in small_history
    ]
    improved = DynamicAttackDefense().fit(stronger, date(2021, 1, 1))
    assert (
        improved.team_state("a", "2020-2021").mean[0]
        > model.team_state("a", "2020-2021").mean[0] + 0.3
    )
    assert (
        improved.team_state("a", "2020-2021").mean[1] > model.team_state("a", "2020-2021").mean[1]
    )


def test_posterior_state_draws_match_predictive_marginals_and_survive_refit(small_history):
    day = date(2020, 8, 20)
    model = DynamicAttackDefense().fit(small_history, day)
    fixture = replace(small_history[0].fixture, match_date=day)
    rng = np.random.default_rng(12)
    states = model.sample_forecast_state(rng, size=60000)
    home, away = states.sample_scores(fixture, rng)
    empirical = [np.mean(home > away), np.mean(home == away), np.mean(home < away)]
    assert empirical == pytest.approx(model.predict_match(fixture).probabilities, abs=0.008)
    saved = states.rates(fixture)
    model.fit(small_history, date(2021, 1, 1))
    for original, later in zip(saved, states.rates(fixture), strict=True):
        assert later == pytest.approx(original)


def test_shared_training_blocks_same_day_and_future_in_both_divisions(bridge_history):
    cutoff = date(2020, 8, 1)
    current = season_matches(
        2020, PL, [f"e{i}" for i in range(3, 6)] + [f"p{i}" for i in range(17)], 4
    )
    champ = season_matches(2020, CHAMPIONSHIP, [f"c{i}" for i in range(24)], 6)
    spec = {
        "id": "M4",
        "kind": "dynamic_attack_defense",
        "train_window_days": 0,
        "train_competitions": [PL, CHAMPIONSHIP],
    }
    config = {
        "competition_id": PL,
        "train_window_days": 1095,
        "min_train_matches": 1,
        "models": [spec],
    }
    history = bridge_history + current + champ
    altered = [replace(m, home_goals=20) if m.available_on > cutoff else m for m in history]
    original = rolling_predictions(history, config, cutoff, cutoff + timedelta(days=1))
    mutated = rolling_predictions(altered, config, cutoff, cutoff + timedelta(days=1))
    for a, b in zip(original, mutated, strict=True):
        assert [a[k] for k in ("p_home", "p_draw", "p_away")] == [
            b[k] for k in ("p_home", "p_draw", "p_away")
        ]
    model, _, training = fitted_model(history, config, "M4", cutoff)
    assert {m.fixture.competition_id for m in training} == {PL, CHAMPIONSHIP}
    assert all(m.available_on <= cutoff for m in training)
    predicted = {r["match_id"]: r for r in original}[current[0].fixture.match_id]
    assert model.predict_match(current[0].fixture).probabilities == pytest.approx(
        [predicted[k] for k in ("p_home", "p_draw", "p_away")]
    )
