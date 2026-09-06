import csv
import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from epl_forecast.cli import fitted_model
from epl_forecast.data import live as source
from epl_forecast.data.live import capture_snapshot, load_live_season, timestamp
from epl_forecast.data.normalize import TEAM_FILE
from epl_forecast.data.sources import SourceAccessError
from epl_forecast.live_forecast import check_freshness, export_forecast
from epl_forecast.storage import file_hash, write_json

OBSERVED = datetime(2020, 9, 2, 20, tzinfo=UTC)
SPEC = {"id": "M2", "kind": "attack_defense_poisson", "parameters": {}}
CONFIG = {
    "models": [SPEC],
    "train_window_days": 1095,
    "min_train_matches": 1,
    "competition_id": "eng-premier-league",
}


def refresh_hashes(directory):
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    for entry in manifest["files"]:
        entry["sha256"] = file_hash(directory / entry["name"])
        entry["bytes"] = (directory / entry["name"]).stat().st_size
    write_json(path, manifest)


def update_fixtures(directory, mutate):
    path = directory / "fpl_fixtures.json"
    rows = json.loads(path.read_text())
    mutate(rows)
    write_json(path, rows)
    refresh_hashes(directory)


@pytest.fixture
def live_snapshot(tmp_path):
    with TEAM_FILE.open(newline="") as stream:
        teams = list(csv.DictReader(stream))[:20]
    bootstrap = {
        "teams": [{"id": i + 1, "name": team["team_name"]} for i, team in enumerate(teams)],
        "events": [{"id": 1, "deadline_time": "2020-08-01T12:00:00Z"}],
    }
    fixtures = []
    for i, (home, away) in enumerate((h, a) for h in range(1, 21) for a in range(1, 21) if h != a):
        kickoff = datetime(2020, 9, 3, 14, tzinfo=UTC) + timedelta(days=i // 10)
        if i < 2:
            kickoff = datetime(2020, 9, 1 + i, 14, tzinfo=UTC)
        fixtures.append(
            {
                "id": i + 1,
                "event": i // 10 + 1,
                "kickoff_time": kickoff.isoformat(),
                "team_h": home,
                "team_a": away,
                "started": i < 2,
                "finished": i == 0,
                "finished_provisional": i < 2,
                "minutes": 90 if i < 2 else 0,
                "team_h_score": 2 if i < 2 else None,
                "team_a_score": 0 if i < 2 else None,
            }
        )
    write_json(tmp_path / "fpl_bootstrap.json", bootstrap)
    write_json(tmp_path / "fpl_fixtures.json", fixtures)
    manifest = {
        "schema_version": 1,
        "season_id": "2020-2021",
        "started_at": (OBSERVED - timedelta(seconds=2)).isoformat(),
        "completed_at": OBSERVED.isoformat(),
        "files": [
            {"name": name, "retrieved_at": (OBSERVED - timedelta(seconds=1)).isoformat()}
            for name in ("fpl_bootstrap.json", "fpl_fixtures.json")
        ],
        "errors": [],
    }
    write_json(tmp_path / "manifest.json", manifest)
    refresh_hashes(tmp_path)
    return tmp_path


def test_capture_keeps_raw_bytes_and_partial_failures(tmp_path, monkeypatch):
    def fake_download(url):
        if url.endswith("fixtures.csv"):
            raise SourceAccessError("HTTP 503")
        payload = b'{"raw": "unchanged bytes"}\n'
        return payload, {"retrieved_at": datetime.now(UTC).isoformat(), "url": url}

    monkeypatch.setattr(source, "download", fake_download)
    first = capture_snapshot(tmp_path, 2026)
    second = capture_snapshot(tmp_path, 2026)
    assert first != second
    manifest = json.loads((first / "manifest.json").read_text())
    assert len(manifest["files"]) == 4
    assert manifest["errors"][0]["name"] == "football_data_fixtures.csv"
    assert (first / "fpl_bootstrap.json").read_bytes() == b'{"raw": "unchanged bytes"}\n'


def test_live_completion_and_same_day_fit_isolation(live_snapshot):
    live = load_live_season(live_snapshot)
    assert len(live.played) == 2
    assert len(live.remaining) == 378
    assert live.details[live.played[1].fixture.match_id]["status"] == "finished_provisional"
    first, _, training = fitted_model(live.played, CONFIG, "M2", OBSERVED.date())
    assert len(training) == 1
    update_fixtures(live_snapshot, lambda rows: rows[1].update(team_h_score=99, team_a_score=88))
    second_live = load_live_season(live_snapshot)
    second, _, _ = fitted_model(second_live.played, CONFIG, "M2", OBSERVED.date())
    assert np.array_equal(first.attack, second.attack)
    assert np.array_equal(first.defense, second.defense)


def test_future_score_labels_do_not_enter_live_inputs(live_snapshot):
    first = load_live_season(live_snapshot)
    update_fixtures(live_snapshot, lambda rows: rows[-1].update(team_h_score=99, team_a_score=99))
    second = load_live_season(live_snapshot)
    assert first.remaining == second.remaining
    assert [(m.home_goals, m.away_goals) for m in first.played] == [
        (m.home_goals, m.away_goals) for m in second.played
    ]
    assert all(
        row["home_goals"] is None for row in second.details.values() if row["status"] == "scheduled"
    )


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda rows: rows.pop(), "380"),
        (lambda rows: rows.append(rows[0]), "Duplicate"),
        (lambda rows: rows[-1].update(team_h=100), "outside this season"),
        (lambda rows: rows[-1].update(finished=True, started=True), "inconsistent kickoff"),
        (lambda rows: rows[1].update(minutes=60), "fewer than 90"),
    ],
)
def test_invalid_live_schedules_fail(live_snapshot, mutation, error):
    update_fixtures(live_snapshot, mutation)
    with pytest.raises(ValueError, match=error):
        load_live_season(live_snapshot)


