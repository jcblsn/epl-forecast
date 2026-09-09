"""Render the standalone player-layer evidence tables from a frozen evaluation run."""

import argparse
import json
from pathlib import Path

CANDIDATE_ORDER = (
    "pooled_role",
    "recent_raw",
    "long_run",
    "recent_long",
    "long_plus_env",
    "context_share",
    "context_share_recent",
    "combined_long",
    "api_only",
    "api_rating",
)
MARK_TITLES = {
    "xg": "Shooting (Understat xG)",
    "xa": "Creation (Understat xA)",
    "process_shots": "Shot volume (Understat shots)",
}


def interval(entry):
    if entry is None:
        return "reference"
    low, high = entry["interval"]
    marker = "" if low <= 0 <= high else " *"
    return f"{entry['difference']:+.4f} [{low:+.4f}, {high:+.4f}]{marker}"


def chronological_table(block):
    lines = [
        "| Candidate | CRPS | MAE | 50% cover | 90% cover | Relative width | CRPS − long_run (95% CI) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name in CANDIDATE_ORDER:
        entry = block["chronological"].get(name)
        if not entry or not entry["all"]:
            continue
        row = entry["all"]
        paired = block["chronological_paired_vs_long_run"].get(name)
        width = row.get("mean_relative_width_90")
        lines.append(
            f"| `{name}` | {row['crps']:.5f} | {row['mae']:.4f} | {row['coverage_50']:.3f} | "
            f"{row['coverage_90']:.3f} | {width:.2f} | {interval(paired)} |"
            if width is not None
            else f"| `{name}` | {row['crps']:.5f} | {row['mae']:.4f} | {row['coverage_50']:.3f} | "
            f"{row['coverage_90']:.3f} | — | {interval(paired)} |"
        )
    return lines


def transfer_table(block):
    lines = [
        "| Candidate | CRPS | MAE | 50% cover | 90% cover | CRPS − long_run (95% CI) |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for name in CANDIDATE_ORDER:
        row = block["transfer"].get(name)
        if not row:
            continue
        paired = block["transfer_paired_vs_long_run"].get(name)
        lines.append(
            f"| `{name}` | {row['crps']:.5f} | {row['mae']:.4f} | {row['coverage_50']:.3f} | "
            f"{row['coverage_90']:.3f} | {interval(paired)} |"
        )
    return lines


def slice_table(block, names, slices):
    lines = [
        "| Candidate | " + " | ".join(slices) + " |",
        "| --- | " + " | ".join("---:" for _ in slices) + " |",
    ]
    for name in names:
        entry = block["chronological"].get(name)
        if not entry:
            continue
        cells = []
        for key in slices:
            value = entry.get(key)
            cells.append(f"{value['crps']:.5f}" if value else "—")
        lines.append(f"| `{name}` | " + " | ".join(cells) + " |")
    counts = block["chronological"]["long_run"]
    lines.append(
        "| cases | "
        + " | ".join(str((counts.get(k) or {}).get("cases", "—")) for k in slices)
        + " |"
    )
    return lines


def residual_table(block):
    lines = [
        "| Candidate | Players | Half-split correlation (95% CI) | Persistent sd | Noise sd |",
        "| --- | ---: | --- | ---: | ---: |",
    ]
    for name in CANDIDATE_ORDER:
        entry = (block.get("residual_persistence") or {}).get(name)
        if not entry:
            continue
        low, high = entry["interval"]
        lines.append(
            f"| `{name}` | {entry['players']} | {entry['half_split_correlation']:+.3f} "
            f"[{low:+.3f}, {high:+.3f}] | {entry['persistent_sd']:.3f} | {entry['noise_sd']:.3f} |"
        )
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--slices",
        nargs="+",
        default=[
            "all",
            "changed_club",
            "low_history",
            "high_history",
            "role_FWD",
            "role_MID",
            "role_DEF",
        ],
    )
    args = parser.parse_args()
    summary = json.loads((args.run / "summary.json").read_text())
    lines = []
    for mark, block in summary["marks"].items():
        title = MARK_TITLES.get(mark, mark)
        lines.append(f"### {title}")
        lines.append("")
        lines.append(
            f"{block['cases']} cases built, {len(block['scored_cutoffs'])} scored cutoffs, "
            f"{block['transfer_episodes']} observed club changes. "
            f"A starred interval excludes zero."
        )
        lines.append("")
        lines.append("Chronological, horizon " + str(summary["horizon_days"]) + " days.")
        lines.append("")
        lines.extend(chronological_table(block))
        lines.append("")
        lines.append("Frozen pre-move estimate against early new-club process.")
        lines.append("")
        lines.extend(transfer_table(block))
        lines.append("")
        lines.append("CRPS by slice.")
        lines.append("")
        lines.extend(slice_table(block, CANDIDATE_ORDER, args.slices))
        lines.append("")
        lines.append("Persistence of the residual the mapping does not explain.")
        lines.append("")
        lines.extend(residual_table(block))
        lines.append("")
    text = "\n".join(lines) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
