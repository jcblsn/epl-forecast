"""Audit Understat/FPL identity links and role semantics without fuzzy assignment."""

import argparse
import json
from pathlib import Path

from epl_forecast.data.player_process import identity_audit
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=Path("configs/understat_player_sample.json"))
    parser.add_argument(
        "--players", type=Path, default=Path("data/processed/players/player_matches.csv.gz")
    )
    parser.add_argument("--aliases", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Identity report already exists")
    aliases = json.loads(args.aliases.read_text()) if args.aliases else {}
    report = identity_audit(args.sample, args.players, aliases=aliases)
    if args.aliases:
        report["inputs"][str(args.aliases)] = file_hash(args.aliases)
    write_json(args.output, report)


if __name__ == "__main__":
    main()
