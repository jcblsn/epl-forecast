from types import SimpleNamespace

from epl_forecast.data import collect
from epl_forecast.data.capture import QuotaReached


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
