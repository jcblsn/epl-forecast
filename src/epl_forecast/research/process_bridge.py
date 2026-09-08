"""Pooled Championship shot summaries mapped to promoted PL process priors."""

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from epl_forecast.datasets import Dataset
from epl_forecast.models.promotion import PromotionBridge, TeamPrior, fit_bridge_regression


def shot_summaries(data_root):
    data = Dataset(data_root)
    result = {}
    try:
        rows = data.rows(
            "SELECT f.season_id, f.match_date, f.match_id, f.home_team_id, "
            "f.away_team_id, h.shots AS hs, a.shots AS ass, h.source_sha256 FROM fixtures f "
            "JOIN team_process h ON f.match_id=h.match_id AND f.home_team_id=h.team_id "
            "JOIN team_process a ON f.match_id=a.match_id AND f.away_team_id=a.team_id "
            "WHERE f.provider='football_data' AND h.provider='football_data' "
            "AND a.provider='football_data' AND f.competition_id='eng-championship' "
            "AND f.season_id>='2013-2014' AND h.shots IS NOT NULL AND a.shots IS NOT NULL "
            "AND h.shots_on_target<=h.shots AND a.shots_on_target<=a.shots "
            "ORDER BY f.season_id, f.match_date, f.match_id"
        )
        seasons = defaultdict(list)
        for row in rows:
            seasons[row["season_id"]].append(row)
        for season, games in seasons.items():
            average = np.mean([[r["hs"], r["ass"]] for r in games], axis=0)
            groups = defaultdict(list)
            for r in games:
                groups[r["home_team_id"]].append([r["hs"], r["ass"], 1])
                groups[r["away_team_id"]].append([r["ass"], r["hs"], 0])
            teams = {}
            for team, values in groups.items():
                values = np.array(values)
                home = values[:, 2]
                exposure = np.column_stack(
                    [
                        home * average[0] + (1 - home) * average[1],
                        home * average[1] + (1 - home) * average[0],
                    ]
                )
                ratios = values[:, :2] / exposure
                relative = ratios.mean(axis=0)
                teams[team] = {
                    "mean": np.log(relative) * [1, -1],
                    "variance": ratios.var(axis=0, ddof=1) / (len(values) * relative**2),
                    "matches": len(values),
                }
            result[season] = {
                "teams": teams,
                "available_on": max(r["match_date"] for r in games) + timedelta(days=1),
                "sha256": games[0]["source_sha256"],
            }
        return result
    finally:
        data.close()


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


def bridge_diagnostic(matches, records, data_root=Path("data")):
    sources = shot_summaries(data_root)
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
        "canonical_data_root": str(data_root),
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
