"""Stage missing API-FOOTBALL player histories independently of the canonical writer."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from epl_forecast.data.api_football import preflight, request
from epl_forecast.data.capture import Fetcher, QuotaReached, SourceAccessError, writer_lock
from epl_forecast.data.collect import prioritized_players
from epl_forecast.storage import write_json


def captured_keys(records):
    return {
        (r["context"]["endpoint"], int(r["context"]["player"]))
        for r in records
        if r["provider"] == "api_football"
        and r["context"].get("endpoint") in {"transfers", "sidelined"}
        and "player" in r["context"]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--start", type=int, default=2016)
    parser.add_argument("--end", type=int, default=2026)
    parser.add_argument("--max-requests", type=int, default=6000)
    parser.add_argument("--reserve", type=int, default=1000)
    args = parser.parse_args()
    if (
        args.stage.resolve() == args.data.resolve()
        or args.data.resolve() in args.stage.resolve().parents
    ):
        raise ValueError("Stage must be separate from canonical data")
    if args.start > args.end or args.max_requests < 1 or args.reserve < 0:
        raise ValueError("Invalid capture bounds")
    with writer_lock(args.stage):
        source = Fetcher(args.data)
        fetcher = Fetcher(args.stage, reserve=args.reserve)
        known = captured_keys(source.records + fetcher.records)
        people = prioritized_players(args.data, args.start, args.end)
        pending = [
            (endpoint, p["api_id"])
            for p in people
            for endpoint in ("sidelined", "transfers")
            if (endpoint, p["api_id"]) not in known
        ]
        report = {
            "started_at": datetime.now(UTC).isoformat(),
            "start": args.start,
            "end": args.end,
            "players": len(people),
            "pending_at_start": len(pending),
            "captured": 0,
            "errors": [],
            "status": "running",
            "publication": "raw staging only; canonical publication still required",
            "subscription": preflight(fetcher),
        }
        report_file = args.stage / "progress.json"
        write_json(report_file, report)
        print(f"Missing player-history requests: {len(pending)}", flush=True)
        try:
            for endpoint, pid in pending[: args.max_requests]:
                try:
                    request(fetcher, endpoint, {"player": pid}, historical=True)
                    report["captured"] += 1
                except QuotaReached:
                    raise
                except (SourceAccessError, ConnectionError) as error:
                    report["errors"].append(
                        {"endpoint": endpoint, "player": pid, "reason": str(error)}
                    )
                report["updated_at"] = datetime.now(UTC).isoformat()
                report["remaining_quota"] = fetcher.remaining
                write_json(report_file, report)
                if report["captured"] % 50 == 0:
                    print(
                        f"Captured {report['captured']}/{len(pending)}; quota {fetcher.remaining}",
                        flush=True,
                    )
            report["status"] = "complete" if report["captured"] == len(pending) else "paused"
        except QuotaReached as error:
            report.update(status="paused", reason=str(error))
        finally:
            report["finished_at"] = datetime.now(UTC).isoformat()
            write_json(report_file, report)
        print(report["status"], flush=True)


if __name__ == "__main__":
    main()
