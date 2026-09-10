from datetime import date

import numpy as np
import pytest

from epl_forecast.models.centered_quality_tilt import tilt_coordinates
from epl_forecast.models.cross_division import CrossDivisionQualityTilt
from epl_forecast.models.division_map import (
    IDENTITY,
    DivisionMap,
    DivisionMapPopulation,
    DivisionMapQualityTilt,
)
from epl_forecast.models.promotion import CHAMPIONSHIP, PL
from epl_forecast.schema import Fixture, Match, fixture_id

BASE, HOME, LEVEL = np.log(1.35), 0.24, -0.20


def two_division_history(seed=0, seasons=3, crossings=3, level=LEVEL, compression=1.0):
    """A club's Premier League strength is a compression of its own latent scale."""
    rng = np.random.default_rng(seed)
    pl = [f"pl{i}" for i in range(8)]
    championship = [f"ch{i}" for i in range(8)]
    quality = {t: rng.normal(0.0, 0.22) for t in pl + championship}
    tilt = {t: rng.normal(0.0, 0.10) for t in pl + championship}
    matches, start = [], date(2018, 8, 1)
    for year in range(2018, 2018 + seasons):
        season = f"{year}-{year + 1}"
        for competition, teams, offset in ((PL, pl, 0.0), (CHAMPIONSHIP, championship, level)):
            scale = compression if competition == PL else 1.0
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
                spread = scale * (quality[home] - quality[away])
                level_terms = BASE + offset + tilt[home] + tilt[away]
                matches.append(
                    Match(
                        fixture,
                        int(rng.poisson(np.exp(level_terms + HOME + spread))),
                        int(rng.poisson(np.exp(level_terms - spread))),
                    )
                )
        start = date(year + 1, 8, 1)
        for k in range(crossings):
            pl[-1 - k], championship[k] = championship[k], pl[-1 - k]
    return matches, quality


@pytest.mark.parametrize("teams", [0, 1, 2, 12])
@pytest.mark.parametrize("absorption", [(2.0, 0.0), (2.0, 0.0, 1.8, 0.0), (2.0, 0.0, 0.0, 0.0)])
def test_league_block_coordinates_invert(teams, absorption):
    transform, inverse = tilt_coordinates(teams, absorption)
    np.testing.assert_allclose(transform @ inverse, np.eye(len(transform)), atol=2e-15)
    assert len(transform) == len(absorption) + 2 * teams


def test_an_odd_league_block_is_rejected():
    with pytest.raises(ValueError, match="even number of slots"):
        tilt_coordinates(4, (2.0, 0.0, 1.0))


def test_a_map_that_amplifies_is_rejected():
    with pytest.raises(ValueError, match="compresses toward"):
        DivisionMap(1.4, 0.5, 0.07, 0.10).validated()


def test_a_nonpositive_slope_is_rejected():
    with pytest.raises(ValueError, match="must be positive"):
        DivisionMapPopulation(division_map=(0.0, 0.5, 0.07, 0.10))


def two_club_model(division_map, states, divisions):
    model = DivisionMapPopulation(division_map=division_map, independent_poisson=True)
    for index, (team, state) in enumerate(states.items()):
        model.team_index[team] = index
        model.mean = np.r_[model.mean, state]
        model.covariance = np.pad(model.covariance, ((0, 2), (0, 2)))
        model.covariance[-2:, -2:] = np.eye(2) * 0.04
    model.divisions = dict(divisions)
    return model


def test_the_map_moves_a_club_to_its_new_population_by_the_stated_slope():
    """Attack and defence are compressed toward the destination division's means."""
    states = {
        "top": np.array([0.30, 0.00]),
        "other": np.array([0.10, 0.00]),
        "mover": np.array([0.50, 0.00]),
        "rest": np.array([-0.10, 0.00]),
    }
    divisions = {"top": PL, "other": PL, "mover": CHAMPIONSHIP, "rest": CHAMPIONSHIP}
    model = two_club_model(DivisionMap(0.5, 0.5, 1e-9, 1e-9), states, divisions)
    model._map_state("mover", PL)
    source = np.mean([[0.50], [-0.10]])
    destination = np.mean([[0.30], [0.10]])
    expected = destination + 0.5 * (0.50 - source)
    np.testing.assert_allclose(model.mean[model._team_slice("mover")], [expected, 0.0], atol=1e-12)


def test_the_map_adds_the_residual_spread_it_cannot_predict():
    states = {"a": np.array([0.2, 0.0]), "b": np.array([-0.2, 0.0])}
    model = two_club_model(DivisionMap(0.5, 0.5, 0.3, 0.3), states, {"a": PL, "b": CHAMPIONSHIP})
    before = model.covariance[model._team_slice("b"), model._team_slice("b")].copy()
    model._map_state("b", PL)
    after = model.covariance[model._team_slice("b"), model._team_slice("b")]
    np.testing.assert_allclose(after, 0.25 * before + np.eye(2) * 0.045, atol=1e-12)


def test_a_unit_map_leaves_matched_populations_where_they_are():
    states = {"a": np.array([0.2, 0.05]), "b": np.array([0.2, 0.05])}
    model = two_club_model(IDENTITY, states, {"a": PL, "b": CHAMPIONSHIP})
    model._map_state("b", PL)
    np.testing.assert_allclose(model.mean[model._team_slice("b")], [0.2, 0.05], atol=1e-12)


def test_a_crossing_club_is_mapped_rather_than_carried():
    matches, _ = two_division_history(seed=6, compression=0.4)
    model = DivisionMapQualityTilt(independent_poisson=True).fit(matches, date(2021, 8, 1))
    assert model.crossings
    assert {row["to"] for row in model.crossings} == {PL, CHAMPIONSHIP}
    crossed = {row["team_id"] for row in model.crossings}
    sources = {source.source for (team, _), source in model.entry_priors.items() if team in crossed}
    assert "mapped across divisions" in sources
    assert model.division_summary()["mapped_crossings"] == len(model.crossings)


def test_the_map_shrinks_promoted_clubs_toward_their_new_population():
    matches, _ = two_division_history(seed=6, compression=0.4)
    cutoff = date(2021, 8, 1)
    carried = CrossDivisionQualityTilt(independent_poisson=True).fit(matches, cutoff)
    mapped = DivisionMapQualityTilt(independent_poisson=True).fit(matches, cutoff)
    season = "2020-2021"
    promoted = sorted(
        {
            row["team_id"]
            for row in mapped.crossings
            if row["to"] == PL and (row["team_id"], season) in mapped.entry_priors
        }
    )
    assert promoted
    spread = {
        name: float(np.std([model.entry_priors[team, season].mean[0] for team in promoted]))
        for name, model in (("carried", carried), ("mapped", mapped))
    }
    assert spread["mapped"] < spread["carried"]


def test_the_centered_coordinate_keeps_the_division_scoring_level_reachable():
    matches, _ = two_division_history(seed=3)
    model = DivisionMapQualityTilt(independent_poisson=True).fit(matches, date(2021, 8, 1))
    summary = model.division_summary()
    assert (
        abs(summary["championship_scoring_level"] - LEVEL)
        < 4 * (summary["championship_scoring_level_sd"])
    )
    assert abs(summary["home_advantage"] - HOME) < 4 * summary["home_advantage_sd"]
