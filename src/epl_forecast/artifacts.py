import csv
import io
import platform
import subprocess
import sys
from importlib.metadata import distributions
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


def execution_provenance(root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[2]

    def git(*args):
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.rstrip("\n")
        except (OSError, subprocess.CalledProcessError):
            return None

    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    execution_files = [root / "pyproject.toml", root / "uv.lock"]
    execution_files.extend(sorted((root / "scripts").glob("*.py")))
    invoked = Path(sys.argv[0]).resolve()
    return {
        "commit": commit,
        "dirty": bool(status) if status is not None else None,
        "git_status": status,
        "execution_files": {
            p.relative_to(root).as_posix(): file_hash(p) for p in execution_files if p.is_file()
        },
        "lockfile_sha256": file_hash(root / "uv.lock") if (root / "uv.lock").is_file() else None,
        "argv": list(sys.argv),
        "interpreter_argv": list(sys.orig_argv),
        "invoked_file_sha256": file_hash(invoked) if invoked.is_file() else None,
        "working_directory": str(Path.cwd()),
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "dependencies": dict(
            sorted((d.metadata["Name"], d.version) for d in distributions() if d.metadata["Name"])
        ),
    }


def provenance(config: dict, data_manifest: dict) -> dict:
    execution = execution_provenance()
    return {
        "package_version": __version__,
        "code_sha256": code_fingerprint(),
        "python": platform.python_version(),
        "dependencies": execution["dependencies"],
        "execution": execution,
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


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stream.getvalue())
