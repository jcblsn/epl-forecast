"""One command from collected data to a verified, published forecast.

The pipeline reuses the existing collector, forecast export, product verifier and
immutable archive. It runs the frozen product model for both leagues, refuses to
publish an archive that fails verification, then derives the compact public
documents, refreshes the snapshot index and rebuilds the prospective ledger.
Provider data never leaves `data/`; only `site/data/` is publishable.
"""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from epl_forecast.data.capture import SourceAccessError, writer_lock
from epl_forecast.data.collect import collect
from epl_forecast.datasets import Dataset
from epl_forecast.ledger import build_ledger, realized_outcomes
from epl_forecast.prospective import information_fingerprint
from epl_forecast.publication import (
    derive_forecast,
    load_policy,
    publish_document,
    rebuild_index,
)
from epl_forecast.storage import json_bytes, write_immutable, write_json

PRODUCT_MODEL = "M7-xg-v1"
PRODUCT_CONFIG = Path("configs/xg_quality_tilt.toml")
LEAGUES = ("eng-premier-league", "eng-championship")
REPOSITORY = Path(__file__).resolve().parents[2]


def snapshot_id(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H%M%SZ")


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, check=False, cwd=REPOSITORY)


def run_forecast(data: Path, league: str, cutoff: datetime, output: Path, simulations: int):
    return _run(
        [
            sys.executable,
            "-m",
            "epl_forecast.cli",
            "forecast",
            "--data",
            str(data),
            "--competition",
            league,
            "--cutoff",
            cutoff.isoformat(),
            "--config",
            str(PRODUCT_CONFIG),
            "--model",
            PRODUCT_MODEL,
            "--output",
            str(output),
            "--simulations",
            str(simulations),
        ]
    )


def verify_archive(data: Path, archive: Path, output: Path):
    return _run(
        [
            sys.executable,
            "scripts/verify_forecast_product.py",
            "--archive",
            str(archive),
            "--data",
            str(data),
            "--output",
            str(output),
        ]
    )


def due(state: dict, fingerprint: str, now: datetime, interval_hours: float) -> bool:
    if state.get("fingerprint") != fingerprint:
        return True
    last = state.get("published_at")
    if not last:
        return True
    return (now - datetime.fromisoformat(last)).total_seconds() >= interval_hours * 3600


def operate(
    data: Path = Path("data"),
    site: Path = Path("site"),
    runs: Path = Path("runs/product"),
    simulations: int = 10000,
    interval_hours: float = 12,
    force: bool = False,
    collect_first: bool = True,
) -> dict:
    data, site, runs = Path(data), Path(site), Path(runs)
    policy = load_policy()
    result = {"status": "ok", "published": [], "collection": None}
    if collect_first:
        try:
            with writer_lock(data):
                result["collection"] = collect(data)
        except SourceAccessError as error:
            return {"status": "skipped", "reason": str(error)}
    now = datetime.now(UTC)
    dataset = Dataset(data, now)
    try:
        fingerprint = information_fingerprint(dataset)
        outcomes = realized_outcomes(dataset.fixtures())
    finally:
        dataset.close()
    state_path = runs / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if not force and not due(state, fingerprint, now, interval_hours):
        result.update(status="unchanged", reason="No new information since the last publication")
        build_ledger(site, outcomes, policy)
        return result
    snapshot = snapshot_id(now)
    attempt = runs / snapshot
    documents, failures = [], []
    for league in LEAGUES:
        archive = attempt / league
        forecast = run_forecast(data, league, now, archive, simulations)
        write_immutable(
            attempt / f"{league}-forecast.log", (forecast.stdout + forecast.stderr).encode()
        )
        if forecast.returncode:
            failures.append(
                {"league": league, "stage": "forecast", "detail": forecast.stderr[-800:]}
            )
            continue
        reports = attempt / f"{league}-verification"
        verification = verify_archive(data, archive, reports)
        write_immutable(
            attempt / f"{league}-verify.log", (verification.stdout + verification.stderr).encode()
        )
        if verification.returncode:
            failures.append(
                {"league": league, "stage": "verify", "detail": verification.stdout[-800:]}
            )
            continue
        report = json.loads((reports / "verification.json").read_text())
        documents.append(
            derive_forecast(
                json.loads((archive / "forecast.json").read_text()),
                json.loads((archive / "run.json").read_text()),
                snapshot,
                report["archives"][str(archive)],
            )
        )
    if failures or len(documents) != len(LEAGUES):
        result.update(status="failed", failures=failures, attempt=str(attempt))
        write_immutable(attempt / "pipeline.json", json_bytes(result))
        return result
    for document in documents:
        publish_document(site, document, policy)
        result["published"].append(f"{snapshot}/{document['competition_id']}")
    index = rebuild_index(site, policy)
    ledger = build_ledger(site, outcomes, policy)
    result.update(
        attempt=str(attempt),
        snapshot_id=snapshot,
        snapshots=len(index["snapshots"]),
        scored_matches=ledger["summary"].get("overall", {}).get("scored", 0),
    )
    write_immutable(attempt / "pipeline.json", json_bytes(result))
    write_json(state_path, {"fingerprint": fingerprint, "published_at": now.isoformat()})
    return result
