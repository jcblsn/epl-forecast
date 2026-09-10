from datetime import date

import numpy as np
import pytest

from epl_forecast.models.cross_division import CrossDivisionQualityTilt, CrossDivisionXG
from epl_forecast.models.promotion import CHAMPIONSHIP, PL
from epl_forecast.schema import Fixture, Match, fixture_id

BASE, HOME, LEVEL = np.log(1.35), 0.24, -0.20


def two_division_history(seed=0, seasons=3, crossings=3, level=LEVEL):
    rng = np.random.default_rng(seed)
    pl = [f"pl{i}" for i in range(8)]
    championship = [f"ch{i}" for i in range(8)]
    quality = {t: rng.normal(0.0, 0.22) for t in pl + championship}
    tilt = {t: rng.normal(0.0, 0.10) for t in pl + championship}
    matches, start = [], date(2018, 8, 1)
    for year in range(2018, 2018 + seasons):
        season = f"{year}-{year + 1}"
        for competition, teams, offset in ((PL, pl, 0.0), (CHAMPIONSHIP, championship, level)):
            for index, (home, away) in enumerate((h, a) for h in teams for a in teams if h != a):
                day = date.fromordinal(start.toordinal() + index // 4)
                fixture = Fixture(
                    fixture_id(competition, season, home, away),
                    competition,
                    season,
                    day,
                    home,
                    away,
                )
                home_rate = np.exp(
                    BASE + HOME + offset + quality[home] + tilt[home] - quality[away] + tilt[away]
                )
                away_rate = np.exp(
                    BASE + offset + quality[away] + tilt[away] - quality[home] + tilt[home]
                )
                matches.append(
                    Match(fixture, int(rng.poisson(home_rate)), int(rng.poisson(away_rate)))
                )
        start = date(year + 1, 8, 1)
        for k in range(crossings):
            pl[-1 - k], championship[k] = championship[k], pl[-1 - k]
    return matches, quality


def test_a_promoted_club_carries_its_state_instead_of_resetting():
    matches, _ = two_division_history()
    cutoff = date(2021, 8, 1)
    model = CrossDivisionQualityTilt().fit(matches, cutoff)
    crossed = model.division_summary()["crossed_divisions"]
    assert crossed
    for team in crossed:
        entries = [source for (t, _), source in model.entry_priors.items() if t == team]
        assert any(e.source == "carried across seasons and divisions" for e in entries)
        assert sum(e.source == "cross-division population" for e in entries) == 1


def test_the_filter_recovers_a_known_division_scoring_level_and_home_advantage():
    matches, _ = two_division_history(seed=3)
    model = CrossDivisionQualityTilt().fit(matches, date(2021, 8, 1))
    summary = model.division_summary()
    assert (
        abs(summary["championship_scoring_level"] - LEVEL)
        < 3 * summary["championship_scoring_level_sd"]
    )
    assert abs(summary["home_advantage"] - HOME) < 3 * summary["home_advantage_sd"]


def test_observed_transitions_sharpen_the_division_scoring_level():
    with_crossings = CrossDivisionQualityTilt().fit(
        two_division_history(seed=1, crossings=3)[0], date(2021, 8, 1)
    )
    without = CrossDivisionQualityTilt().fit(
        two_division_history(seed=1, crossings=0)[0], date(2021, 8, 1)
    )
    assert with_crossings.covariance[2, 2] < without.covariance[2, 2]


def test_championship_fixtures_load_the_division_offsets_and_premier_league_does_not():
    matches, _ = two_division_history()
    model = CrossDivisionQualityTilt().fit(matches, date(2021, 8, 1))
    premier = Fixture(
        fixture_id(PL, "2021-2022", "pl0", "pl1"), PL, "2021-2022", date(2021, 8, 20), "pl0", "pl1"
    )
    second = Fixture(
        fixture_id(CHAMPIONSHIP, "2021-2022", "pl0", "pl1"),
        CHAMPIONSHIP,
        "2021-2022",
        date(2021, 8, 20),
        "pl0",
        "pl1",
    )
    assert model._league_design(premier)[:, 2:].sum() == 0
    assert model._league_design(second)[:, 2:].tolist() == [[1, 1], [1, 0]]
    top, lower = model.forecast_moments(premier)[0], model.forecast_moments(second)[0]
    assert lower == pytest.approx(
        top + model.division_scoring_level + [model.division_home_offset, 0]
    )


def test_the_same_club_keeps_one_state_slot_across_divisions():
    matches, _ = two_division_history()
    model = CrossDivisionQualityTilt().fit(matches, date(2021, 8, 1))
    assert len(model.team_index) == 16
    assert len(model.mean) == model.league_dimensions + 2 * 16


def test_a_division_outside_the_hierarchy_is_refused():
    matches, _ = two_division_history()
    stray = matches[0]
    competition = "esp-la-liga"
    outside = Match(
        Fixture(
            fixture_id(competition, "2018-2019", "a", "b"),
            competition,
            "2018-2019",
            stray.fixture.match_date,
            "a",
            "b",
        ),
        1,
        0,
    )
    with pytest.raises(ValueError, match="PL and Championship"):
        CrossDivisionQualityTilt().fit([*matches, outside], date(2021, 8, 1))


def xg_rows(matches, seed=0, noise=0.35):
    rng = np.random.default_rng(seed)
    rows = []
    for match in matches:
        rows.append(
            {
                "match_id": match.fixture.match_id,
                "match_date": str(match.fixture.match_date),
                "available_on": str(date.fromordinal(match.fixture.match_date.toordinal() + 1)),
                "home_goals": match.home_goals,
                "away_goals": match.away_goals,
                "home_xg": float(rng.gamma(4.0, (match.home_goals + noise) / 4.0)),
                "away_xg": float(rng.gamma(4.0, (match.away_goals + noise) / 4.0)),
            }
        )
    return rows


def test_team_xg_sharpens_club_states_without_replacing_the_goal_likelihood():
    matches, _ = two_division_history(seed=2)
    cutoff = date(2021, 8, 1)
    goals_only = CrossDivisionQualityTilt(dispersion=None).fit(matches, cutoff)
    with_xg = CrossDivisionXG(xg_rows(matches)).fit(matches, cutoff)
    assert with_xg.fit_diagnostics["xg_matches"] == len(matches)
    team = with_xg.league_dimensions
    assert np.trace(with_xg.covariance[team:, team:]) < np.trace(
        goals_only.covariance[team:, team:]
    )


def test_xg_published_after_the_daily_update_is_not_retrofitted():
    matches, _ = two_division_history(seed=2)
    rows = xg_rows(matches)
    for row in rows:
        row["available_on"] = "2030-06-01"
    late = CrossDivisionXG(rows).fit(matches, date(2021, 8, 1))
    assert late.fit_diagnostics["xg_matches"] == 0


def test_xg_states_still_recover_the_known_division_scoring_level():
    matches, _ = two_division_history(seed=3)
    model = CrossDivisionXG(xg_rows(matches)).fit(matches, date(2021, 8, 1))
    summary = model.division_summary()
    assert (
        abs(summary["championship_scoring_level"] - LEVEL)
        < 3 * summary["championship_scoring_level_sd"]
    )


def test_quality_tilt_and_attack_defence_are_one_state_in_two_coordinates():
    """The rotation is a change of coordinates, not a second model family."""
    matches, _ = two_division_history()
    cutoff = date(2021, 8, 1)
    model = CrossDivisionQualityTilt().fit(matches, cutoff)
    fixture = Fixture(
        fixture_id(PL, "2021-2022", "pl0", "pl1"), PL, "2021-2022", cutoff, "pl0", "pl1"
    )
    quality_mean, quality_covariance = model.forecast_moments(fixture)

    rotation = np.eye(len(model.mean))
    for index in range(len(model.team_index)):
        start = model.league_dimensions + 2 * index
        rotation[start : start + 2, start : start + 2] = [[1.0, 1.0], [1.0, -1.0]]
    attack_mean = rotation @ model.mean
    attack_covariance = rotation @ model.covariance @ rotation.T

    design = np.zeros((2, len(model.mean)))
    design[:, : model.league_dimensions] = model._league_design(fixture)
    for team, transform in zip(
        (fixture.home_team_id, fixture.away_team_id),
        (np.array([[1, 0], [0, -1]]), np.array([[0, -1], [1, 0]])),
        strict=True,
    ):
        design[:, model._team_slice(team)] = transform

    assert design @ attack_mean == pytest.approx(quality_mean, abs=1e-12)
    assert design @ attack_covariance @ design.T == pytest.approx(quality_covariance, abs=1e-12)


def _forward_rate_moments(model, fixture, size=40000, seed=7):
    sampled = model.sample_forecast_state(np.random.default_rng(seed), size)
    home, away = sampled.rates(fixture, np.random.default_rng(seed + 1))
    logs = np.log(np.column_stack([home, away]))
    return logs.mean(axis=0), np.cov(logs, rowvar=False)


def test_sampled_championship_states_reproduce_the_direct_forecast():
    """The forward simulator must load every leading league slot, not only two."""
    matches, _ = two_division_history()
    cutoff = date(2021, 8, 1)
    model = CrossDivisionQualityTilt(independent_poisson=True).fit(matches, cutoff)
    for competition in (PL, CHAMPIONSHIP):
        fixture = Fixture(
            fixture_id(competition, "2021-2022", "pl0", "pl1"),
            competition,
            "2021-2022",
            cutoff,
            "pl0",
            "pl1",
        )
        mean, covariance = model.forecast_moments(fixture)
        sampled_mean, sampled_covariance = _forward_rate_moments(model, fixture)
        assert sampled_mean == pytest.approx(mean, abs=0.02)
        assert sampled_covariance == pytest.approx(np.asarray(covariance), abs=0.02)


def test_the_championship_offsets_actually_move_the_sampled_rates():
    matches, _ = two_division_history()
    cutoff = date(2021, 8, 1)
    model = CrossDivisionQualityTilt(independent_poisson=True).fit(matches, cutoff)
    rates = {}
    for competition in (PL, CHAMPIONSHIP):
        fixture = Fixture(
            fixture_id(competition, "2021-2022", "pl0", "pl1"),
            competition,
            "2021-2022",
            cutoff,
            "pl0",
            "pl1",
        )
        rates[competition] = _forward_rate_moments(model, fixture)[0]
    shift = rates[CHAMPIONSHIP] - rates[PL]
    expected = np.array(
        [model.division_scoring_level + model.division_home_offset, model.division_scoring_level]
    )
    assert shift == pytest.approx(expected, abs=0.02)


def test_a_new_season_entrant_is_evolved_with_club_dynamics_not_league_dynamics():
    matches, _ = two_division_history()
    cutoff = date(2021, 8, 1)
    model = CrossDivisionQualityTilt(independent_poisson=True).fit(matches, cutoff)
    later = date(2022, 3, 1)
    fixture = Fixture(
        fixture_id(PL, "2021-2022", "pl0", "pl1"), PL, "2021-2022", later, "pl0", "pl1"
    )
    mean, covariance = model.forecast_moments(fixture)
    sampled_mean, sampled_covariance = _forward_rate_moments(model, fixture)
    assert sampled_mean == pytest.approx(mean, abs=0.03)
    assert sampled_covariance == pytest.approx(np.asarray(covariance), abs=0.03)


def test_the_declared_league_prior_reaches_the_initial_state():
    model = CrossDivisionQualityTilt(
        division_scoring_level_sd=0.31, division_home_sd=0.07, independent_poisson=True
    )
    assert np.sqrt(np.diag(model.covariance)) == pytest.approx([0.25, 0.25, 0.31, 0.07])
    assert model.mean[2:] == pytest.approx([0.0, 0.0])
