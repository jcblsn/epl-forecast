from types import SimpleNamespace

from epl_forecast.data import collect
from epl_forecast.data.capture import QuotaReached
from epl_forecast.datasets import publish


def test_recent_player_histories_precede_older_seasons(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        collect, "Fetcher", lambda root, reserve: SimpleNamespace(root=root, records=[])
    )
    monkeypatch.setattr(collect.api, "preflight", lambda fetcher: {})
    monkeypatch.setattr(collect, "recent_readiness", lambda root, end: {})
    monkeypatch.setattr(
        collect, "prioritized_players", lambda root, start, end: [{"api_id": start}]
    )

    def request(fetcher, endpoint, params=None, **kwargs):
        calls.append((endpoint, params))
        if endpoint == "teams" and params["season"] == 2022:
            raise QuotaReached("End the test at the first older-season request")
        if endpoint == "leagues":
            return {
                "response": [
                    {
                        "seasons": [
                            {
                                "year": year,
                                "coverage": {
                                    "fixtures": {"lineups": False, "statistics_players": False},
                                    "injuries": False,
                                },
                            }
                            for year in range(2022, 2027)
                        ]
                    }
                ]
            }
        if endpoint == "players":
            return {"response": [], "paging": {"current": 1, "total": 1}}
        return {"response": []}

    monkeypatch.setattr(collect, "normalized_request", request)
    report = collect.backfill(tmp_path, start=2022, end=2026)
    assert report["status"] == "paused"
    assert report["current_api_complete"] and report["recent_api_complete"]
    current_history = calls.index(("sidelined", {"player": 2026}))
    for league in (39, 40):
        assert calls.index(("teams", {"league": league, "season": 2026})) < current_history
        assert current_history < calls.index(("teams", {"league": league, "season": 2025}))
    recent_history = calls.index(("sidelined", {"player": 2023}))
    assert recent_history < calls.index(("teams", {"league": 39, "season": 2022}))


def evidence(endpoint=None, player=None):
    context = {}
    if endpoint is not None:
        context["endpoint"] = endpoint
    if player is not None:
        context["player"] = player
    return {
        "provider": "api_football",
        "retrieved_at": "2026-09-08T12:00:00+00:00",
        "evidence_basis": "retrospective",
        "source_sha256": f"{endpoint}{player}".ljust(64, "a"),
        "context": context,
    }


def readiness_fixture(home, away, home_starters, away_starters, season="2026-2027"):
    competition = "eng-premier-league"
    match_id = f"{competition}:{season}:{home}:{away}"
    common = {"match_id": match_id, "competition_id": competition, "season_id": season}
    appearances = [
        {
            **common,
            "player_id": f"p{team}{index}",
            "team_id": team,
            "starts": 1,
            "minutes": 90 if index < usable else None,
        }
        for team, count, usable in ((home, *home_starters), (away, *away_starters))
        for index in range(count)
    ]
    return {
        "fixtures": [
            {
                **common,
                "stage": "regular",
                "status": "finished",
                "home_team_id": home,
                "away_team_id": away,
                "match_date": "2026-08-15",
                "home_goals": 1,
                "away_goals": 0,
            }
        ],
        "appearances": appearances,
        "players": [
            {"player_id": r["player_id"], "api_id": index, "name": f"Player {index}"}
            for index, r in enumerate(appearances, start=1)
        ],
    }


def test_readiness_requires_eleven_usable_starters_for_each_team(tmp_path):
    publish(tmp_path, evidence(), readiness_fixture("a", "b", (12, 12), (10, 10)))
    publish(tmp_path, evidence(), readiness_fixture("c", "d", (11, 10), (11, 11)))
    publish(tmp_path, evidence(), readiness_fixture("e", "f", (11, 11), (11, 11)))
    report = collect.recent_readiness(tmp_path, 2026)
    assert report["incomplete_starting_lineups"] == 2
    incomplete = {r["match_id"] for r in report["incomplete_starting_lineup_detail"]}
    assert incomplete == {
        "eng-premier-league:2026-2027:a:b",
        "eng-premier-league:2026-2027:c:d",
    }
    current = next(
        r
        for r in report["seasons"]
        if r["season_id"] == "2026-2027" and r["competition_id"] == "eng-premier-league"
    )
    assert current["finished"] == 3 and current["finished_with_starter_minutes"] == 1
    assert not report["ready_for_player_experiments"]


def test_pending_player_histories_use_set_differences(tmp_path, monkeypatch):
    publish(tmp_path, evidence(), readiness_fixture("a", "b", (11, 11), (11, 11)))
    for player in (7, 8, 999):
        publish(tmp_path, evidence("transfers", player), {})
    publish(tmp_path, evidence("sidelined", 7), {})
    monkeypatch.setattr(
        collect,
        "prioritized_players",
        lambda root, start, end: [{"api_id": api_id} for api_id in (7, 8, 9)],
    )
    report = collect.recent_readiness(tmp_path, 2026)
    assert report["current_players"] == 3
    assert report["pending_current_player_histories"] == {"transfers": 1, "sidelined": 2}


def test_archive_audit_separates_uncovered_seasons_from_defective_captures(tmp_path):
    publish(tmp_path, evidence(), readiness_fixture("a", "b", (11, 11), (11, 11)))
    publish(tmp_path, evidence(), readiness_fixture("c", "d", (11, 0), (11, 11)))
    uncovered = readiness_fixture("e", "f", (0, 0), (0, 0))
    uncovered["appearances"] = []
    uncovered["players"] = []
    publish(tmp_path, evidence(), uncovered)
    report = collect.audit(tmp_path)["incomplete_starting_lineups"]
    assert report["fixtures"] == 2
    assert report["by_season"] == {
        "eng-premier-league/2026-2027": {"fixtures": 2, "without_any_appearance": 1}
    }
    assert [r["match_id"] for r in report["examples"]] == ["eng-premier-league:2026-2027:c:d"]
