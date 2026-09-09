"""Explain individual player estimates: components, uncertainty, exposure and evidence."""

import argparse
import json
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import new_run_directory, provenance, write_csv
from epl_forecast.datasets import Dataset
from epl_forecast.research.player_layer import CANDIDATES, PlayerLayer, observation_rows, player_state
from epl_forecast.research.player_layer_evaluation import (
    _matrix,
    _offset,
    build_cases,
    fit_poisson_ridge,
)
from epl_forecast.research.player_layer_inspector import compare, decompose, estimate_table
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.storage import write_json


def normalized(value):
    return (
        unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode()
    )


def resolve(layer, wanted):
    names = {}
    for index, row in enumerate(layer.rows):
        if row.get("player_name"):
            names.setdefault(row["player_id"], row["player_name"])
    resolved, unresolved = {}, []
    for target in wanted:
        needle = normalized(target)
        matches = [pid for pid, name in names.items() if needle in normalized(name)]
        matches.sort(key=lambda pid: -len(layer.by_player[pid]))
        if matches:
            resolved[target] = matches[0]
        else:
            unresolved.append(target)
    return resolved, unresolved


def timeline(layer, player_id, cutoff):
    indices = layer.by_player.get(player_id)
    if indices is None:
        return []
    indices = indices[layer.eligible[indices] <= cutoff.toordinal()]
    spells = []
    for index in indices:
        club = str(layer.teams[index])
        season = layer.rows[index]["season_id"]
        if spells and spells[-1]["club"] == club and spells[-1]["season_id"] == season:
            spell = spells[-1]
        else:
            spell = {
                "club": club,
                "season_id": season,
                "first": str(date.fromordinal(int(layer.days[index]))),
                "appearances": 0,
                "minutes": 0.0,
                "xg": 0.0,
                "xa": 0.0,
                "process_appearances": 0,
            }
            spells.append(spell)
        spell["last"] = str(date.fromordinal(int(layer.days[index])))
        spell["appearances"] += 1
        spell["minutes"] += float(layer.rows[index]["minutes"])
        if layer.available["xg"][index]:
            spell["process_appearances"] += 1
            spell["xg"] += float(layer.values["xg"][index])
            spell["xa"] += float(layer.values["xa"][index])
    return spells


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--marks", nargs="+", default=["xg", "xa"])
    parser.add_argument("--players", nargs="+", required=True)
    parser.add_argument("--horizon-days", type=int, default=90)
    parser.add_argument("--training-months", type=int, default=24)
    parser.add_argument("--leaderboard", type=int, default=40)
    args = parser.parse_args()
    new_run_directory(args.output)
    cutoff = date.fromisoformat(args.cutoff)
    data = frozen_dataset(args.data, args.manifest) if args.manifest else Dataset(args.data)
    try:
        rows = observation_rows(data)
        manifest = data.provenance()
    finally:
        data.close()
    layer = PlayerLayer(rows)
    resolved, unresolved = resolve(layer, args.players)
    closed = cutoff - timedelta(days=args.horizon_days)
    training_cutoffs = []
    current = closed
    for _ in range(args.training_months):
        training_cutoffs.append(current.replace(day=1))
        current = (current.replace(day=1) - timedelta(days=1)).replace(day=1)
    training_cutoffs = sorted(set(training_cutoffs))
    report = {
        "cutoff": str(cutoff),
        "resolved_players": resolved,
        "unresolved_players": unresolved,
        "training_cutoffs": [str(c) for c in training_cutoffs],
        "marks": {},
    }
    for mark in args.marks:
        cases = build_cases(layer, training_cutoffs, args.horizon_days, mark)
        block = {"training_cases": len(cases), "candidates": {}}
        if not cases:
            report["marks"][mark] = block
            continue
        response = np.array([c["target_total"] for c in cases])
        offset = _offset(cases, mark)
        states = {
            label: player_state(layer, player_id, cutoff)
            for label, player_id in resolved.items()
        }
        eligible = [
            player_state(layer, pid, cutoff)
            for pid, indices in layer.by_player.items()
            if layer.available[mark][
                indices[layer.eligible[indices] <= cutoff.toordinal()]
            ].sum()
            >= 5
        ]
        for candidate in CANDIDATES:
            names, matrix = _matrix(cases, candidate, mark)
            model = fit_poisson_ridge(matrix, offset, response)
            model["names"] = names
            block["candidates"][candidate] = {
                "coefficients": dict(
                    zip(["intercept", *names], [float(v) for v in model["beta"]], strict=True)
                ),
                "dispersion": model["dispersion"],
                "players": {
                    label: decompose(model, state, candidate, mark)
                    for label, state in states.items()
                },
            }
            table = estimate_table(model, eligible, candidate, mark)
            write_csv(
                args.output / f"{mark}_{candidate}_estimates.csv",
                list(table[0]) if table else ["player_id"],
                table[: args.leaderboard],
            )
            labels = sorted(states)
            block["candidates"][candidate]["pairwise"] = [
                compare(model, states[left], states[right], candidate, mark)
                for i, left in enumerate(labels)
                for right in labels[i + 1 :]
            ]
        report["marks"][mark] = block
    report["timelines"] = {
        label: timeline(layer, player_id, cutoff) for label, player_id in resolved.items()
    }
    write_json(args.output / "inspection.json", report)
    write_json(
        args.output / "provenance.json",
        provenance({"cutoff": str(cutoff), "players": args.players}, manifest),
    )
    print(
        json.dumps(
            {
                mark: {
                    label: {
                        candidate: round(
                            block["candidates"][candidate]["players"][label][
                                "estimated_rate_per_90"
                            ],
                            4,
                        )
                        for candidate in ("pooled_role", "long_run", "context_share")
                        if candidate in block["candidates"]
                    }
                    for label in resolved
                }
                for mark, block in report["marks"].items()
                if block["candidates"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
