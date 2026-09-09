"""Build an offline inspector for the standalone player-process layer.

Produces one self-contained HTML file: component leaderboards with uncertainty,
per-player decomposition and evidence timelines, head-to-head differences, frozen
pre-transfer estimates against realized new-club process, and the evaluation tables.
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import execution_provenance
from epl_forecast.datasets import Dataset
from epl_forecast.research.player_layer import (
    CANDIDATE_NOTES,
    CANDIDATES,
    PlayerLayer,
    observation_rows,
    player_state,
)
from epl_forecast.research.player_layer_evaluation import (
    _matrix,
    _offset,
    build_cases,
    fit_poisson_ridge,
    transfer_episodes,
)
from epl_forecast.research.player_layer_inspector import decompose
from epl_forecast.research.readiness import frozen_dataset

TRAJECTORY_CANDIDATES = ("pooled_role", "long_run", "recent_long", "context_share", "api_only")


def month_starts(start, end):
    cutoffs, current = [], start.replace(day=1)
    while current <= end:
        cutoffs.append(current)
        current = (current.replace(day=28) + timedelta(days=7)).replace(day=1)
    return cutoffs


def fitted_models(layer, mark, cutoff, horizon_days, training_months, candidates):
    closed = cutoff - timedelta(days=horizon_days)
    training_cutoffs = []
    current = closed.replace(day=1)
    for _ in range(training_months):
        training_cutoffs.append(current)
        current = (current - timedelta(days=1)).replace(day=1)
    cases = build_cases(layer, sorted(set(training_cutoffs)), horizon_days, mark)
    if len(cases) < 200:
        return {}, len(cases)
    offset = _offset(cases, mark)
    response = np.array([c["target_total"] for c in cases])
    models = {}
    for candidate in candidates:
        names, matrix = _matrix(cases, candidate, mark)
        model = fit_poisson_ridge(matrix, offset, response)
        model["names"] = names
        models[candidate] = model
    return models, len(cases)


def spells(layer, player_id, cutoff):
    indices = layer.by_player.get(player_id)
    if indices is None:
        return []
    indices = indices[layer.eligible[indices] <= cutoff.toordinal()]
    result = []
    for index in indices:
        club, season = str(layer.teams[index]), layer.rows[index]["season_id"]
        if result and result[-1]["club"] == club and result[-1]["season"] == season:
            spell = result[-1]
        else:
            spell = {
                "club": club,
                "season": season,
                "first": str(date.fromordinal(int(layer.days[index]))),
                "matches": 0,
                "minutes": 0,
                "xg": 0.0,
                "xa": 0.0,
                "process": 0,
            }
            result.append(spell)
        spell["last"] = str(date.fromordinal(int(layer.days[index])))
        spell["matches"] += 1
        spell["minutes"] += int(layer.rows[index]["minutes"])
        if layer.available["xg"][index]:
            spell["process"] += 1
            spell["xg"] += float(layer.values["xg"][index])
            spell["xa"] += float(layer.values["xa"][index])
    for spell in result:
        spell["xg"] = round(spell["xg"], 3)
        spell["xa"] = round(spell["xa"], 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--evaluation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--trajectory-months", type=int, default=18)
    parser.add_argument("--horizon-days", type=int, default=90)
    parser.add_argument("--training-months", type=int, default=24)
    parser.add_argument("--minimum-appearances", type=int, default=5)
    args = parser.parse_args()
    cutoff = date.fromisoformat(args.cutoff)
    data = frozen_dataset(args.data, args.manifest) if args.manifest else Dataset(args.data)
    try:
        rows = observation_rows(data)
        provenance = data.provenance()
    finally:
        data.close()
    layer = PlayerLayer(rows)
    marks = ("xg", "xa")
    trajectory = month_starts(
        (cutoff - timedelta(days=31 * args.trajectory_months)).replace(day=1), cutoff
    )
    names = {}
    for row in layer.rows:
        if row.get("player_name"):
            names.setdefault(row["player_id"], row["player_name"])

    eligible = {}
    for point in trajectory:
        day = point.toordinal()
        for player_id, indices in layer.by_player.items():
            usable = indices[(layer.eligible[indices] <= day) & layer.available["xg"][indices]]
            if len(usable) >= args.minimum_appearances:
                eligible.setdefault(player_id, set()).add(point)
    print(f"{len(eligible)} players with process history at one or more cutoffs", flush=True)

    series = {pid: {m: {c: [] for c in TRAJECTORY_CANDIDATES} for m in marks} for pid in eligible}
    latest, coefficients, training_sizes = {}, {}, {}
    for mark in marks:
        for point in trajectory:
            models, count = fitted_models(
                layer, mark, point, args.horizon_days, args.training_months, TRAJECTORY_CANDIDATES
            )
            training_sizes[f"{mark}:{point}"] = count
            for player_id, points in eligible.items():
                if point not in points:
                    for candidate in TRAJECTORY_CANDIDATES:
                        series[player_id][mark][candidate].append(None)
                    continue
                state = player_state(layer, player_id, point)
                for candidate in TRAJECTORY_CANDIDATES:
                    model = models.get(candidate)
                    if model is None:
                        series[player_id][mark][candidate].append(None)
                        continue
                    result = decompose(model, state, candidate, mark)
                    series[player_id][mark][candidate].append(
                        [
                            round(result["estimated_rate_per_90"], 4),
                            round(result["uncertainty"]["total_log_sd"], 4),
                        ]
                    )
            print(f"  {mark} {point} fitted on {count} cases", flush=True)
        models, count = fitted_models(
            layer, mark, cutoff, args.horizon_days, args.training_months, tuple(CANDIDATES)
        )
        coefficients[mark] = {
            name: dict(
                zip(
                    ["intercept", *(model["names"] or [])],
                    [round(float(v), 4) for v in model["beta"]],
                    strict=True,
                )
            )
            for name, model in models.items()
        }
        for player_id in eligible:
            state = player_state(layer, player_id, cutoff)
            block = latest.setdefault(player_id, {})
            block["role"] = state.role
            block["club"] = state.club
            results = {
                name: decompose(model, state, name, mark) for name, model in models.items()
            }
            reference = next(iter(results.values()))
            # Exposure, staleness and the share are properties of the player and mark,
            # so they are stored once rather than repeated for every representation.
            block[mark] = {
                "pool": round(reference["role_population_rate"], 5),
                "evidence": {
                    k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in reference["evidence"].items()
                    if k != "share" and v is not None
                },
                "share": (
                    {
                        k: round(v, 4)
                        for k, v in (reference["evidence"]["share"] or {}).items()
                        if v is not None
                    }
                    if reference["evidence"].get("share")
                    else None
                ),
                "candidates": {name: _compact(result) for name, result in results.items()},
            }
    episodes = transfer_episodes(layer, "xg")
    moves = []
    buckets = {}
    for episode in episodes:
        buckets.setdefault(episode["cutoff"].replace(day=1), []).append(episode)
    for origin, group in sorted(buckets.items(), reverse=True):
        models, _ = fitted_models(
            layer,
            "xg",
            origin,
            args.horizon_days,
            args.training_months,
            ("long_run", "context_share", "api_only"),
        )
        if not models:
            continue
        for episode in group:
            moves.append(
                {
                    "player": names.get(episode["player_id"], episode["player_id"]),
                    "player_id": episode["player_id"],
                    "cutoff": str(episode["cutoff"]),
                    "from": episode["club_before"],
                    "to": episode["club_after"],
                    "role": episode["role"],
                    "prior_matches": round(episode["prior_exposure"], 1),
                    "new_club_matches": round(episode["target_exposure"], 1),
                    "observed_xg_per_90": round(
                        episode["target_total"] / episode["target_exposure"], 4
                    ),
                    "predicted": {
                        name: round(
                            decompose(models[name], episode["state"], name, "xg")[
                                "estimated_rate_per_90"
                            ],
                            4,
                        )
                        for name in models
                    },
                }
            )
    moves.sort(key=lambda m: m["cutoff"], reverse=True)
    payload = {
        "generated_at": str(date.today()),
        "cutoff": str(cutoff),
        "trajectory": [str(p) for p in trajectory],
        "marks": list(marks),
        "candidates": list(CANDIDATES),
        "trajectory_candidates": list(TRAJECTORY_CANDIDATES),
        "candidate_notes": CANDIDATE_NOTES,
        "coefficients": coefficients,
        "training_cases": training_sizes,
        "players": [
            {
                "id": pid,
                "name": names.get(pid, pid),
                "role": latest[pid]["role"],
                "club": latest[pid]["club"],
                "series": series[pid],
                "latest": {m: latest[pid][m] for m in marks},
                "spells": spells(layer, pid, cutoff),
            }
            for pid in sorted(eligible, key=lambda p: names.get(p, p).casefold())
        ],
        "transfers": moves,
        "evaluation": json.loads((args.evaluation / "summary.json").read_text())
        if args.evaluation
        else None,
        "provenance": {
            "batches": len(provenance["batches"]),
            "cutoff": provenance["cutoff"],
            "commit": execution_provenance()["commit"],
        },
    }
    template = Path(__file__).with_name("player_layer_preview.html").read_text()
    body = json.dumps(payload, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(template.replace("__LAYER_DATA__", body))
    print(f"Preview: {args.output}; {len(payload['players'])} players, {len(moves)} club changes")


def _compact(result):
    return {
        "rate": round(result["estimated_rate_per_90"], 4),
        "relative": round(result["role_relative"], 3),
        "mapping_sd": round(result["uncertainty"]["mapping_log_sd"], 4),
        "local_sd": round(result["uncertainty"]["player_local_log_sd"], 4),
        "total_sd": round(result["uncertainty"]["total_log_sd"], 4),
        "contributions": [
            [c["feature"], round(c["raw_value"], 3), round(c["coefficient"], 3), round(c["log_contribution"], 3)]
            for c in result["contributions"]
        ],
    }


if __name__ == "__main__":
    main()
