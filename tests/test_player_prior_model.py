from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from epl_forecast.models.quality_tilt import QualityTiltFilter
from epl_forecast.research.player_prior import PlayerPriorFeatures
from epl_forecast.research.player_prior_model import TimeVaryingPlayerFilter, TimeVaryingPlayerPrior
from epl_forecast.schema import Fixture, Match, fixture_id


def example():
    matches, rows = [], []
    teams = ["arsenal", "chelsea", "liverpool", "everton"]
    for i in range(10):
        home, away = teams[i % 4], teams[(i + 1 + i // 4) % 4]
        if home == away:
            away = teams[(i + 1) % 4]
        day = date(2024, 8, 1) + timedelta(days=5 * i)
        key = fixture_id("eng-premier-league", "2024-2025", home, away)
        if key in {m.fixture.match_id for m in matches}:
            continue
        f = Fixture(key, "eng-premier-league", "2024-2025", day, home, away)
        matches.append(Match(f, i % 4, i % 3))
        for team in (home, away):
            for j, role in enumerate(["GK"] + ["DEF"] * 4 + ["MID"] * 4 + ["FWD"] * 3):
                minutes = 90 if j < 10 or (j == 10 + i % 2) else 0
                rows.append(
                    {
                        "player_id": f"{team}-{j}",
                        "player_name": f"{team}-{j}",
                        "team_id": team,
                        "match_id": key,
                        "competition_id": f.competition_id,
                        "season_id": f.season_id,
                        "kickoff_time": f"{day}T14:00:00Z",
                        "minutes": minutes,
                        "starts": int(minutes > 0),
                        "position": role,
                        "passes_total": 30 + i + j,
                        "shots": j % 4,
                        "key_passes": j % 3,
                        "duels_won": j % 5,
                        "saves": i % 5 if j == 0 else None,
                        "rating": 6.0 + i % 3,
                        "provider": "api_football",
                        "retrieved_at": "2026-09-09T12:00:00Z",
                        "evidence_basis": "retrospective",
                    }
                )
    return matches, rows


def test_joint_mapping_residual_covariance_and_incremental_replay():
    matches, rows = example()
    source = PlayerPriorFeatures(rows)
    cutoff = matches[-1].available_on
    model = TimeVaryingPlayerFilter(source, lineup_draws=4).fit(
        matches[:2], matches[1].available_on
    )
    model.fit(matches, cutoff)
    fresh = TimeVaryingPlayerFilter(source, lineup_draws=4).fit(matches, cutoff)
    assert model.player_index == fresh.player_index
    assert model.mean == pytest.approx(fresh.mean, abs=1e-9)
    assert model.covariance == pytest.approx(fresh.covariance, abs=1e-9)
    assert np.linalg.eigvalsh(model.covariance).min() > 0
    mapping = model.mapping_slice
    club = slice(2, mapping.start)
    players = sorted(model.player_index.values())
    assert np.max(np.abs(model.mean[mapping])) > 1e-6
    assert np.max(np.abs(model.covariance[club, mapping])) > 1e-6
    assert np.max(np.abs(model.covariance[club, :][:, players])) > 1e-6
    before = model.mean.copy()
    f = replace(matches[0].fixture, match_date=cutoff)
    probability = model.predict_match(f).probabilities
    assert np.sum(probability) == pytest.approx(1)
    assert model.mean == pytest.approx(before)


def test_unchanged_lineup_exactly_cancels_all_player_terms():
    matches, rows = example()
    source = PlayerPriorFeatures(rows)
    model = TimeVaryingPlayerFilter(source).fit(matches[:1], matches[0].available_on)
    f = matches[0].fixture
    weights = model._centered_weights(f, matches[0].available_on)
    assert weights == {}
    assert np.all(model._design(f, model.as_of, weights, 1)[0] == 0)


def test_target_stats_and_actual_minutes_do_not_change_deployable_prior_or_forecast():
    matches, rows = example()
    target = matches[-1]
    train = matches[:-1]
    cutoff = target.fixture.match_date
    changed = [
        {**r, "shots": 999, "rating": 0, "minutes": 1, "position": "GK"}
        if r["match_id"] == target.fixture.match_id
        else r
        for r in rows
    ]
    models = [
        TimeVaryingPlayerFilter(PlayerPriorFeatures(r), lineup_draws=4).fit(train, cutoff)
        for r in (rows, changed)
    ]
    a, b = models
    assert a.mean == pytest.approx(b.mean)
    assert a.predict_match(target.fixture).probabilities == pytest.approx(
        b.predict_match(target.fixture).probabilities, abs=1e-12
    )
    pid = next(r["player_id"] for r in rows if r["match_id"] == target.fixture.match_id)
    assert a.player_prior(pid, target.fixture) == b.player_prior(pid, target.fixture)
    before = a.mean.copy()
    assert (
        np.max(
            np.abs(
                np.array(a.score_distribution(target.fixture, oracle=True).outcome_probabilities())
                - np.array(
                    b.score_distribution(target.fixture, oracle=True).outcome_probabilities()
                )
            )
        )
        > 1e-6
    )
    assert a.mean == pytest.approx(before)


def test_no_reference_preserves_parent_and_new_player_prior_is_finite():
    matches, _ = example()
    cutoff = matches[0].available_on
    model = TimeVaryingPlayerFilter(PlayerPriorFeatures([])).fit(matches[:1], cutoff)
    parent = QualityTiltFilter(dispersion=None).fit(matches[:1], cutoff)
    assert model.mean[:6] == pytest.approx(parent.mean)
    assert model.covariance[:6, :6] == pytest.approx(parent.covariance)
    f = replace(matches[0].fixture, match_date=cutoff)
    assert model.predict_match(f).probabilities == pytest.approx(
        parent.predict_match(f).probabilities
    )
    prior = model.player_prior("new", f)["components"]["quality"]
    assert prior["mean"] == 0 and np.isfinite(prior["sd"])


def test_rating_ensemble_retains_support_and_reports_mixture_priors():
    matches, rows = example()
    cutoff = matches[2].available_on
    model = TimeVaryingPlayerPrior(
        PlayerPriorFeatures(rows), include_rating=True, lineup_draws=2
    ).fit(matches[:3], cutoff)
    f = replace(matches[0].fixture, match_date=cutoff)
    assert len(model.members) == 4
    assert np.isclose(sum(model.predict_match(f).probabilities), 1)
    assert model.player_prior("new", f)["components"]["quality"]["sd"] > 0
    assert len(model.lineup_summary(f)) == 2
    with pytest.raises(NotImplementedError):
        model.sample_forecast_state(np.random.default_rng(1))
