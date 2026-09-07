"""Pooled Championship shot summaries mapped to promoted PL process priors."""

from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

from epl_forecast.data.normalize import normalize_rows, team_aliases
from epl_forecast.data.sources import csv_rows, read_snapshot
from epl_forecast.models.promotion import PromotionBridge, TeamPrior, fit_bridge_regression
from epl_forecast.storage import file_hash


def shot_summaries(snapshot_path, data_root):
    aliases = team_aliases()
    result = {}
    for entry in read_snapshot(snapshot_path)["files"]:
        if entry["division"] != "E1" or entry["season_start"] < 2013:
            continue
        path = data_root / entry["path"]
        if file_hash(path) != entry["sha256"]:
            raise ValueError("Championship raw checksum mismatch")
        payload = path.read_bytes()
        matches, _, _ = normalize_rows(payload, entry, aliases)
        raw = dict(csv_rows(payload)[1])
        groups = defaultdict(list)
        all_shots = []
        for match in matches:
            row = raw[match.source_row]
            if not all(row.get(f, "").isdigit() for f in ("HS", "AS", "HST", "AST")):
                continue
            hs, ass, ht, at = (int(row[f]) for f in ("HS", "AS", "HST", "AST"))
            if ht > hs or at > ass:
                continue
            all_shots.append([hs, ass])
            groups[match.fixture.home_team_id].append([hs, ass, 1])
            groups[match.fixture.away_team_id].append([ass, hs, 0])
        average = np.mean(all_shots, axis=0)
        teams = {}
        for team, rows in groups.items():
            values = np.array(rows)
            home = values[:, 2]
            exposure = np.column_stack(
                [
                    home * average[0] + (1 - home) * average[1],
                    home * average[1] + (1 - home) * average[0],
                ]
            )
            ratios = values[:, :2] / exposure
            relative = ratios.mean(axis=0)
            mean = np.log(relative) * [1, -1]
            variance = ratios.var(axis=0, ddof=1) / (len(rows) * relative**2)
            teams[team] = {"mean": mean, "variance": variance, "matches": len(rows)}
        result[entry["season_id"]] = {
            "teams": teams,
            "available_on": max(m.available_on for m in matches),
            "sha256": entry["sha256"],
        }
    return result


def process_cohorts(matches, records, sources):
    xg = {r["match_id"]: r for r in records}
    seasons = defaultdict(list)
    for match in matches:
        if match.fixture.competition_id == "eng-premier-league" and match.fixture.match_id in xg:
            seasons[match.fixture.season_id].append(match)
    result = []
    for season, games in sorted(seasons.items()):
        year = int(season[:4])
        source = sources.get(f"{year - 1}-{year}")
        if not source or len(games) != 380:
            continue
        league_xg = np.array(
            [[xg[m.fixture.match_id]["home_xg"], xg[m.fixture.match_id]["away_xg"]] for m in games]
        ).mean(axis=0)
        teams = {t for m in games for t in (m.fixture.home_team_id, m.fixture.away_team_id)}
        for team in sorted(teams & source["teams"].keys()):
            selected = sorted(
                [m for m in games if team in (m.fixture.home_team_id, m.fixture.away_team_id)],
                key=lambda m: m.fixture.match_date,
            )[:10]
            values, expected = [], []
            for match in selected:
                row = xg[match.fixture.match_id]
                home = match.fixture.home_team_id == team
                values.append(
                    [row["home_xg"], row["away_xg"]] if home else [row["away_xg"], row["home_xg"]]
                )
                expected.append(league_xg if home else league_xg[::-1])
            ratios = np.array(values) / np.array(expected)
            mean = ratios.mean(axis=0)
            variance = ratios.var(axis=0, ddof=1) / (len(selected) * mean**2)
            target = np.log(mean) * [1, -1]
            row = {
                "team_id": team,
                "season_id": season,
                "available_on": str(max(m.available_on for m in games)),
                "source_available_on": str(source["available_on"]),
                "target_first_match": str(selected[0].fixture.match_date),
                "target_last_match": str(selected[-1].fixture.match_date),
                "source_matches": source["teams"][team]["matches"],
            }
            for i, dimension in enumerate(("attack", "defense")):
                row[f"championship_{dimension}"] = float(source["teams"][team]["mean"][i])
                row[f"championship_{dimension}_variance"] = float(
                    source["teams"][team]["variance"][i]
                )
                row[f"entry_{dimension}"] = float(target[i])
                row[f"entry_{dimension}_variance"] = float(variance[i])
            result.append(row)
    return result


