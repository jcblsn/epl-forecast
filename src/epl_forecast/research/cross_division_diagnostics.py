"""Known-state mechanics checks for the cross-division club-state candidate."""

from collections import defaultdict
from datetime import date

import numpy as np

from epl_forecast.models.cross_division import CrossDivisionQualityTilt, CrossDivisionXG
from epl_forecast.models.promotion import CHAMPIONSHIP, PL
from epl_forecast.schema import Fixture, Match, fixture_id

TRUE_BASE = np.log(1.35)
TRUE_HOME = 0.24
TRUE_LEVEL = -0.20


def two_division_history(
    seed,
    seasons=4,
    clubs=10,
    crossings=3,
    level=TRUE_LEVEL,
    quality_sd=0.22,
    tilt_sd=0.10,
    chance_probability=0.2,
):
    """Generate both divisions from one club-state scale and a known division level."""
    rng = np.random.default_rng(seed)
    top = [f"pl{i}" for i in range(clubs)]
    lower = [f"ch{i}" for i in range(clubs)]
    quality = {t: rng.normal(0.0, quality_sd) for t in top + lower}
    tilt = {t: rng.normal(0.0, tilt_sd) for t in top + lower}
    matches, observations, start = [], [], date(2018, 8, 1)
    for year in range(2018, 2018 + seasons):
        season = f"{year}-{year + 1}"
        for competition, teams, offset in ((PL, top, 0.0), (CHAMPIONSHIP, lower, level)):
            pairs = [(h, a) for h in teams for a in teams if h != a]
            for index, (home, away) in enumerate(pairs):
                day = date.fromordinal(start.toordinal() + index // 4)
                fixture = Fixture(
                    fixture_id(competition, season, home, away),
                    competition,
                    season,
                    day,
                    home,
                    away,
                )
                rates = np.exp(
                    [
                        TRUE_BASE
                        + TRUE_HOME
                        + offset
                        + quality[home]
                        + tilt[home]
                        - quality[away]
                        + tilt[away],
                        TRUE_BASE
                        + offset
                        + quality[away]
                        + tilt[away]
                        - quality[home]
                        + tilt[home],
                    ]
                )
                opportunities = rng.poisson(rates / chance_probability)
                goals = rng.binomial(opportunities, chance_probability)
                xg = rng.gamma(opportunities, chance_probability)
                match = Match(fixture, int(goals[0]), int(goals[1]))
                matches.append(match)
                observations.append(
                    {
                        "match_id": fixture.match_id,
                        "match_date": str(day),
                        "available_on": str(match.available_on),
                        "home_goals": match.home_goals,
                        "away_goals": match.away_goals,
                        "home_xg": float(xg[0]),
                        "away_xg": float(xg[1]),
                    }
                )
        start = date(year + 1, 8, 1)
        for k in range(crossings):
            top[-1 - k], lower[k] = lower[k], top[-1 - k]
    return matches, observations, quality, tilt


DYNAMICS = {
    "quality_retention": 0.85,
    "quality_sd": 0.09,
    "tilt_retention": 0.5,
    "tilt_sd": 0.07,
}


def _cutoff(seasons):
    return date(2018 + seasons, 8, 1)


def recovery_checks(replicates=30, seasons=4, crossings=3, chance_probability=0.2):
    """Recover a known division level, home advantage and club states from goals."""
    results = defaultdict(list)
    for seed in range(replicates):
        matches, observations, quality, _ = two_division_history(
            seed, seasons=seasons, crossings=crossings, chance_probability=chance_probability
        )
        cutoff = _cutoff(seasons)
        models = {
            "goals_only": CrossDivisionQualityTilt(independent_poisson=True, **DYNAMICS),
            "goals_xg": CrossDivisionXG(observations, chance_probability, **DYNAMICS),
        }
        for name, model in models.items():
            model.fit(matches, cutoff)
            level_sd = float(np.sqrt(model.covariance[2, 2]))
            home_sd = float(np.sqrt(model.covariance[1, 1]))
            order = list(model.team_index)
            estimated = model.mean[model.league_dimensions :: 2]
            truth = np.array([quality[t] for t in order])
            results[name, "level_error"].append(float(model.division_level - TRUE_LEVEL))
            results[name, "level_sd"].append(level_sd)
            results[name, "level_covered"].append(
                float(abs(model.division_level - TRUE_LEVEL) <= 1.959964 * level_sd)
            )
            results[name, "home_error"].append(float(model.mean[1] - TRUE_HOME))
            results[name, "home_covered"].append(
                float(abs(model.mean[1] - TRUE_HOME) <= 1.959964 * home_sd)
            )
            results[name, "quality_correlation"].append(
                float(np.corrcoef(estimated, truth - truth.mean())[0, 1])
            )
            results[name, "quality_mse"].append(
                float(np.mean((estimated - (truth - truth.mean())) ** 2))
            )
    rows = []
    for name in ("goals_only", "goals_xg"):
        row = {"model": name, "replicates": replicates}
        for metric in (
            "level_error",
            "level_sd",
            "level_covered",
            "home_error",
            "home_covered",
            "quality_correlation",
            "quality_mse",
        ):
            values = np.array(results[name, metric])
            row[metric] = float(values.mean())
            row[f"{metric}_replicate_se"] = float(values.std(ddof=1) / np.sqrt(replicates))
        rows.append(row)
    paired = np.array(results["goals_xg", "quality_mse"]) - results["goals_only", "quality_mse"]
    return {
        "scope": "synthetic two-division opportunity process with a known common club scale",
        "seasons": seasons,
        "crossings_per_season": crossings,
        "chance_probability": chance_probability,
        "true_division_level": TRUE_LEVEL,
        "true_home_advantage": TRUE_HOME,
        "results": rows,
        "xg_minus_goals_quality_mse": {
            "mean": float(paired.mean()),
            "replicate_standard_error": float(paired.std(ddof=1) / np.sqrt(replicates)),
        },
    }


def crossing_sensitivity(replicates=12, seasons=4, counts=(0, 1, 3, 5)):
    """Observed transitions, not the prior, are what identify the common scale."""
    rows = []
    for crossings in counts:
        sds, errors = [], []
        for seed in range(replicates):
            matches, _, _, _ = two_division_history(seed, seasons=seasons, crossings=crossings)
            model = CrossDivisionQualityTilt(independent_poisson=True, **DYNAMICS).fit(
                matches, _cutoff(seasons)
            )
            sds.append(float(np.sqrt(model.covariance[2, 2])))
            errors.append(float(model.division_level - TRUE_LEVEL))
        rows.append(
            {
                "crossings_per_season": crossings,
                "replicates": replicates,
                "level_posterior_sd": float(np.mean(sds)),
                "level_root_mean_squared_error": float(np.sqrt(np.mean(np.square(errors)))),
            }
        )
    return rows


def coordinate_equivalence(seed=0, seasons=3):
    """An attack/defence rotation reproduces the Quality/Tilt forecast exactly."""
    matches, _, _, _ = two_division_history(seed, seasons=seasons)
    cutoff = _cutoff(seasons)
    model = CrossDivisionQualityTilt(independent_poisson=True, **DYNAMICS).fit(matches, cutoff)
    season = f"{2018 + seasons}-{2019 + seasons}"
    fixture = Fixture(fixture_id(PL, season, "pl0", "pl1"), PL, season, cutoff, "pl0", "pl1")
    quality_mean, quality_covariance = model.forecast_moments(fixture)
    rotation = np.eye(len(model.mean))
    for index in range(len(model.team_index)):
        start = model.league_dimensions + 2 * index
        rotation[start : start + 2, start : start + 2] = [[1.0, 1.0], [1.0, -1.0]]
    design = np.zeros((2, len(model.mean)))
    design[:, : model.league_dimensions] = model._league_design(fixture)
    for team, transform in zip(
        (fixture.home_team_id, fixture.away_team_id),
        (np.array([[1, 0], [0, -1]]), np.array([[0, -1], [1, 0]])),
        strict=True,
    ):
        design[:, model._team_slice(team)] = transform
    return {
        "mean_max_absolute_difference": float(
            np.max(np.abs(design @ (rotation @ model.mean) - quality_mean))
        ),
        "covariance_max_absolute_difference": float(
            np.max(
                np.abs(
                    design @ (rotation @ model.covariance @ rotation.T) @ design.T
                    - quality_covariance
                )
            )
        ),
        "interpretation": "one state in two coordinates, not a second model family",
    }
