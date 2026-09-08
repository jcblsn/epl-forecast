import json
from datetime import UTC, datetime

import pytest

from epl_forecast.datasets import publish
from epl_forecast.research.readiness import freeze_research, frozen_dataset


def test_freeze_pins_publications_and_preserves_actual_information_cutoff(tmp_path):
    root = tmp_path / "data"
    request = {
        "provider": "football_data",
        "retrieved_at": "2026-09-08T12:00:00+00:00",
        "evidence_basis": "retrospective",
        "source_sha256": "a" * 64,
        "context": {},
    }
    fixture = {
        "match_id": "eng-premier-league:2025-2026:a:b",
        "competition_id": "eng-premier-league",
        "season_id": "2025-2026",
        "home_team_id": "a",
        "away_team_id": "b",
        "match_date": "2025-08-01",
        "status": "finished",
        "stage": "regular",
        "home_goals": 1,
        "away_goals": 0,
    }
    publish(root, request, {"fixtures": [fixture]})
    destination = tmp_path / "research.json"
    report = freeze_research(root, destination)
    assert report["readiness"]["eligible_cohorts"] == {}
    assert report["readiness"]["cohorts"][0]["valid_matches"]["xg"] == []
    publish(
        root,
        {**request, "retrieved_at": "2026-09-08T13:00:00+00:00"},
        {"fixtures": [{**fixture, "home_goals": 5}]},
    )
    frozen = frozen_dataset(root, destination)
    assert frozen.matches()[0].home_goals == 1
    frozen.close()
    historical = frozen_dataset(root, destination, datetime(2025, 8, 2, tzinfo=UTC))
    assert historical.matches() == []
    historical.close()
    with pytest.raises(ValueError, match="immutable"):
        freeze_research(root, destination)
    modified = json.loads(destination.read_text())
    modified["canonical_manifests"][0]["request"]["retrieved_at"] = "2025-08-01T00:00:00+00:00"
    destination.write_text(json.dumps(modified))
    with pytest.raises(ValueError, match="checksum"):
        frozen_dataset(root, destination)


def test_full_season_requires_complete_xg_but_process_uses_explicit_cases(tmp_path):
    request = {
        "provider": "football_data",
        "retrieved_at": "2026-09-08T12:00:00+00:00",
        "evidence_basis": "retrospective",
        "source_sha256": "a" * 64,
        "context": {},
    }
    fixtures, process = [], []
    teams = [f"t{i}" for i in range(20)]
    for h in teams:
        for a in teams:
            if h == a:
                continue
            mid = f"{h}-{a}"
            fixtures.append(
                {
                    "match_id": mid,
                    "competition_id": "eng-premier-league",
                    "season_id": "2025-2026",
                    "home_team_id": h,
                    "away_team_id": a,
                    "match_date": "2025-08-01",
                    "status": "finished",
                    "stage": "regular",
                    "home_goals": 1,
                    "away_goals": 0,
                }
            )
            process.extend(
                {
                    "match_id": mid,
                    "team_id": t,
                    "competition_id": "eng-premier-league",
                    "season_id": "2025-2026",
                    "shots": 10,
                    "shots_on_target": 4,
                }
                for t in (h, a)
            )
    process[0]["shots"] = process[0]["shots_on_target"] = None
    publish(tmp_path / "data", request, {"fixtures": fixtures, "team_process": process})
    report = freeze_research(tmp_path / "data", tmp_path / "freeze.json")["readiness"]
    cohort = ["eng-premier-league", "2025-2026"]
    assert report["eligible_cohorts"]["goals_information"] == [cohort]
    assert report["eligible_cohorts"]["process_information_complete_cases"] == [cohort]
    assert "matched_uncertainty_ladder" not in report["eligible_cohorts"]
    assert len(report["cohorts"][0]["valid_matches"]["shots"]) == 379
    assert any(
        r["match_id"] == "t0-t1" and r["signal"] == "shots" for r in report["signal_exclusions"]
    )
