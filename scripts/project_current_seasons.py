"""Create an immutable M7 projection of every division and a matched sensitivity snapshot."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from epl_forecast.artifacts import execution_provenance, write_csv
from epl_forecast.cli import fitted_model, load_config
from epl_forecast.competitions import COMPETITION_IDS
from epl_forecast.competitions import competition as competition_info
from epl_forecast.datasets import Dataset, timestamp
from epl_forecast.live import LONDON, load_live_season
from epl_forecast.research.current_projection import compare_forecasts, noise_flags
from epl_forecast.research.uncertainty_ladder import MatchedStateMixture
from epl_forecast.sanctions import load_registry
from epl_forecast.simulation import simulate_season
from epl_forecast.storage import file_hash, json_bytes, sha256_bytes, write_json

COMPETITIONS = COMPETITION_IDS
MODEL_ID = "M7-xg-v1"
VARIANTS = {
    "full_m7": {},
    "posterior_mean": {"posterior": False},
    "no_future_innovations": {"innovations": False},
}


def configured_model(competition, cutoff):
    config = load_config(Path("configs/xg_quality_tilt.toml"))
    config["competition_id"] = competition
    for spec in config["models"]:
        spec.setdefault("parameters", {})["competition_id"] = competition
        if spec["id"] == MODEL_ID:
            spec["parameters"]["data_cutoff"] = cutoff.isoformat()
    return config


def previous_teams(matches, competition, season):
    year = int(season[:4])
    prior = f"{year - 1}-{year}"
    return {
        team
        for match in matches
        if match.fixture.competition_id == competition and match.fixture.season_id == prior
        for team in (match.fixture.home_team_id, match.fixture.away_team_id)
    }


def compact_snapshot(forecast, names, variant):
    return {
        key: forecast[key]
        for key in (
            "competition_id",
            "season_id",
            "as_of",
            "results_observed_at",
            "simulations",
            "seed",
            "played_matches",
            "remaining_matches",
            "state_uncertainty",
            "future_state_evolution",
            "ranking_rules",
            "ranking_rules_evidence",
            "playoff_model",
            "point_adjustments",
            "assumptions",
        )
    } | {
        "variant": variant,
        "teams": [{"team_name": names[row["team_id"]], **row} for row in forecast["teams"]],
    }


def table_rows(snapshot):
    rows = []
    for team in sorted(snapshot["teams"], key=lambda row: row["mean_position"]):
        row = {
            "competition_id": snapshot["competition_id"],
            "season_id": snapshot["season_id"],
            "forecast_timestamp": snapshot["results_observed_at"],
            "team_id": team["team_id"],
            "team_name": team["team_name"],
            "expected_rank": team["mean_position"],
            "median_rank": team["median_position"],
            "expected_points": team["mean_points"],
            "median_points": team["median_points"],
        }
        for target in ("position", "points"):
            for level in (50, 80, 90):
                row[f"{target}_{level}_lower"], row[f"{target}_{level}_upper"] = team[
                    f"{target}_intervals"
                ][str(level)]
        row.update({key: value for key, value in team.items() if key.endswith("_probability")})
        rows.append(row)
    return rows


def probability_rows(snapshot):
    return [
        {
            "competition_id": snapshot["competition_id"],
            "season_id": snapshot["season_id"],
            "forecast_timestamp": snapshot["results_observed_at"],
            "team_id": team["team_id"],
            "team_name": team["team_name"],
            "position": position,
            "probability": probability,
        }
        for team in snapshot["teams"]
        for position, probability in enumerate(team["position_probabilities"], 1)
    ]


def fields(rows):
    return list(dict.fromkeys(key for row in rows for key in row))


def heatmap(snapshot, destination):
    teams = sorted(snapshot["teams"], key=lambda row: row["mean_position"])
    values = np.array([row["position_probabilities"] for row in teams])
    fig, axis = plt.subplots(figsize=(12, max(7, len(teams) * 0.34)))
    image = axis.imshow(values, aspect="auto", cmap="YlGnBu", vmin=0)
    axis.set_xticks(range(len(teams)), range(1, len(teams) + 1))
    axis.set_yticks(range(len(teams)), [row["team_name"] for row in teams])
    axis.set_xlabel("Final position")
    axis.set_title(
        f"{snapshot['competition_id']} {snapshot['season_id']} M7 final-rank probabilities"
    )
    fig.colorbar(image, ax=axis, label="Probability")
    fig.tight_layout()
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def report(snapshots, sensitivity, simulations, seed, cutoff):
    lines = [
        "# Current M7 season projection",
        "",
        f"Information cutoff: `{cutoff.isoformat()}`. Simulations: {simulations:,}. Seed: {seed}.",
        "M7 is the primary structural surface; market pooling is not used.",
        "",
    ]
    for snapshot in snapshots:
        promotion = "promotion_probability" in snapshot["teams"][0]
        lines.extend(
            [
                f"## {competition_info(snapshot['competition_id']).name}",
                "",
                (
                    "| Team | Exp rank | Median | 90% rank | Exp pts | 90% pts | Auto | Playoff | Promotion | Relegation |"
                    if promotion
                    else "| Team | Exp rank | Median | 90% rank | Exp pts | 90% pts | Title | Top five | Relegation |"
                ),
                (
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
                    if promotion
                    else "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
                ),
            ]
        )
        for team in sorted(snapshot["teams"], key=lambda row: row["mean_position"]):
            values = [
                team["team_name"],
                f"{team['mean_position']:.2f}",
                str(team["median_position"]),
                "–".join(map(str, team["position_intervals"]["90"])),
                f"{team['mean_points']:.1f}",
                "–".join(map(str, team["points_intervals"]["90"])),
            ]
            if promotion:
                values.extend(
                    f"{team[key]:.1%}"
                    for key in (
                        "automatic_promotion_probability",
                        "playoff_qualification_probability",
                        "promotion_probability",
                        "relegation_probability",
                    )
                )
            else:
                values.extend(
                    f"{team[key]:.1%}"
                    for key in (
                        "title_probability",
                        "top_five_probability",
                        "relegation_probability",
                    )
                )
            lines.append("| " + " | ".join(values) + " |")
        lines.extend(
            ["", f"![Rank probability heatmap]({snapshot['competition_id']}-heatmap.png)", ""]
        )
    lines.extend(
        [
            "## Matched uncertainty sensitivity",
            "",
            "Distances compare each rank PMF with full M7. The Monte Carlo row is an independent full-M7 rerun; `teams above noise` counts Wasserstein distances larger than that team’s rerun distance.",
            "",
            "| Competition | Variant | Median rank W1 | Max rank W1 | Mean 90% width change | Teams above noise |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for competition in COMPETITIONS:
        variants = sorted(
            {row["variant"] for row in sensitivity if row["competition_id"] == competition}
        )
        for variant in variants:
            rows = [
                row
                for row in sensitivity
                if row["competition_id"] == competition and row["variant"] == variant
            ]
            lines.append(
                f"| {competition} | {variant} | {np.median([r['rank_wasserstein'] for r in rows]):.3f} | "
                f"{max(r['rank_wasserstein'] for r in rows):.3f} | "
                f"{np.mean([r['rank_interval_90_width_change'] for r in rows]):+.2f} | "
                f"{sum(r['rank_wasserstein_exceeds_mc_noise'] for r in rows)}/{len(rows)} |"
            )
    lines.extend(
        [
            "",
            "The full CSV reports team-level expected-rank changes, 50/80/90% width changes, event-probability changes, Wasserstein distance and total variation, with Monte Carlo-noise flags.",
            "",
            "EFL postseason probabilities simulate the edition-specific bracket after every regular-season path. The retained rules do not resolve extra-time probabilities, neutral-site scoring, or semi-final leg order, so the explicit approximations recorded in the JSON remain part of the forecast definition.",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff", type=timestamp, required=True)
    parser.add_argument("--season", default="2026-2027")
    parser.add_argument("--simulations", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=20260910)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("Projection output must be a new or empty directory")
    args.output.mkdir(parents=True, exist_ok=True)
    cutoff_day = args.cutoff.astimezone(LONDON).date()
    data = Dataset(args.data, args.cutoff)
    try:
        matches = data.matches()
        provenance = data.provenance()
        sanctions = load_registry(data)
    finally:
        data.close()
    manifest = {
        "schema_version": 1,
        "purpose": "immutable current M7 season-rank projection and matched uncertainty sensitivity",
        "forecast_timestamp": args.cutoff.isoformat(),
        "model_cutoff_london_date": str(cutoff_day),
        "season_id": args.season,
        "competitions": list(COMPETITIONS),
        "model_id": MODEL_ID,
        "simulations": args.simulations,
        "seed": args.seed,
        "variants": VARIANTS,
        "mc_replication_seed": args.seed + 1_000_003,
        "data_provenance_sha256": sha256_bytes(json_bytes(provenance)),
        "data_manifest_count": len(provenance["batches"]),
        "execution": execution_provenance(),
        "point_adjustments": {
            competition: sanctions.known_adjustments(competition, args.season, cutoff_day)
            for competition in COMPETITIONS
        },
        "configs": {},
    }
    write_json(args.output / "data_provenance.json", provenance)
    snapshots, sensitivity, noise_rows = [], [], []
    for competition_index, competition in enumerate(COMPETITIONS):
        live = load_live_season(args.data, args.cutoff, competition, args.season)
        adjustments = manifest["point_adjustments"][competition]
        config = configured_model(competition, args.cutoff)
        manifest["configs"][competition] = config
        model, _, training = fitted_model(matches, config, MODEL_ID, cutoff_day)
        promoted = set(live.teams) - previous_teams(matches, competition, args.season)
        variants = dict(VARIANTS)
        if competition == "eng-premier-league":
            variants["promoted_posterior_mean"] = {"fixed_teams": promoted}
        forecasts = {}
        for variant, switches in variants.items():
            forecast_model = MatchedStateMixture(
                model,
                live.teams,
                args.season,
                posterior=switches.get("posterior", True),
                evolution=True,
                innovations=switches.get("innovations", True),
                fixed_teams=switches.get("fixed_teams", ()),
            )
            forecast = simulate_season(
                forecast_model,
                live.played,
                live.remaining,
                list(live.teams),
                cutoff_day,
                args.simulations,
                args.seed + competition_index * 100,
                adjustments,
                results_observed_at=live.observed_at,
            )
            forecast["uncertainty_variant"] = variant
            forecasts[variant] = forecast
            write_json(args.output / "forecasts" / f"{competition}-{variant}.json", forecast)
        replicate_model = MatchedStateMixture(model, live.teams, args.season)
        replicate = simulate_season(
            replicate_model,
            live.played,
            live.remaining,
            list(live.teams),
            cutoff_day,
            args.simulations,
            manifest["mc_replication_seed"] + competition_index,
            adjustments,
            results_observed_at=live.observed_at,
        )
        baseline = forecasts["full_m7"]
        noise_rows.extend(compare_forecasts(replicate, baseline, live.teams, "mc_replication"))
        for variant, forecast in forecasts.items():
            if variant != "full_m7":
                sensitivity.extend(compare_forecasts(forecast, baseline, live.teams, variant))
        snapshot = compact_snapshot(baseline, live.teams, "full_m7")
        snapshot["training_matches"] = len(training)
        snapshot["promoted_entry_teams"] = sorted(promoted)
        snapshots.append(snapshot)
        heatmap(snapshot, args.output / f"{competition}-heatmap.png")
    noise_flags(sensitivity, noise_rows)
    write_json(args.output / "snapshot.json", {"manifest": manifest, "forecasts": snapshots})
    write_json(args.output / "manifest.json", manifest)
    tables = [row for snapshot in snapshots for row in table_rows(snapshot)]
    probabilities = [row for snapshot in snapshots for row in probability_rows(snapshot)]
    write_csv(args.output / "table.csv", fields(tables), tables)
    write_csv(args.output / "rank_probabilities.csv", fields(probabilities), probabilities)
    write_csv(args.output / "sensitivity.csv", fields(sensitivity), sensitivity)
    write_csv(args.output / "mc_noise.csv", fields(noise_rows), noise_rows)
    (args.output / "report.md").write_text(
        report(snapshots, sensitivity, args.simulations, args.seed, args.cutoff)
    )
    hashes = {
        str(path.relative_to(args.output)): file_hash(path)
        for path in sorted(args.output.rglob("*"))
        if path.is_file()
    }
    write_json(args.output / "completion.json", {"files": hashes})
    print(args.output / "report.md")


if __name__ == "__main__":
    main()
