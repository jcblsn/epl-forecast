"""Retain the complete corrected player comparison and render its horizon audit."""

import argparse
import csv
import gzip
import io
import json
import tarfile
from pathlib import Path

from epl_forecast.artifacts import new_run_directory
from epl_forecast.research.player_layer_evaluation import paired_bootstrap
from epl_forecast.storage import file_hash, write_json


def scores(file):
    with file.open() as stream:
        return [dict(row, crps=float(row["crps"])) for row in csv.DictReader(stream)]


def interval(entry, candidate):
    paired = entry["transfer_paired_vs_long_run"][candidate]
    low, high = paired["interval"]
    return f"{paired['difference']:+.4f} [{low:+.4f}, {high:+.4f}]"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-pattern", default="runs/player-layer-complete-h{horizon}")
    parser.add_argument("--audit", type=Path, default=Path("runs/player-signal-audit-corrected"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("runs/research-ready-v2-player-layer/manifest.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    new_run_directory(args.output)
    sources = [(args.manifest, "data_manifest.json")]
    summary = {
        "horizons": {},
        "signal_audit": json.loads((args.audit / "signal_audit.json").read_text()),
    }
    lines = [
        "# Corrected player evidence",
        "",
        "Lower CRPS is better. Differences are candidate minus long_run, with 95% player-clustered bootstrap intervals. Cases differ across horizons; compare candidates within a row's horizon.",
        "",
    ]
    for horizon in (90, 180, 240):
        run = Path(args.run_pattern.format(horizon=horizon))
        block = json.loads((run / "summary.json").read_text())
        assert block["horizon_days"] == horizon
        for mark, entry in block["marks"].items():
            if "observation_end_exclusive" not in entry:
                raise ValueError("Use corrected runs with fully elapsed target windows")
            entry["additional_paired_comparisons"] = {
                population: {
                    f"{candidate}_vs_api_only": paired_bootstrap(
                        scores(run / f"{mark}_{candidate}_{population}.csv"),
                        scores(run / f"{mark}_api_only_{population}.csv"),
                    )
                    for candidate in ("api_depth_matched", "api_rating")
                }
                for population in ("chronological", "transfer")
            }
        summary["horizons"][str(horizon)] = block
        sources.extend(
            (file, f"h{horizon}/{file.relative_to(run)}")
            for file in sorted(run.rglob("*"))
            if file.is_file()
        )
        lines.extend(
            [
                f"## {horizon}-day transfers",
                "",
                "| Mark | Cases | Long-run CRPS | Pooled role − long-run | API − long-run | Matched API − long-run |",
                "| --- | ---: | ---: | --- | --- | --- |",
            ]
        )
        for mark in ("xg", "xa", "process_shots"):
            entry = block["marks"][mark]

            reference = entry["transfer"]["long_run"]
            lines.append(
                f"| {mark} | {reference['cases']} | {reference['crps']:.4f} | {interval(entry, 'pooled_role')} | {interval(entry, 'api_only')} | {interval(entry, 'api_depth_matched')} |"
            )
        lines.append("")
    sources.extend(
        (file, f"signal_audit/{file.relative_to(args.audit)}")
        for file in sorted(args.audit.rglob("*"))
        if file.is_file()
    )
    archive = args.output / "evidence.tar.gz"
    with (
        archive.open("wb") as stream,
        gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as tar,
    ):
        for file, name in sources:
            payload = file.read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    write_json(args.output / "summary.json", summary)
    write_json(
        args.output / "manifest.json",
        {
            "archive_sha256": file_hash(archive),
            "files": {name: file_hash(file) for file, name in sources},
        },
    )
    (args.output / "report.md").write_text("\n".join(lines))
    print(json.dumps({"files": len(sources), "archive_bytes": archive.stat().st_size}))


if __name__ == "__main__":
    main()
