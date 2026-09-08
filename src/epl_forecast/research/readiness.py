"""Experiment-specific eligibility over a frozen canonical publication snapshot."""

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from epl_forecast.artifacts import execution_provenance
from epl_forecast.data.collect import (
    captured_player_histories,
    identity_contradictions,
    incomplete_lineup,
    starter_counts,
)
from epl_forecast.data.rules import reviewed_rules_evidence
from epl_forecast.datasets import Dataset
from epl_forecast.storage import json_bytes, sha256_bytes, write_immutable


def player_evidence_audit(data, fixtures, contradictions):
    appearances = defaultdict(list)
    process = defaultdict(list)
    for row in data.rows("SELECT * FROM appearances"):
        appearances[row["match_id"]].append(row)
    for row in data.rows("SELECT * FROM player_process"):
        process[row["match_id"]].append(row)
    collisions = {r["match_id"] for r in contradictions["same_team_name_collisions"]}
    valid, exclusions = [], []
    for fixture in fixtures:
        if fixture["status"] != "finished":
            continue
        mid = fixture["match_id"]
        rows = process[mid]
        reasons = []
        if mid in collisions:
            reasons.append("unresolved same-team identity collision")
        if not rows:
            reasons.append("no player-process capture")
        else:
            expected = {fixture["home_team_id"], fixture["away_team_id"]}
            if {r["team_id"] for r in rows} != expected:
                reasons.append("player-process team set does not match fixture")
            if any(r["player_id"] is None for r in rows):
                reasons.append("unlinked player-process identity")
            keys = [(r["team_id"], r["player_id"]) for r in rows if r["player_id"] is not None]
            if len(keys) != len(set(keys)):
                reasons.append("multiple process records share a canonical player")
            if any(r["minutes"] is None or r["minutes"] < 0 for r in rows):
                reasons.append("unknown or invalid process exposure")
            if any(r["xg"] is None or r["shots"] is None for r in rows):
                reasons.append("missing attacking-process observations")
            active = {
                (r["team_id"], r["player_id"])
                for r in appearances[mid]
                if r["minutes"] is not None and (r["minutes"] > 0 or r["starts"] == 1)
            }
            observed = {
                (r["team_id"], r["player_id"])
                for r in rows
                if r["minutes"] is not None and r["minutes"] > 0
            }
            if not active or active != observed:
                reasons.append("positive-exposure identities disagree across providers")
        if reasons:
            exclusions.append({"match_id": mid, "reasons": sorted(set(reasons))})
        else:
            valid.append(mid)
    return {
        "valid_matches": sorted(valid),
        "exclusions": exclusions,
        "captured_fixtures": sum(bool(process[f["match_id"]]) for f in fixtures),
        "scope": "Necessary identity/exposure checks only; intersect with starter_minutes and team xG. Provider minute totals remain separate measurements. This is not sufficient model, allocation-likelihood, or strict-replay readiness.",
    }


