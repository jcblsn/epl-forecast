"""Run reusable M8 observation and known-state diagnostics."""

import argparse
from datetime import date
from pathlib import Path

from epl_forecast.artifacts import new_run_directory
from epl_forecast.datasets import load_dataset
from epl_forecast.research.process_diagnostics import conditional_goal_checks, known_state_checks
from epl_forecast.storage import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 8, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2024, 11, 1))
    parser.add_argument("--replicates", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bridge", action="store_true")
    parser.add_argument("--predictive", action="store_true")
    args = parser.parse_args()
    new_run_directory(args.output)
    from epl_forecast.datasets import load_process

    observations = load_process(args.data)
    report = {
        "canonical_data": str(args.data),
        "conditional_goals": conditional_goal_checks(observations),
    }
    write_json(args.output / "report.json", report)
    if args.predictive:
        from epl_forecast.research.process_diagnostics import predictive_checks

        matches, _, _ = load_dataset(Path("data"))
        report["predictive"] = predictive_checks(matches, observations, args.start, args.end)
        write_json(args.output / "report.json", report)
    if args.bridge:
        from epl_forecast.research.process_bridge import bridge_diagnostic

        matches, _, _ = load_dataset(Path("data"))
        report["championship_bridge"] = bridge_diagnostic(matches, observations)
        write_json(args.output / "report.json", report)
    if args.replicates:
        matches, _, _ = load_dataset(Path("data"))
        subset = [
            m
            for m in matches
            if m.fixture.competition_id == "eng-premier-league"
            and args.start <= m.fixture.match_date < args.end
        ]
        report["known_state"] = known_state_checks(subset, args.replicates)
        write_json(args.output / "report.json", report)


if __name__ == "__main__":
    main()
