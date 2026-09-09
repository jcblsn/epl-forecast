"""Replay retained API-FOOTBALL evidence into an isolated player-prior dataset."""

import argparse
import json
from pathlib import Path

from epl_forecast.data import api_football as api
from epl_forecast.data.capture import Fetcher, retain, writer_lock
from epl_forecast.datasets import Dataset
from epl_forecast.storage import file_hash, json_bytes, write_immutable, write_json


def coverage(data):
    fields = [
        "goals",
        "assists",
        "shots",
        "shots_on_target",
        "saves",
        "yellow_cards",
        "red_cards",
        *api.PLAYER_STAT_FIELDS,
        "pass_accuracy",
    ]
    return {
        "fields": [
            {"field": field, **r}
            for field in fields
            for r in data.rows(
                f"SELECT competition_id, season_id, position, count(*) AS appearances, "
                f"count({field}) AS observed, sum(minutes) AS minutes, "
                f"sum(CASE WHEN {field} IS NOT NULL THEN minutes ELSE 0 END) AS observed_minutes "
                "FROM appearances WHERE minutes>0 GROUP BY ALL ORDER BY ALL"
            )
        ],
        "accuracy_forms": data.rows(
            "SELECT season_id, count(pass_accuracy) AS observed, "
            "count(*) FILTER (WHERE contains(pass_accuracy, '%')) AS explicit_percent, "
            "max(try_cast(pass_accuracy AS DOUBLE)) AS max_bare_value "
            "FROM appearances WHERE minutes>0 GROUP BY season_id ORDER BY season_id"
        ),
        "matches": data.rows(
            "SELECT competition_id, season_id, count(*) AS matches FROM fixtures "
            "WHERE status='finished' AND stage='regular' GROUP BY ALL ORDER BY ALL"
        ),
        "normalization_issues": [
            {"source_sha256": m["request"]["source_sha256"], **issue}
            for m in data.manifests
            for issue in m["request"].get("normalization_issues", [])
        ],
        "pass_accuracy_policy": "Preserved verbatim; ambiguous bare-number units excluded from V1 features",
        "missing_policy": "Null is unobserved; denominators use only minutes with an observed field",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seasons", type=int, nargs="+", default=[2022, 2023, 2024])
    args = parser.parse_args()
    if (
        args.output.resolve() == args.source.resolve()
        or args.source.resolve() in args.output.resolve().parents
    ):
        raise ValueError("Research output must be separate from source data")
    with writer_lock(args.output):
        source = Fetcher(args.source)
        selected = []
        for record in sorted(source.latest.values(), key=lambda r: (r["retrieved_at"], r["url"])):
            context = record["context"]
            if record["provider"] != "api_football" or context.get("endpoint") not in {
                "fixtures",
                "players",
            }:
                continue
            if context["endpoint"] == "players" and context.get("season") not in args.seasons:
                continue
            raw = args.source / record["raw_path"]
            if file_hash(raw) != record["source_sha256"]:
                raise ValueError(f"Raw checksum mismatch: {raw}")
            payload = raw.read_bytes()
            body = json.loads(payload)
            if context["endpoint"] == "fixtures":
                body = {
                    **body,
                    "response": [
                        m
                        for m in body["response"]
                        if m["league"]["id"] in api.LEAGUES
                        and m["league"]["season"] in args.seasons
                        and (m.get("players") or m.get("lineups"))
                    ],
                }
                if not body["response"]:
                    continue
            retained = retain(
                args.output,
                record["provider"],
                record["url"],
                payload,
                record["retrieved_at"],
                record["evidence_basis"],
                record["context"],
            )
            selected.append(
                api.normalize(
                    {**retained, "selected_seasons": sorted(args.seasons)}, body, args.output
                )
            )
            if len(selected) % 25 == 0:
                print(f"Replayed {len(selected)} retained captures", flush=True)
        data = Dataset(args.output, manifests=selected)
        try:
            data.verify()
            write_json(args.output / "coverage.json", coverage(data))
            manifest = {
                "seasons": sorted(args.seasons),
                "source": "API-FOOTBALL only; retained fixtures and historical player profiles",
                "cutoff_policy": "Prior London dates; retrospective capture times do not delay historical observations",
                "manifests": selected,
            }
            write_immutable(args.output / "input_manifest.json", json_bytes(manifest))
        finally:
            data.close()
        print(f"Complete: {len(selected)} captures", flush=True)


if __name__ == "__main__":
    main()
