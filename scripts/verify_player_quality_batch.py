"""Audit retained M6 forecasts, comparison coverage and timestamped availability evidence."""

import csv
import gzip
import json
import tarfile
from hashlib import sha256
from pathlib import Path

import numpy as np

from epl_forecast.data.live import timestamp
from epl_forecast.storage import file_hash, write_json


def main():
    root = Path("docs/experiments/m6_quality")
    payload = gzip.decompress((root / "live_forecast.json.gz").read_bytes())
    forecast = json.loads(payload)
    archive = json.loads((root / "live_archive.json").read_text())
    run = json.loads((root / "live_run.json").read_text())
    with tarfile.open(root / "live_snapshot.tar.gz") as bundle:
        manifest = json.load(bundle.extractfile("manifest.json"))
        for entry in manifest["files"]:
            assert sha256(bundle.extractfile(entry["name"]).read()).hexdigest() == entry["sha256"]
    assert (
        file_hash(root / "live_player_matches.csv.gz")
        == run["inputs"]["runs/m6-quality-player-capture/player_matches.csv.gz"]
    )
    assert sha256(payload).hexdigest() == archive["files"]["forecast.json"]
    assert len(forecast["matches"]) == len(archive["forward_match_ids"]) == 350
    assert {r["match_id"] for r in forecast["matches"]} == set(archive["forward_match_ids"])
    assert all(
        timestamp(r["kickoff_time"]) > timestamp(archive["archived_at"])
        for r in forecast["matches"]
    )
    assert timestamp(forecast["state_observed_at"]) <= timestamp(archive["archived_at"])
    for row in forecast["matches"]:
        assert abs(sum(row[k] for k in ("p_home", "p_draw", "p_away")) - 1) < 1e-10
        assert len(row["player_quality"]) == 2
        for team in row["player_quality"]:
            assert team["lineup_selection_quality_sd"] > 0
            for specification in team["specifications"]:
                assert (
                    abs(sum(p["expected_minutes"] for p in specification["players"]) - 990) < 1e-7
                )
    simulation = forecast["simulation"]
    assert simulation["remaining_matches"] == 350 and simulation["played_matches"] == 30
    assert simulation["simulations"] == 2000 and len(simulation["teams"]) == 20
    direct = {r["match_id"]: r for r in forecast["matches"]}
    z = []
    for row in simulation["match_frequencies"]:
        for key in ("p_home", "p_draw", "p_away"):
            p = direct[row["match_id"]][key]
            z.append(abs(row[key] - p) / np.sqrt(p * (1 - p) / simulation["simulations"]))
    assert len(z) == 1050 and np.mean(np.array(z) < 3) > 0.99
    predictions = list(csv.DictReader((root / "predictions.csv").open()))
    regimes = {r["regime"] for r in predictions}
    assert regimes == {"M5_team_only", "M6_deployable", "M6_oracle_diagnostic"}
    assert len(predictions) == 1140
    for regime in regimes:
        rows = [r for r in predictions if r["regime"] == regime]
        assert len({r["match_id"] for r in rows}) == 380
        if "oracle" in regime:
            assert all(r["deployable"] == "False" for r in rows)
    scenario = json.loads((root / "availability_scenario.json").read_text())
    response = json.loads((root / "response.json").read_text())
    assert len(scenario["restored_minus_current_season"]) == 20
    assert scenario["availability"]["probability"] == 0
    assert any(not r["expired"] for r in scenario["matches"])
    assert any(r["expired"] for r in scenario["matches"])
    assert all(
        max(abs(v) for v in r["restored_minus_current"].values()) == 0
        for r in scenario["matches"]
        if r["expired"]
    )
    stress = next(r for r in response["summary"] if r["case"] == "five_player_stress")
    assert stress["mean_probability_change"][0] < -0.02
    reference = json.loads((root / "posterior_reference.json").read_text())
    assert len(reference["matches"]) == 60 and len(reference["players"]) == 424
    assert reference["diagnostics"]["divergences"] == 0
    assert reference["diagnostics"]["max_rhat"] < 1.01
    report = {
        "forecast_archive_sha256_verified": True,
        "snapshot_and_player_input_hashes_verified": True,
        "prospective_match_count": 350,
        "archive_completed_at": archive["archived_at"],
        "chronological_matches_per_regime": 380,
        "season_paths": 2000,
        "joint_player_reference": reference["diagnostics"],
        "match_path_agreement_fraction_within_three_se": float(np.mean(np.array(z) < 3)),
        "match_path_agreement_max_se": max(z),
        "expiring_current_absence": {
            "player": scenario["player_name"],
            "source": scenario["availability"]["source"],
        },
        "five_player_stress_home_probability_change": stress["mean_probability_change"][0],
        "inputs": {
            p.name: file_hash(p) for p in sorted(root.iterdir()) if p.name != "verification.json"
        },
    }
    write_json(root / "verification.json", report)
    print("Verified M6 batch artifacts", flush=True)


if __name__ == "__main__":
    main()
