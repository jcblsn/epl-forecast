from datetime import date

import pytest

from epl_forecast.schema import Fixture, Match, fixture_id
from epl_forecast.training import training_matches


def matches():
    rows = []
    for competition in ("eng-premier-league", "eng-championship", "eng-league-one"):
        fixture = Fixture(
            fixture_id(competition, "2025-2026", "a", "b"),
            competition,
            "2025-2026",
            date(2025, 9, 1),
            "a",
            "b",
        )
        rows.append(Match(fixture, 1, 0))
    return rows


def test_a_per_division_table_selects_each_division_training_set():
    spec = {
        "train_window_days": 0,
        "train_competitions": {
            "eng-championship": ["eng-premier-league", "eng-championship"],
            "eng-league-one": ["eng-championship", "eng-league-one"],
        },
    }
    selected = {}
    for competition in ("eng-championship", "eng-league-one"):
        config = {"competition_id": competition, "train_window_days": 0, "min_train_matches": 1}
        rows = training_matches(matches(), config, spec, date(2026, 1, 1))
        selected[competition] = {m.fixture.competition_id for m in rows}
    assert selected == {
        "eng-championship": {"eng-premier-league", "eng-championship"},
        "eng-league-one": {"eng-championship", "eng-league-one"},
    }
    config = {"competition_id": "eng-league-two", "train_window_days": 0, "min_train_matches": 1}
    with pytest.raises(ValueError, match="include the forecast competition"):
        training_matches(matches(), config, spec, date(2026, 1, 1))