def shot_prior(cohorts, source, as_of, target_season):
    eligible = [
        r
        for r in cohorts
        if date.fromisoformat(r["available_on"]) <= as_of and r["season_id"] < target_season
    ]
    means, variances, coefficients = [], [], []
    for i, dimension in enumerate(("attack", "defense")):
        regression = fit_bridge_regression(eligible, dimension)
        x, xv = source["mean"][i], source["variance"][i]
        design = np.array([1, x])
        means.append(design @ regression.coefficients)
        variance = (
            regression.residual_sd**2
            + design @ regression.covariance @ design
            + xv * (regression.coefficients[1] ** 2 + regression.covariance[1, 1])
        )
        variances.append(max(0.25**2, variance))
        coefficients.append(regression.coefficients.tolist())
    return (
        TeamPrior(
            np.array(means), np.diag(variances), "post-2013 Championship shots process bridge"
        ),
        len(eligible),
        coefficients,
    )


def bridge_diagnostic(
    matches, records, snapshot_path=Path("configs/data_snapshot.json"), data_root=Path("data")
):
    sources = shot_summaries(snapshot_path, data_root)
    cohorts = process_cohorts(matches, records, sources)
    predictions = []
    for season in sorted({r["season_id"] for r in cohorts if r["season_id"] >= "2023-2024"}):
        year = int(season[:4])
        cutoff = date(year, 8, 1)
        source = sources[f"{year - 1}-{year}"]
        if source["available_on"] > cutoff:
            raise ValueError("Championship source was unavailable before season entry")
        baseline = PromotionBridge(matches, cutoff, season)
        for row in [r for r in cohorts if r["season_id"] == season]:
            team = row["team_id"]
            prior, training, coefficients = shot_prior(
                cohorts, source["teams"][team], cutoff, season
            )
            control = baseline.prior(team, use_performance=False)
            for name, state in [("shots_bridge", prior), ("frozen_population_bridge", control)]:
                target = np.array([row["entry_attack"], row["entry_defense"]])
                noise = np.array([row["entry_attack_variance"], row["entry_defense_variance"]])
                variance = np.diag(state.covariance) + noise
                error = state.mean - target
                predictions.append(
                    {
                        "model": name,
                        "team": team,
                        "season": season,
                        "as_of": str(cutoff),
                        "prior_mean": state.mean.tolist(),
                        "prior_variance": np.diag(state.covariance).tolist(),
                        "target_process_proxy": target.tolist(),
                        "proxy_variance": noise.tolist(),
                        "squared_error": float(np.mean(error**2)),
                        "proxy_nll": float(
                            np.mean(0.5 * (np.log(2 * np.pi * variance) + error**2 / variance))
                        ),
                        "proxy_coverage90": float(
                            np.mean(np.abs(error) <= 1.644853626951 * np.sqrt(variance))
                        ),
                        "training_cohorts": training
                        if name == "shots_bridge"
                        else len(baseline.cohorts),
                        "coefficients": coefficients if name == "shots_bridge" else None,
                    }
                )
    summary = []
    for name in ("shots_bridge", "frozen_population_bridge"):
        rows = [r for r in predictions if r["model"] == name]
        summary.append(
            {
                "model": name,
                "teams": len(rows),
                **{
                    k: float(np.mean([r[k] for r in rows]))
                    for k in ("squared_error", "proxy_nll", "proxy_coverage90")
                },
            }
        )
    return {
        "source_snapshot_sha256": file_hash(snapshot_path),
        "cohorts": cohorts,
        "predictions": predictions,
        "summary": summary,
        "scope": (
            "Pre-season priors scored against noisy first-ten PL xG proxies; "
            "not latent-state coverage or match-forecast evidence"
        ),
        "observation": (
            "Division/home-adjusted season shot ratios with sampling variance; "
            "pooled errors-in-variables bridge"
        ),
        "prior_sd_floor": 0.25,
        "excluded": "Pre-2013 source regime, missing shot rows, shots-on-target exceeding shots",
    }
