import argparse
import json
import subprocess
import sys
from pathlib import Path

from epl_forecast.artifacts import new_run_directory
from epl_forecast.storage import file_hash, write_json


def run(*arguments: str) -> None:
    subprocess.run([sys.executable, "-m", "epl_forecast.cli", *map(str, arguments)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduce the initial forecasting milestone")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    new_run_directory(args.output)
    processed = args.output / "processed"
    run("data", "restore", "--root", args.data_root)
    run("data", "normalize", "--root", args.data_root, "--output", processed)
    repeated = args.output / "processed_repeat"
    run("data", "normalize", "--root", args.data_root, "--output", repeated)
    hashes = {}
    for name in ("matches.csv", "odds.csv", "coverage.json", "manifest.json"):
        hashes[name] = file_hash(processed / name)
        if hashes[name] != file_hash(repeated / name):
            raise RuntimeError(f"Normalization is not deterministic: {name}")
    run("data", "audit", "--data", processed, "--output", args.output / "data_audit.csv")
    run("data", "cross-check", "--data", processed, "--output", args.output / "crosscheck.json")
    for split in ("development", "validation", "holdout"):
        run("evaluate", "--data", processed, "--split", split, "--output", args.output / split)
    simulation_dir = args.output / "simulation"
    run(
        "simulate",
        "--data",
        processed,
        "--season",
        "2024-2025",
        "--as-of",
        "2025-01-01",
        "--europe-scenario",
        "configs/europe_scenario.example.json",
        "--output",
        simulation_dir,
    )
    run(
        "predict",
        "--data",
        processed,
        "--season",
        "2024-2025",
        "--date",
        "2024-08-17",
        "--home",
        "arsenal",
        "--away",
        "wolverhampton-wanderers",
        "--output",
        args.output / "example_forecast.json",
    )
    simulation = json.loads((simulation_dir / "simulation.json").read_text())
    title_sum = sum(row["title_probability"] for row in simulation["teams"])
    relegation_sum = sum(row["relegation_probability"] for row in simulation["teams"])
    if abs(title_sum - 1) > 1e-10 or abs(relegation_sum - 3) > 1e-10:
        raise RuntimeError("Simulation event probabilities do not conserve slots")
    write_json(
        args.output / "verification.json",
        {
            "normalized_files_identical": hashes,
            "title_probability_sum": title_sum,
            "relegation_probability_sum": relegation_sum,
            "crosscheck_passed": True,
            "completed_splits": ["development", "validation", "holdout"],
            "simulation_draws": simulation["simulations"],
            "remaining_fixtures": simulation["remaining_matches"],
        },
    )
    print(f"Reproduction complete: {args.output}")


if __name__ == "__main__":
    main()
