"""Build an offline temporal prior inspector from retained chronological estimates."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from epl_forecast.research.player_prior import load_prior_inputs
from epl_forecast.storage import file_hash

NUMERIC = (
    "mean",
    "sd",
    "feature_mean",
    "residual_mean",
    "local_sd",
    "centered_control_mean",
    "legacy_mean",
    "rating_mean",
    "effective_minutes",
    "days_since_meaningful_minutes",
    "expected_minutes",
    "reference_minutes",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = json.loads((args.evaluation / "run.json").read_text())
    if file_hash(args.inputs / "input_manifest.json") != run["input_manifest_sha256"]:
        raise ValueError("Preview inputs do not match evaluation")
    _, source, _ = load_prior_inputs(args.inputs)
    names = {r["player_id"]: r["player_name"] for r in source.history.rows}
    grouped = defaultdict(dict)
    with (args.evaluation / "player_priors.csv").open() as stream:
        for row in csv.DictReader(stream):
            values = {key: float(row[key]) if row[key] else None for key in NUMERIC}
            item = {
                "date": row["cutoff"],
                "team": row["team_id"],
                "role": row["role"],
                "latest_evidence_date": row["latest_evidence_date"],
                **values,
            }
            previous = grouped[row["player_id"]].get(row["cutoff"])
            if previous is not None and abs(previous["mean"] - item["mean"]) > 1e-10:
                raise ValueError("Conflicting prior means at one player cutoff")
            if previous is None or item["expected_minutes"] > previous["expected_minutes"]:
                grouped[row["player_id"]][row["cutoff"]] = item
    players = [
        {"id": pid, "name": names.get(pid) or pid, "rows": [days[day] for day in sorted(days)]}
        for pid, days in sorted(grouped.items())
    ]
    players.sort(key=lambda p: (p["name"].casefold(), p["id"]))
    if not players:
        raise ValueError("No retained player prior estimates")
    data = {
        "players": players,
        "season": run["arguments"]["season"],
        "evaluation_status": run["status"],
        "input_manifest_sha256": run["input_manifest_sha256"],
        "estimates_sha256": file_hash(args.evaluation / "player_priors.csv"),
    }
    template = Path(__file__).with_name("player_prior_preview.html").read_text()
    payload = json.dumps(data, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(template.replace("__PRIOR_DATA__", payload))
    print(
        f"Preview: {args.output}; {len(players)} players, {sum(len(p['rows']) for p in players)} cutoffs"
    )


if __name__ == "__main__":
    main()
