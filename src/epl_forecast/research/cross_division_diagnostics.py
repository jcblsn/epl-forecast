"""Known-state mechanics checks for the cross-division club-state candidate."""

from collections import defaultdict
from datetime import date
from typing import NamedTuple

import numpy as np

from epl_forecast.models.cross_division import CrossDivisionQualityTilt, CrossDivisionXG
from epl_forecast.models.promotion import CHAMPIONSHIP, PL
from epl_forecast.schema import Fixture, Match, fixture_id

TRUE_BASE = np.log(1.35)
TRUE_HOME = 0.24
TRUE_SCORING_LEVEL = -0.20


class DivisionHistory(NamedTuple):
    matches: list
    observations: list
    quality: dict
    tilt: dict
    transitions: list

    def true_log_rates(self, fixture):
        offset = TRUE_SCORING_LEVEL if fixture.competition_id == CHAMPIONSHIP else 0.0
        home, away = fixture.home_team_id, fixture.away_team_id
        return np.array(
            [
                TRUE_BASE
                + TRUE_HOME
                + offset
                + self.quality[home]
                + self.tilt[home]
                - self.quality[away]
                + self.tilt[away],
                TRUE_BASE
                + offset
                + self.quality[away]
                + self.tilt[away]
                - self.quality[home]
                + self.tilt[home],
            ]
        )


def two_division_history(
    seed,
    seasons=4,
    clubs=10,
    crossings=3,
    level=TRUE_SCORING_LEVEL,
    quality_sd=0.22,
    tilt_sd=0.10,
    chance_probability=0.2,
    quality_gap=0.0,
):
    """Generate both divisions from one club-state scale and a known scoring level.

    `quality_gap` plants an absolute strength difference between the two club
    populations while each club keeps its own latent identity when it crosses.
    That is the cross-division problem the persistent state is meant to solve,
    and it is distinct from the scoring-level difference `level` plants.
    """
    rng = np.random.default_rng(seed)
    top = [f"pl{i}" for i in range(clubs)]
    lower = [f"ch{i}" for i in range(clubs)]
    quality = {t: rng.normal(0.0, quality_sd) for t in top}
    quality.update({t: rng.normal(-quality_gap, quality_sd) for t in lower})
    tilt = {t: rng.normal(0.0, tilt_sd) for t in top + lower}
    matches, observations, transitions, start = [], [], [], date(2018, 8, 1)
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
        next_season = f"{year + 1}-{year + 2}"
        for k in range(crossings):
            promoted, relegated = lower[k], top[-1 - k]
            top[-1 - k], lower[k] = promoted, relegated
            transitions.append({"season_id": next_season, "team_id": promoted, "to": PL})
            transitions.append({"season_id": next_season, "team_id": relegated, "to": CHAMPIONSHIP})
    return DivisionHistory(matches, observations, quality, tilt, transitions)


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
        history = two_division_history(
            seed, seasons=seasons, crossings=crossings, chance_probability=chance_probability
        )
        matches, observations, quality = history.matches, history.observations, history.quality
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
            results[name, "level_error"].append(
                float(model.division_scoring_level - TRUE_SCORING_LEVEL)
            )
            results[name, "level_sd"].append(level_sd)
            results[name, "level_covered"].append(
                float(abs(model.division_scoring_level - TRUE_SCORING_LEVEL) <= 1.959964 * level_sd)
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
        "true_division_scoring_level": TRUE_SCORING_LEVEL,
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
            matches = two_division_history(seed, seasons=seasons, crossings=crossings).matches
            model = CrossDivisionQualityTilt(independent_poisson=True, **DYNAMICS).fit(
                matches, _cutoff(seasons)
            )
            sds.append(float(np.sqrt(model.covariance[2, 2])))
            errors.append(float(model.division_scoring_level - TRUE_SCORING_LEVEL))
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
    matches = two_division_history(seed, seasons=seasons).matches
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


def promotion_slope_audit(matches, as_of, target_season):
    """How far a real promoted club's state travels: unit slope is M9's assumption.

    The cross-division state transports a club's Championship state into the
    Premier League unchanged apart from one shared division level, which is a
    slope of one in both dimensions. The retained promotion bridge estimates that
    slope from realized promoted cohorts instead.
    """
    from epl_forecast.models.promotion import PromotionBridge

    eligible = [
        m
        for m in matches
        if m.fixture.competition_id in (PL, CHAMPIONSHIP) and m.available_on <= as_of
    ]
    bridge = PromotionBridge(eligible, as_of, target_season)
    report = bridge.diagnostics()
    for block in report["dimensions"].values():
        slope_sd = block["coefficient_sd"][1]
        block["standard_errors_from_unit_slope"] = float((1.0 - block["slope"]) / slope_sd)
    report["interpretation"] = (
        "M9 assumes a slope of one in both dimensions; the cohorts do not support that"
    )
    return report


def promotion_calibration(
    replicates=20,
    seasons=5,
    crossings=3,
    quality_gap=0.45,
    first_matches=10,
    chance_probability=0.2,
):
    """Are a promoted club's first forecasts in its new division calibrated?

    Both club populations are drawn with a planted absolute strength gap while
    each club keeps its identity across the divide. A model that carries the
    state without compressing it should show a positive strength bias on newly
    promoted clubs; the errors here are in true log rate, not in loss.
    """
    errors = defaultdict(list)
    for seed in range(replicates):
        history = two_division_history(
            seed,
            seasons=seasons,
            crossings=crossings,
            quality_gap=quality_gap,
            chance_probability=chance_probability,
        )
        moved = {(row["team_id"], row["season_id"]): row["to"] for row in history.transitions}
        models = {
            "goals_only": CrossDivisionQualityTilt(independent_poisson=True, **DYNAMICS),
            "goals_xg": CrossDivisionXG(history.observations, chance_probability, **DYNAMICS),
        }
        counted = defaultdict(int)
        targets = []
        for match in sorted(
            history.matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id)
        ):
            fixture = match.fixture
            for team in (fixture.home_team_id, fixture.away_team_id):
                destination = moved.get((team, fixture.season_id))
                if destination != fixture.competition_id:
                    continue
                counted[team, fixture.season_id] += 1
                if counted[team, fixture.season_id] <= first_matches:
                    targets.append((fixture, team, destination))
        for cutoff_fixture, team, destination in targets:
            training = [m for m in history.matches if m.available_on <= cutoff_fixture.match_date]
            if len(training) < 200:
                continue
            side = 0 if cutoff_fixture.home_team_id == team else 1
            for name, model in models.items():
                model.fit(training, cutoff_fixture.match_date)
                predicted = model.forecast_moments(cutoff_fixture)[0]
                truth = history.true_log_rates(cutoff_fixture)
                label = "promoted" if destination == PL else "relegated"
                errors[name, label].append(float(predicted[side] - truth[side]))
                errors[name, "all_transitions"].append(float(predicted[side] - truth[side]))
    rows = []
    for (name, label), values in sorted(errors.items()):
        values = np.array(values)
        rows.append(
            {
                "model": name,
                "slice": label,
                "team_matches": len(values),
                "mean_log_rate_error": float(values.mean()),
                "standard_error": float(values.std(ddof=1) / np.sqrt(len(values))),
                "root_mean_squared_error": float(np.sqrt(np.mean(values**2))),
            }
        )
    return {
        "scope": "planted absolute club-strength gap between divisions, identities preserved",
        "replicates": replicates,
        "quality_gap": quality_gap,
        "first_matches_after_transition": first_matches,
        "interpretation": (
            "a positive promoted error means the carried state overstates the club's "
            "strength in its new division"
        ),
        "results": rows,
    }


