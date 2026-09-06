"""Restore pinned FPL histories and audit a retrospective player-match dataset."""

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from epl_forecast.data.live import read_live_snapshot
from epl_forecast.data.normalize import TEAM_FILE, team_aliases
from epl_forecast.data.players import normalize_player_matches, read_player_csv
from epl_forecast.data.sources import download


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("configs/player_data_snapshot.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/players"))
    parser.add_argument("--snapshots", type=Path, default=Path("snapshots"))
    parser.add_argument("--matches", type=Path, default=Path("data/processed/matches.csv"))
    parser.add_argument("--report", type=Path, default=Path("docs/player_data_audit.json"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    files = {}
    for entry in manifest["files"]:
        path = Path(entry["path"])
        if not path.exists():
            payload, _ = download(entry["url"])
            if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise ValueError(f"Restored source checksum mismatch: {path}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        payload = path.read_bytes()
        if len(payload) != entry["bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError(f"Source checksum mismatch: {path}")
        files[path] = entry
    root = Path("data/raw/players") / manifest["commit"]
    teams, _ = read_player_csv(root / "master_team_list.csv")
    aliases = team_aliases()
    registry, _ = read_player_csv(TEAM_FILE)
    aliases.update({r["team_name"]: r["team_id"] for r in registry})
    aliases.update(
        {
            "Man Utd": "manchester-united",
            "Sheffield Utd": "sheffield-united",
            "Spurs": "tottenham-hotspur",
        }
    )
    output, reports = [], []
    prior_codes = set()
    prior_element_codes = defaultdict(set)
    for season in sorted({p.parent.parent.name for p in files if p.name == "merged_gw.csv"}):
        directory = root / season
        path = directory / "gws/merged_gw.csv"
        rows, encoding = read_player_csv(path)
        players, _ = read_player_csv(directory / "players_raw.csv")
        fixture_path = directory / "fixtures.csv"
        fixtures = read_player_csv(fixture_path)[0] if fixture_path.exists() else None
        mapping = {r["team"]: aliases[r["team_name"]] for r in teams if r["season"] == season}
        team_path = directory / "teams.csv"
        if team_path.exists():
            mapping = {r["id"]: aliases[r["name"]] for r in read_player_csv(team_path)[0]}
        normalized, report = normalize_player_matches(
            season, rows, players, mapping, files[path]["sha256"], fixtures
        )
        codes = [r["code"] for r in players if r.get("code")]
        report["encoding"] = encoding
        report["player_codes_missing"] = len(players) - len(codes)
        report["player_code_duplicates"] = len(codes) - len(set(codes))
        report["codes_seen_in_previous_seasons"] = len(set(codes) & prior_codes)
        report["element_ids_reused_for_different_codes"] = sum(
            bool(prior_element_codes[r["id"]] - {r["code"]}) for r in players
        )
        report["fixtures_crosschecked"] = fixtures is not None
        for row in players:
            prior_element_codes[row["id"]].add(row["code"])
        prior_codes.update(codes)
        output.extend(normalized)
        reports.append(report)
        print(f"{season}: {len(normalized):,} normalized rows", flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "player_matches.csv.gz"
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped,
    ):
        import io

        with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(output[0]))
            writer.writeheader()
            writer.writerows(output)
    snapshots = []
    for path in sorted(args.snapshots.glob("*/fpl_bootstrap.json")):
        captured = read_live_snapshot(path.parent)
        entry = next(r for r in captured["files"] if r["name"] == path.name)
        bootstrap = json.loads(path.read_text())
        players = bootstrap["elements"]
        fields = (
            "status",
            "news",
            "news_added",
            "chance_of_playing_this_round",
            "chance_of_playing_next_round",
            "can_select",
            "can_transact",
            "removed",
            "team_join_date",
            "birth_date",
            "scout_risks",
            "scout_news_link",
        )
        snapshots.append(
            {
                "path": str(path),
                "sha256": entry["sha256"],
                "retrieved_at": entry["retrieved_at"],
                "players": len(players),
                "statuses": dict(Counter(r["status"] for r in players)),
                "field_nonempty": {
                    field: sum(r.get(field) not in (None, "", [], {}) for r in players)
                    for field in fields
                },
                "player_match_history_present": "history" in players[0],
            }
        )
    dataset = args.output / "player_matches.csv.gz"
    match_crosscheck = None
    if args.matches.exists():
        matches = {r["match_id"]: r for r in read_player_csv(args.matches)[0]}
        player_fixtures = {r["match_id"]: r["kickoff_time"][:10] for r in output}
        matched = set(matches) & set(player_fixtures)
        match_crosscheck = {
            "path": str(args.matches),
            "sha256": hashlib.sha256(args.matches.read_bytes()).hexdigest(),
            "player_fixtures": len(player_fixtures),
            "matched": len(matched),
            "missing_match_ids": sorted(set(player_fixtures) - set(matches)),
            "date_disagreements": sorted(
                key for key in matched if matches[key]["match_date"] != player_fixtures[key]
            ),
        }
    report = {
        "source_manifest": str(args.manifest),
        "source_commit": manifest["commit"],
        "dataset": str(dataset),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "normalized_rows": len(output),
        "seasons": reports,
        "local_snapshots": snapshots,
        "football_data_match_crosscheck": match_crosscheck,
        "historical_publication_timestamps_verified": False,
        "prior_minutes_policy": "Last five observed player-fixtures on strictly earlier UTC dates; "
        "includes zero minutes, resets each season, blank for no history. Retrospective values "
        "may contain later corrections; no timestamped historical release claim.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {dataset} and {args.report}")


if __name__ == "__main__":
    main()
