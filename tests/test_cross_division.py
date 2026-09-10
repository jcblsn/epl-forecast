from datetime import date

import numpy as np
import pytest

from epl_forecast.models.cross_division import CrossDivisionQualityTilt
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


def test_the_filter_recovers_a_known_division_level_and_home_advantage():
    matches, _ = two_division_history(seed=3)
    model = CrossDivisionQualityTilt().fit(matches, date(2021, 8, 1))
    summary = model.division_summary()
    assert abs(summary["championship_level"] - LEVEL) < 3 * summary["championship_level_sd"]
    assert abs(summary["home_advantage"] - HOME) < 3 * summary["home_advantage_sd"]


def test_observed_transitions_sharpen_the_division_level():
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
    assert lower == pytest.approx(top + model.division_level + [model.division_home_advantage, 0])


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
