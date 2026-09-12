"""Publish already-archived product forecasts into the site archive.

This preserves earlier prospective runs exactly as they were generated: each
archive is verified as it stands and then reduced to the same public document a
fresh pipeline run would write. Nothing is refitted, and an archive that fails
verification is reported and skipped rather than corrected.
"""

import argparse
import json
import re
from pathlib import Path

from epl_forecast.datasets import Dataset
from epl_forecast.ledger import build_ledger, realized_outcomes
from epl_forecast.pipeline import verify_archive
from epl_forecast.publication import (
    carry_forward_impacts,
    derive_forecast,
    load_policy,
    publish_document,
    rebuild_index,
)

STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{6})")


def snapshot_id(directory: Path) -> str:
    match = STAMP.search(directory.name)
    if not match:
        raise ValueError(f"Archive directory carries no timestamp: {directory}")
    return f"{match.group(1)}Z"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("runs/product"))
    parser.add_argument("--pattern", default="*/eng-*")
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--verification", type=Path, default=Path("runs/product/backfill"))
    args = parser.parse_args()
    policy = load_policy()
    published, skipped = [], []
    for archive in sorted(args.source.glob(args.pattern)):
        if not (archive / "forecast.json").is_file():
            continue
        relative = archive.relative_to(args.source)
        attempt, name = relative.parts[0], relative.as_posix()
        report_directory = args.verification / relative
        completed = verify_archive(args.data, archive, report_directory)
        if completed.returncode:
            reason = (completed.stdout + completed.stderr).strip().splitlines()
            skipped.append(
                {"archive": name, "reason": reason[-1] if reason else "verification failed"}
            )
            continue
        report = json.loads((report_directory / "verification.json").read_text())
        try:
            document = carry_forward_impacts(
                args.site,
                derive_forecast(
                    json.loads((archive / "forecast.json").read_text()),
                    json.loads((archive / "run.json").read_text()),
                    snapshot_id(args.source / attempt),
                    report["archives"][str(archive)],
                ),
            )
            publish_document(args.site, document, policy)
        except ValueError as error:
            skipped.append({"archive": name, "reason": str(error)})
            continue
        published.append(f"{document['snapshot_id']}/{document['competition_id']}")
    index = rebuild_index(args.site, policy)
    dataset = Dataset(args.data)
    try:
        outcomes = realized_outcomes(dataset.fixtures())
    finally:
        dataset.close()
    ledger = build_ledger(args.site, outcomes, policy)
    print(
        json.dumps(
            {
                "published": published,
                "skipped": skipped,
                "snapshots": len(index["snapshots"]),
                "scored_matches": ledger["summary"].get("overall", {}).get("scored", 0),
                "unsettled": ledger["unsettled"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
