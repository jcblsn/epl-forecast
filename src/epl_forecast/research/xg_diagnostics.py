"""High-information scores and paired diagnostics for the team xG channel."""

from collections import defaultdict

import numpy as np
from scipy.special import gammaln, logsumexp
from scipy.stats import binom

from epl_forecast.models.poisson import PoissonMixture
from epl_forecast.models.xg_observation import ChanceObservation


def conditional_opportunities(rates, xg, p):
    """Return log p(xG|rate) and p(N|xG,rate), including the exact zero atom."""
    rates = np.asarray(rates)
    if not np.isfinite(xg) or xg < 0:
        raise ValueError("Conditioning xG must be finite and nonnegative")
    if xg == 0:
        return -rates / p, np.ones((len(rates), 1)), np.zeros(1)
    count = 128
    while True:
        n = np.arange(1, count + 1)
        terms = (
            n * np.log(rates[:, None])
            - rates[:, None] / p
            - xg / p
            + (n - 1) * np.log(xg)
            - 2 * n * np.log(p)
            - gammaln(n + 1)
            - gammaln(n)
        )
        normalizer = logsumexp(terms, axis=1)
        weights = np.exp(terms - normalizer[:, None])
        ratio = rates * xg / p**2 / (count * (count + 1))
        if np.all(ratio < 1) and np.max(weights[:, -1] * ratio / (1 - ratio)) < 1e-14:
            return normalizer, weights, n
        count *= 2
        if count > 8192:
            raise RuntimeError("Conditional opportunity series failed to converge")


class ConditionalXGScores:
    """Nondeployable p(goals|realized target xG, pre-match information).

    Reweights both Gaussian state quadrature and noise specifications by target
    xG evidence. No target goals are read when constructing the distribution.
    """

    def __init__(self, model, fixture, home_xg, away_xg):
        self.components = []
        members = getattr(model, "members", [model])
        weights = getattr(model, "weights", np.ones(1))
        for member, weight in zip(members, weights, strict=True):
            if weight == 0:
                continue
            state = PoissonMixture(*member.forecast_moments(fixture), member.quadrature_order)
            p = member.chance_probability
            lh, wh, nh = conditional_opportunities(state.home_rates, home_xg, p)
            la, wa, na = conditional_opportunities(state.away_rates, away_xg, p)
            log_prior = np.log(weight) + np.log(state.weights)
            self.components.append((state, p, log_prior, lh + la, wh, nh, wa, na))
        self.log_xg_evidence = float(
            logsumexp(np.concatenate([c[2] + c[3] for c in self.components]))
        )
        self.xg = home_xg, away_xg
        limit = 16
        while True:
            grid = self._grid(limit)
            if 1 - grid.sum() < 1e-12:
                break
            limit *= 2
            if limit > 512:
                raise RuntimeError("Conditional score grid tail exceeds tolerance")
        self._probabilities = grid
        self.tail_mass = max(0.0, 1 - float(grid.sum()))

    def _grid(self, limit):
        goals = np.arange(limit + 1)
        grid = np.zeros((limit + 1, limit + 1))
        for _, p, prior, evidence, wh, nh, wa, na in self.components:
            home = wh @ binom.pmf(goals[None, :], nh[:, None], p)
            away = wa @ binom.pmf(goals[None, :], na[:, None], p)
            weights = np.exp(prior + evidence - self.log_xg_evidence)
            grid += (home.T * weights) @ away
        return grid

    def outcome_probabilities(self):
        g = self._probabilities
        return tuple(np.array([np.tril(g, -1).sum(), np.trace(g), np.triu(g, 1).sum()]) / g.sum())

    def log_probability(self, home_goals, away_goals):
        if any(type(g) is not int or g < 0 for g in (home_goals, away_goals)):
            raise ValueError("Goals must be nonnegative integers")
        if any(x == 0 and g > 0 for x, g in zip(self.xg, (home_goals, away_goals), strict=True)):
            return -np.inf
        terms = []
        for state, p, prior, *_ in self.components:
            likelihood = ChanceObservation([home_goals, away_goals], self.xg, p)
            log_rates = np.log(np.column_stack([state.home_rates, state.away_rates]))
            terms.extend(prior + [likelihood(eta)[0] for eta in log_rates])
        return float(logsumexp(terms) - self.log_xg_evidence)

    def grid(self, max_goals=10):
        if type(max_goals) is not int or max_goals < 0:
            raise ValueError("max_goals must be a nonnegative integer")
        grid = self._grid(max_goals)
        return grid, max(0.0, 1 - float(grid.sum()))


