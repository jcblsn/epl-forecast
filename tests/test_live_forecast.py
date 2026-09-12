from epl_forecast.live_forecast import flatten_rows


def test_flatten_rows_removes_optional_nested_fields_from_every_row():
    rows, fields = flatten_rows(
        [
            {"match_id": "a", "probabilities": {"home": 0.5}, "price": 2},
            {"match_id": "b", "probabilities": None, "price": None},
        ]
    )
    assert fields == ["match_id", "price"]
    assert rows == [{"match_id": "a", "price": 2}, {"match_id": "b", "price": None}]


def test_a_postponed_fixture_waits_on_the_cutoff_day(tmp_path):
    from datetime import UTC, date, datetime

    from epl_forecast.datasets import publish
    from epl_forecast.live import load_live_season

    def fixture(home, away, status, day, goals=None):
        return {
            "match_id": f"eng-league-one:2026-2027:{home}:{away}",
            "competition_id": "eng-league-one",
            "season_id": "2026-2027",
            "stage": "regular",
            "home_team_id": home,
            "away_team_id": away,
            "match_date": day,
            "kickoff_time": f"{day}T14:00:00+00:00",
            "status": status,
            "home_goals": goals,
            "away_goals": 0 if goals is not None else None,
        }

    evidence = {
        "provider": "api_football",
        "retrieved_at": "2026-09-10T10:00:00+00:00",
        "evidence_basis": "captured",
        "source_sha256": "a" * 64,
        "context": {"endpoint": "fixtures"},
    }
    rows = [
        fixture("oxford-united", "reading", "postponed", "2026-09-08"),
        fixture("reading", "oxford-united", "finished", "2026-08-15", goals=1),
    ]
    publish(tmp_path, evidence, {"fixtures": rows})
    cutoff = datetime(2026, 9, 11, 12, tzinfo=UTC)
    live = load_live_season(tmp_path, cutoff, "eng-league-one", "2026-2027")
    (waiting,) = live.remaining
    assert waiting.match_date == date(2026, 9, 11)
    assert live.details[waiting.match_id]["status"] == "unscheduled"
    assert len(live.played) == 1


def test_a_match_that_started_without_a_result_waits_on_the_cutoff_day(tmp_path):
    """An overdue match keeps the season simulable; its own date is already past."""
    from datetime import UTC, date, datetime

    from epl_forecast.datasets import publish
    from epl_forecast.live import load_live_season

    def fixture(home, away, status, day, goals=None):
        return {
            "match_id": f"eng-league-one:2026-2027:{home}:{away}",
            "competition_id": "eng-league-one",
            "season_id": "2026-2027",
            "stage": "regular",
            "home_team_id": home,
            "away_team_id": away,
            "match_date": day,
            "kickoff_time": f"{day}T14:00:00+00:00",
            "status": status,
            "home_goals": goals,
            "away_goals": 0 if goals is not None else None,
        }

    evidence = {
        "provider": "api_football",
        "retrieved_at": "2026-09-10T10:00:00+00:00",
        "evidence_basis": "captured",
        "source_sha256": "a" * 64,
        "context": {"endpoint": "fixtures"},
    }
    rows = [
        fixture("oxford-united", "reading", "in_progress", "2026-09-10"),
        fixture("reading", "oxford-united", "finished", "2026-08-15", goals=1),
    ]
    publish(tmp_path, evidence, {"fixtures": rows})
    live = load_live_season(
        tmp_path, datetime(2026, 9, 11, 12, tzinfo=UTC), "eng-league-one", "2026-2027"
    )
    (waiting,) = live.remaining
    assert waiting.match_date == date(2026, 9, 11)
    assert live.details[waiting.match_id]["match_date"] == "2026-09-10"
    assert live.details[waiting.match_id]["status"] == "in_progress"
