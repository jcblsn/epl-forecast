import platform
from importlib.metadata import version
from pathlib import Path

from epl_forecast import __version__
from epl_forecast.storage import file_hash, json_bytes, sha256_bytes


def code_fingerprint() -> str:
    root = Path(__file__).parent
    files = {
        p.relative_to(root).as_posix(): file_hash(p)
        for p in sorted(root.rglob("*"))
        if p.suffix in {".py", ".csv", ".json"}
    }
    return sha256_bytes(json_bytes(files))


def provenance(config: dict, data_manifest: dict) -> dict:
    return {
        "package_version": __version__,
        "code_sha256": code_fingerprint(),
        "python": platform.python_version(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy")},
        "config": config,
        "config_sha256": sha256_bytes(json_bytes(config)),
        "data_manifest": data_manifest,
    }


def new_run_directory(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"Run directory is not empty: {path}. Choose a new output path.")
    path.mkdir(parents=True, exist_ok=True)


def results_markdown(summary: dict) -> str:
    lines = ["# Chronological evaluation", ""]
    if summary.get("evaluation_status"):
        lines.extend([f"Evaluation status: {summary['evaluation_status']}.", ""])
    if summary.get("evaluation_note"):
        lines.extend([summary["evaluation_note"], ""])
    lines.extend(
        [
            "Lower is better. Brier is the sum across H/D/A; ECE is the mean of three",
            "classwise, fixed-bin expected calibration errors. Score NLL uses the full",
            "unbounded distribution. Market rows have their own coverage and forecast",
            "horizon; see market_matched.csv"
            + (" and paired_comparisons.json." if summary["paired_comparisons"] else "."),
            "",
            "| Model | Matches | Log loss | Brier | ECE | Score NLL |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary["overall"]:
        score = "—" if row["score_nll"] is None else f"{row['score_nll']:.5f}"
        lines.append(
            f"| {row['model_id']} | {row['matches']} | {row['log_loss']:.5f} | "
            f"{row['brier']:.5f} | {row['classwise_ece']:.5f} | {score} |"
        )
    return "\n".join(lines) + "\n"