def paired_blocks(left, right, seed=702, replicates=2000):
    """Paired calendar-week bootstrap; losses are correlated within a football week."""
    from datetime import date

    if set(left) != set(right) or not left:
        raise ValueError("Paired diagnostics require identical nonempty fixture sets")
    blocks = defaultdict(list)
    for key in sorted(left):
        row = left[key]
        day = date.fromisoformat(row["match_date"])
        iso = day.isocalendar()
        difference = -np.log(float(row[f"p_{dict(H='home', D='draw', A='away')[row['outcome']]}"]))
        other = right[key]
        if (other["match_date"], other["outcome"]) != (row["match_date"], row["outcome"]):
            raise ValueError("Paired rows disagree on date or outcome")
        difference += np.log(
            float(other[f"p_{dict(H='home', D='draw', A='away')[other['outcome']]}"])
        )
        blocks[iso.year, iso.week].append(difference)
    totals = np.array([sum(v) for v in blocks.values()])
    counts = np.array([len(v) for v in blocks.values()])
    indices = np.random.default_rng(seed).integers(len(blocks), size=(replicates, len(blocks)))
    boot = totals[indices].sum(axis=1) / counts[indices].sum(axis=1)
    return {
        "matches": len(left),
        "calendar_weeks": len(blocks),
        "replicates": replicates,
        "mean_outcome_loss_difference": float(totals.sum() / counts.sum()),
        "interval_95": np.quantile(boot, [0.025, 0.975]).tolist(),
    }


def adaptation_diagnostic(matches, replicates=40, seed=703):
    """Known-state abrupt Quality change: information diagnostic, not historical calibration."""
    from dataclasses import replace
    from datetime import date

    from epl_forecast.models.centered_quality_tilt import CenteredQualityTiltFilter
    from epl_forecast.models.quality_tilt import QualityTiltFilter
    from epl_forecast.models.xg_quality_tilt import XG_DYNAMICS, XGQualityTiltFilter
    from epl_forecast.research.quality_tilt_reference import prepare

    template = prepare(
        sorted(
            [
                m
                for m in matches
                if m.fixture.competition_id == "eng-premier-league"
                and m.fixture.season_id == "2024-2025"
            ],
            key=lambda m: (m.fixture.match_date, m.fixture.match_id),
        )[:120]
    )
    team = "arsenal"
    index = 2 + 2 * template["teams"].index(team)
    shock_day = date(2024, 9, 15)
    rng = np.random.default_rng(seed)
    errors = defaultdict(list)
    for _ in range(replicates):
        n = template["design"].shape[-1]
        state = (
            np.r_[np.log([1.2, 1.3]), np.zeros(n - 2)]
            + rng.normal(size=n) * np.r_[np.full(2, 0.25), np.full(n - 2, 0.4 / np.sqrt(2))]
        )
        process = QualityTiltFilter(**XG_DYNAMICS)
        truth, last_day, shifted = [], template["dates"][0], False
        for day_index, day in enumerate(template["dates"]):
            if day_index:
                decay, variance = process.transition((day - last_day).days / 365.25, n)
                active = template["active"][day_index - 1]
                decay[2:] = np.where(active, decay[2:], 1)
                variance[2:] = np.where(active, variance[2:], 0)
                state = state * decay + rng.normal(size=n) * np.sqrt(variance)
            if day >= shock_day and not shifted:
                state[index] += 0.35
                shifted = True
            truth.append(state.copy())
            last_day = day
        eta = np.einsum("mij,mj->mi", template["design"], np.array(truth)[template["day_index"]])
        opportunities = rng.poisson(np.exp(eta) / 0.2)
        goals, xg = rng.binomial(opportunities, 0.2), rng.gamma(opportunities, 0.2)
        generated, observations = [], []
        for m, g, x in zip(template["matches"], goals, xg, strict=True):
            game = replace(m, home_goals=int(g[0]), away_goals=int(g[1]))
            generated.append(game)
            observations.append(
                {
                    "match_id": game.fixture.match_id,
                    "provider": "understat",
                    "match_date": str(game.fixture.match_date),
                    "available_on": str(game.available_on),
                    "home_goals": game.home_goals,
                    "away_goals": game.away_goals,
                    "home_xg": float(x[0]),
                    "away_xg": float(x[1]),
                }
            )
        models = {
            "goals_only": CenteredQualityTiltFilter(**XG_DYNAMICS),
            "goals_xg": XGQualityTiltFilter(observations, 0.2, **XG_DYNAMICS),
        }
        replicate_errors = defaultdict(list)
        post = 0
        for i, game in enumerate(generated):
            fixture = game.fixture
            if team not in (fixture.home_team_id, fixture.away_team_id):
                continue
            prior = [m for m in generated if m.available_on <= fixture.match_date]
            if not prior:
                continue
            if fixture.match_date >= shock_day:
                post += 1
            label = (
                "pre_change" if post == 0 else ("first_three_after" if post <= 3 else "later_after")
            )
            for name, model in models.items():
                model.fit(prior, fixture.match_date)
                predicted = model.forecast_moments(fixture)[0]
                replicate_errors[name, label].extend((predicted - eta[i]) ** 2)
        for key, values in replicate_errors.items():
            errors[key].append(float(np.mean(values)))
    rows = [
        {
            "model": k[0],
            "slice": k[1],
            "replicates": len(v),
            "mean_log_rate_squared_error": float(np.mean(v)),
        }
        for k, v in sorted(errors.items())
    ]
    paired = []
    for label in sorted({k[1] for k in errors}):
        difference = np.array(errors["goals_xg", label]) - errors["goals_only", label]
        paired.append(
            {
                "slice": label,
                "xg_minus_goals_mse": float(difference.mean()),
                "replicate_standard_error": float(difference.std(ddof=1) / np.sqrt(replicates)),
            }
        )
    return {
        "seed": seed,
        "replicates": replicates,
        "matches_per_replicate": len(generated),
        "team": team,
        "quality_jump": 0.35,
        "change_date": str(shock_day),
        "scope": "Synthetic M7 opportunity observations; abrupt shift outside assumed OU dynamics",
        "results": rows,
        "paired": paired,
    }