def research_readiness(data: Dataset, start: int = 2013, end: int = 2026) -> dict:
    if start > end:
        raise ValueError("Research window start must not exceed end")
    cohorts = {}
    fixture_groups = defaultdict(list)
    exclusions = []
    signals = {
        (r["match_id"], r["team_id"], r["provider"]): r
        for r in data.rows("SELECT * FROM team_process")
    }
    counts = starter_counts(data)
    fixtures = [
        f
        for f in data.fixtures()
        if start <= int(f["season_id"][:4]) <= end and f["stage"] == "regular"
    ]
    for f in fixtures:
        key = f["competition_id"], f["season_id"]
        fixture_groups[key].append(f)
        cohort = cohorts.setdefault(
            key,
            {
                "competition_id": key[0],
                "season_id": key[1],
                "scheduled": 0,
                "finished": 0,
                "valid_matches": {
                    s: [] for s in ("goals", "xg", "shots", "shots_on_target", "starter_minutes")
                },
            },
        )
        cohort["scheduled"] += 1
        if f["status"] != "finished":
            continue
        cohort["finished"] += 1
        cohort["valid_matches"]["goals"].append(f["match_id"])
        for signal in ("xg", "shots", "shots_on_target"):
            provider = "understat" if signal == "xg" else "football_data"
            rows = [
                signals.get((f["match_id"], t, provider), {})
                for t in (f["home_team_id"], f["away_team_id"])
            ]
            valid = all(r.get(signal) is not None for r in rows)
            if signal != "xg" and int(f["season_id"][:4]) < 2013:
                valid = False
            if valid:
                cohort["valid_matches"][signal].append(f["match_id"])
            else:
                exclusions.append(
                    {
                        "match_id": f["match_id"],
                        "signal": signal,
                        "reason": "unavailable or outside reviewed provider coding window",
                    }
                )
        if incomplete_lineup(counts, f) is None:
            cohort["valid_matches"]["starter_minutes"].append(f["match_id"])
    histories = captured_player_histories(data.manifests)
    recent_start = f"{end - 3}-{end - 2}"
    people = data.rows(
        "WITH population AS (SELECT player_id, season_id FROM memberships UNION "
        "SELECT player_id, season_id FROM appearances) "
        "SELECT DISTINCT p.api_id FROM players p JOIN population USING(player_id) "
        "WHERE season_id>=? AND season_id<=? AND p.api_id IS NOT NULL",
        [recent_start, f"{end}-{end + 1}"],
    )
    ids = {p["api_id"] for p in people}
    missing = {endpoint: sorted(ids - captured) for endpoint, captured in histories.items()}
    contradictions = identity_contradictions(data)
    player_audit = player_evidence_audit(data, fixtures, contradictions)
    contradictions["same_team_name_collisions"] = [
        r
        for r in contradictions["same_team_name_collisions"]
        if recent_start <= r["season_id"] <= f"{end}-{end + 1}"
    ]
    player_ids = set(player_audit["valid_matches"])
    for cohort in cohorts.values():
        cohort["valid_matches"]["player_oracle_evidence"] = sorted(
            player_ids
            & set(cohort["valid_matches"]["starter_minutes"])
            & set(cohort["valid_matches"]["xg"])
        )
    experiments = defaultdict(list)
    for key, cohort in sorted(cohorts.items()):
        expected = {"eng-premier-league": 380, "eng-championship": 552}.get(key[0])
        participants = {
            t for f in fixture_groups[key] for t in (f["home_team_id"], f["away_team_id"])
        }
        pairs = [(f["home_team_id"], f["away_team_id"]) for f in fixture_groups[key]]
        expected_pairs = {(h, a) for h in participants for a in participants if h != a}
        complete = (
            expected is not None
            and cohort["scheduled"] == cohort["finished"] == expected
            and len(expected_pairs) == expected
            and len(set(pairs)) == expected
            and set(pairs) == expected_pairs
        )
        cohort["complete_season"] = complete
        for matches in cohort["valid_matches"].values():
            matches.sort()
        if complete:
            experiments["goals_information"].append(list(key))
            if key[0] == "eng-premier-league" and len(cohort["valid_matches"]["xg"]) == expected:
                experiments["matched_uncertainty_ladder"].append(list(key))
                experiments["xg_information"].append(list(key))
            if cohort["valid_matches"]["shots"] and cohort["valid_matches"]["shots_on_target"]:
                experiments["process_information_complete_cases"].append(list(key))
                experiments["promotion_transition_inputs"].append(list(key))
    return {
        "window": {"start": start, "end": end, "recent_player_start": end - 3},
        "cohorts": list(cohorts.values()),
        "signal_exclusions": exclusions,
        "eligible_cohorts": dict(experiments),
        "recent_player_population": len(ids),
        "missing_recent_player_histories": missing,
        "identity_contradictions": contradictions,
        "player_evidence_audit": player_audit,
        "roster_experiment_ready": False,
        "roster_gate": "History capture coverage alone cannot establish historical squad turnover available before kickoff; retrospective and strict-replay designs need separate validation.",
        "player_oracle_ready": False,
        "player_gate": "Requires team-sensor results, explicit defective-fixture/identity exclusions, and matched known-exposure versus forecast-exposure cohorts.",
        "championship_rules_evidence": reviewed_rules_evidence(
            "eng-championship", f"{end}-{end + 1}"
        ),
        "championship_season_evidence_ready": reviewed_rules_evidence(
            "eng-championship", f"{end}-{end + 1}"
        )
        is not None,
        "championship_gate": "Ready only for regular-season ranks with explicit unresolved disciplinary-tie uncertainty when the named edition has reviewed evidence. Playoff tournament/promotion-win probabilities are not admitted by this flag.",
        "information_policy": {
            "historical_team_observations": "Retrospective next-calendar-day outcome assumption; not proof of historical publication time.",
            "strict_replay": "Filter actual request retrieved_at by the forecast timestamp; never backdate captures to match or transfer dates.",
            "prospective_late_availability": "Not admitted at twelve-hour capture cadence.",
            "markets": "External benchmark only, with separately labeled information horizons.",
            "cohort_usage": "Intersect exact valid_matches IDs for each compared signal set; training must precede each origin and transition targets must be later cohorts.",
        },
    }


def freeze_research(root: Path, destination: Path, start=2013, end=2026) -> dict:
    data = Dataset(root)
    try:
        data.verify()
        report = research_readiness(data, start, end)
        snapshot = data.manifests
    finally:
        data.close()
    manifest = {
        "schema": "research-ready-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "execution": execution_provenance(),
        "readiness": report,
        "canonical_manifests": snapshot,
        "canonical_snapshot_sha256": sha256_bytes(json_bytes(snapshot)),
    }
    write_immutable(destination, json_bytes(manifest))
    return manifest


def frozen_dataset(root: Path, manifest_path: Path, cutoff=None) -> Dataset:
    manifest = json.loads(manifest_path.read_text())
    if manifest["schema"] != "research-ready-v1":
        raise ValueError("Unsupported research manifest")
    snapshot = manifest["canonical_manifests"]
    if sha256_bytes(json_bytes(snapshot)) != manifest["canonical_snapshot_sha256"]:
        raise ValueError("Research snapshot checksum mismatch")
    data = Dataset(root, cutoff=cutoff, manifests=snapshot)
    try:
        data.verify()
    except Exception:
        data.close()
        raise
    return data