def test_unknown_dates_and_postponements_keep_stable_ids(live_snapshot):
    before = load_live_season(live_snapshot)
    update_fixtures(live_snapshot, lambda rows: rows[-1].update(kickoff_time=None, event=None))
    after = load_live_season(live_snapshot)
    assert before.remaining[-1].match_id == after.remaining[-1].match_id
    detail = after.details[after.remaining[-1].match_id]
    assert detail["kickoff_time"] is None
    assert detail["status"] == "unscheduled"
    update_fixtures(
        live_snapshot,
        lambda rows: rows[-1].update(kickoff_time="2020-09-01T14:00:00Z", event=None),
    )
    assert load_live_season(live_snapshot).remaining[-1].match_date == OBSERVED.date()


def test_snapshot_corruption_and_season_mismatch(live_snapshot):
    path = live_snapshot / "fpl_bootstrap.json"
    bootstrap = json.loads(path.read_text())
    bootstrap["events"][0]["deadline_time"] = "2021-08-01T12:00:00Z"
    write_json(path, bootstrap)
    with pytest.raises(ValueError, match="checksum"):
        load_live_season(live_snapshot)
    refresh_hashes(live_snapshot)
    with pytest.raises(ValueError, match="season differs"):
        load_live_season(live_snapshot)


def test_cross_source_disagreements_fail(live_snapshot):
    manifest = json.loads((live_snapshot / "manifest.json").read_text())
    path = live_snapshot / "football_data_E0.csv"
    path.write_text(
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,01/09/2020,Arsenal,Aston Villa,2,0,H\n"
    )
    manifest["files"].append(
        {"name": path.name, "retrieved_at": (OBSERVED - timedelta(seconds=1)).isoformat()}
    )
    write_json(live_snapshot / "manifest.json", manifest)
    refresh_hashes(live_snapshot)
    assert load_live_season(live_snapshot).results_crosschecked == 1
    path.write_text(path.read_text().replace("2,0,H", "0,0,D"))
    refresh_hashes(live_snapshot)
    with pytest.raises(ValueError, match="result conflict"):
        load_live_season(live_snapshot)