def audit_forecast_archive(directory):
    import json
    from pathlib import Path

    from epl_forecast.datasets import timestamp
    from epl_forecast.storage import file_hash

    archive = json.loads((directory / "archive.json").read_text())
    for name, checksum in archive["files"].items():
        if file_hash(directory / name) != checksum:
            raise ValueError(f"Archive checksum mismatch: {directory / name}")
    forecast = json.loads((directory / "forecast.json").read_text())
    run = json.loads((directory / "run.json").read_text())
    for name, checksum in run.get("inputs", {}).items():
        if file_hash(Path(name)) != checksum:
            raise ValueError(f"Archived input checksum mismatch: {name}")
    ids = set(archive["forward_match_ids"])
    rows = {r["match_id"]: r for r in forecast["matches"]}
    if ids != set(rows) or len(rows) != len(forecast["matches"]):
        raise ValueError("Archive is not a complete unique pre-kickoff forecast set")
    archived_at = timestamp(archive["archived_at"])
    if timestamp(forecast["state_observed_at"]) > archived_at:
        raise ValueError("Source observation is later than archive")
    if (
        run.get("information_observed_at")
        and timestamp(run["information_observed_at"]) > archived_at
    ):
        raise ValueError("Player information is later than archive")
    for row in rows.values():
        if timestamp(row["kickoff_time"]) <= archived_at:
            raise ValueError("Forecast was not archived before kickoff")
        if not np.isclose(sum(row[k] for k in ("p_home", "p_draw", "p_away")), 1):
            raise ValueError("Invalid forecast probabilities")
        for team in row.get("player_quality", []):
            for specification in team["specifications"]:
                if not np.isclose(
                    sum(p["expected_minutes"] for p in specification["players"]), 990
                ):
                    raise ValueError("Archived lineup minutes are not coherent")
    simulation = forecast["simulation"]
    if simulation is None or simulation["remaining_matches"] != len(rows):
        raise ValueError("Season simulation does not cover forecast fixtures")
    frequencies = simulation["match_frequencies"]
    if len(frequencies) != len(rows) or {r["match_id"] for r in frequencies} != set(rows):
        raise ValueError("Simulated match frequencies do not cover every fixture once")
    teams = simulation["teams"]
    positions = np.array([r["position_probabilities"] for r in teams])
    if positions.shape != (20, 20) or not (
        np.allclose(positions.sum(axis=0), 1) and np.allclose(positions.sum(axis=1), 1)
    ):
        raise ValueError("Season position probabilities violate table constraints")
    for key, expected in (("title_probability", 1), ("relegation_probability", 3)):
        if not np.isclose(sum(r[key] for r in teams), expected):
            raise ValueError("Season event probabilities violate table constraints")
    for team in teams:
        if not np.isclose(sum(team["points_distribution"].values()), 1):
            raise ValueError("Season points distribution is not normalized")
        limit = team["current_points"] + 3 * (38 - team["played"])
        if any(not team["current_points"] <= int(p) <= limit for p in team["points_distribution"]):
            raise ValueError("Season points exceed remaining-fixture bounds")
    z = []
    for row in simulation["match_frequencies"]:
        for key in ("p_home", "p_draw", "p_away"):
            p = rows[row["match_id"]][key]
            z.append((row[key] - p) / np.sqrt(p * (1 - p) / simulation["simulations"]))
    return {
        "directory": str(directory),
        "archive_sha256": file_hash(directory / "archive.json"),
        "archived_at": archive["archived_at"],
        "forward_matches": len(rows),
        "first_kickoff": min(r["kickoff_time"] for r in rows.values()),
        "simulations": simulation["simulations"],
        "played_matches": simulation["played_matches"],
        "future_state_evolution": forecast["future_state_evolution"],
        "direct_vs_simulated_mean_absolute_z": float(np.abs(z).mean()),
        "direct_vs_simulated_max_absolute_z": float(np.abs(z).max()),
        "direct_vs_simulated_fraction_within_3se": float((np.abs(z) < 3).mean()),
        "input_run_sha256": file_hash(directory / "run.json"),
    }