def scoring_level_prior_sensitivity(matches, as_of, observations=None, chance_probability=0.2):
    """How much does the fitted division scoring level depend on its own prior?

    The uncentered representation leaves the mean of club Tilt able to trade off
    against a league scoring level, so this reports the posterior's movement under
    deliberately different priors rather than assuming the quantity is pinned.
    """
    eligible = [
        m
        for m in matches
        if m.fixture.competition_id in (PL, CHAMPIONSHIP) and m.available_on <= as_of
    ]
    rows = []
    # Tilt enters both teams' rates with the same sign, so its population mean is the
    # quantity that trades off against a league scoring level. Vary that prior too.
    for level_sd in (0.15, 0.30, 0.60):
        for team_sd in (0.25, 0.40, 0.60):
            for tilt_sd in (0.035, 0.07, 0.14):
                dynamics = {**DYNAMICS, "tilt_sd": tilt_sd}
                if observations is None:
                    model = CrossDivisionQualityTilt(
                        division_scoring_level_sd=level_sd,
                        initial_team_sd=team_sd,
                        independent_poisson=True,
                        **dynamics,
                    )
                else:
                    model = CrossDivisionXG(
                        observations,
                        chance_probability,
                        division_scoring_level_sd=level_sd,
                        initial_team_sd=team_sd,
                        **dynamics,
                    )
                model.fit(eligible, as_of)
                summary = model.division_summary()
                rows.append(
                    {
                        "division_scoring_level_sd": level_sd,
                        "initial_team_sd": team_sd,
                        "tilt_sd": tilt_sd,
                        "championship_scoring_level": summary["championship_scoring_level"],
                        "championship_scoring_level_sd": summary["championship_scoring_level_sd"],
                        "home_advantage": summary["home_advantage"],
                        "mean_club_tilt": float(
                            np.mean(model.mean[model.league_dimensions + 1 :: 2])
                        ),
                    }
                )
    levels = np.array([row["championship_scoring_level"] for row in rows])
    posterior_sd = float(np.mean([row["championship_scoring_level_sd"] for row in rows]))
    home = np.array([row["home_advantage"] for row in rows])
    return {
        "as_of": str(as_of),
        "observations": "goals only" if observations is None else "goals and xG",
        "grid": rows,
        "championship_scoring_level_range": float(levels.max() - levels.min()),
        "championship_scoring_level_range_in_posterior_sd": float(
            (levels.max() - levels.min()) / posterior_sd
        ),
        "home_advantage_range": float(home.max() - home.min()),
        "mean_club_tilt_range": float(
            max(r["mean_club_tilt"] for r in rows) - min(r["mean_club_tilt"] for r in rows)
        ),
        "interpretation": (
            "a range comparable to or larger than the reported posterior SD means the "
            "quantity is prior-dependent in this coordinate and should not be read "
            "as a settled latent value"
        ),
    }