def test_export_fixes_today_results_and_archives_future_matches(live_snapshot, monkeypatch):
    from epl_forecast import live_forecast

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return OBSERVED + timedelta(minutes=5)

    monkeypatch.setattr(live_forecast, "datetime", Clock)
    live = load_live_season(live_snapshot)
    check_freshness(live, 24)
    model, _, training = fitted_model(live.played, CONFIG, "M2", OBSERVED.date())
    output = live_snapshot / "forecast"
    forecast = export_forecast(live, model, training, {"model": SPEC}, output, 100, 42, 7, [])
    simulation = forecast["simulation"]
    assert simulation["played_matches"] == 2
    assert (
        next(row for row in simulation["teams"] if row["team_id"] == "arsenal")["current_points"]
        == 6
    )
    assert sum(row["played"] for row in simulation["teams"]) == 4
    assert sum(row["title_probability"] for row in simulation["teams"]) == pytest.approx(1)
    assert sum(row["relegation_probability"] for row in simulation["teams"]) == pytest.approx(3)
    archive = json.loads((output / "archive.json").read_text())
    assert len(archive["forward_match_ids"]) == 378
    for name, digest in archive["files"].items():
        assert file_hash(output / name) == digest
    for row in forecast["matches"]:
        distribution = row["score_distribution"]
        assert sum(row[key] for key in ("p_home", "p_draw", "p_away")) == pytest.approx(1)
        assert np.sum(distribution["grid_home_rows_away_columns"]) + distribution[
            "omitted_probability"
        ] == pytest.approx(1)
    with pytest.raises(ValueError, match="not empty"):
        export_forecast(live, model, training, {"model": SPEC}, output, 100, 42, 7, [])


def test_in_progress_games_withhold_season_projection(live_snapshot):
    update_fixtures(
        live_snapshot,
        lambda rows: rows[2].update(started=True, kickoff_time="2020-09-02T19:00:00Z", minutes=60),
    )
    live = load_live_season(live_snapshot)
    model, _, training = fitted_model(live.played, CONFIG, "M2", OBSERVED.date())
    result = export_forecast(
        live, model, training, {"model": SPEC}, live_snapshot / "forecast", 100, 42, 5, []
    )
    assert result["simulation"] is None
    assert len(result["matches"]) == 377
    assert len(result["fixtures_awaiting_results"]) == 1
    archive = json.loads((live_snapshot / "forecast/archive.json").read_text())
    assert archive["forward_match_ids"] == []


def test_stale_and_naive_timestamps_fail(live_snapshot):
    with pytest.raises(ValueError, match="timezone"):
        timestamp("2020-09-02T20:00:00")
    with pytest.raises(ValueError, match="hours old"):
        check_freshness(load_live_season(live_snapshot), 24)


def test_dynamic_live_export_includes_uncertainty_and_posterior_simulation(live_snapshot):
    from epl_forecast.models.dynamic import DynamicAttackDefense

    live = load_live_season(live_snapshot)
    training = [m for m in live.played if m.available_on <= OBSERVED.date()]
    model = DynamicAttackDefense().fit(training, OBSERVED.date())
    output = live_snapshot / "dynamic-forecast"
    result = export_forecast(
        live,
        model,
        training,
        {"model": {"id": "M4", "kind": "dynamic_attack_defense"}},
        output,
        80,
        42,
        7,
        [],
    )
    assert result["state_uncertainty"] == "posterior"
    assert result["simulation"]["state_uncertainty"] == "posterior"
    assert all(t["attack_sd"] > 0 and t["defense_sd"] > 0 for t in result["team_strengths"])
    assert "uncertainty in current team strength" in (output / "index.html").read_text()
    assert "Clubs without PL history start at 1" not in (output / "index.html").read_text()
    assert result["simulation"]["played_matches"] == 2
