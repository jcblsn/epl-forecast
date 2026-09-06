"""Separate grid support, daily evidence integration, and forecast-relevant coverage."""

import argparse
from datetime import date
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from scipy.stats import norm

from epl_forecast.data.normalize import load_processed
from epl_forecast.models.quality_tilt import QualityTiltFilter
from epl_forecast.research.quality_tilt_reference import (
    PARAMETERS,
    compare_posterior,
    prepare,
    production_posterior,
    sample_reference,
    synthetic_data,
)
from epl_forecast.research.quality_tilt_uncertainty import (
    EvidenceCheckedFilter,
    relevant_functionals,
)
from epl_forecast.simulation import simulate_season
from epl_forecast.storage import write_json

PARENT = dict(
    quality_retention=0.85, quality_sd=0.09, tilt_retention=0.5, tilt_sd=0.07, dispersion=100.0
)


def grid_support(matches):
    specifications = [
        PARENT,
        *[
            {**PARENT, **change}
            for change in (
                {"dispersion": None},
                {"dispersion": 300.0},
                {"quality_sd": 0.045},
                {"tilt_sd": 0.035},
                {"quality_sd": 0.045, "tilt_sd": 0.035},
                {"quality_retention": 0.65},
                {"tilt_retention": 0.25},
            )
        ],
    ]
    models = [QualityTiltFilter(**s) for s in specifications]
    rows = []
    for cutoff in (date(2023, 7, 1), date(2024, 7, 1), date(2025, 7, 1), date(2026, 7, 1)):
        train = [m for m in matches if m.available_on <= cutoff]
        evidence = np.array([m.fit(train, cutoff).log_evidence for m in models])
        weights = np.exp(evidence - logsumexp(evidence))
        rows.append(
            {
                "cutoff": str(cutoff),
                "training_matches": len(train),
                "effective_specifications": float(1 / (weights @ weights)),
                "specifications": [
                    {**s, "log_evidence": float(e), "weight": float(w)}
                    for s, e, w in zip(specifications, evidence, weights, strict=True)
                ],
            }
        )
        print(f"Grid support through {cutoff}", flush=True)
    return {
        "scope": "Equal prior mass on eight fixed probes beyond the original winning corner. "
        "Exploratory full-history Laplace evidence; no production support change.",
        "checkpoints": rows,
    }


def integrals(matches, power, seed):
    data = prepare(
        [
            m
            for m in matches
            if m.fixture.competition_id == "eng-premier-league"
            and date(2024, 8, 1) <= m.fixture.match_date < date(2026, 7, 1)
        ]
    )
    specs = [
        PARENT,
        {**PARENT, "dispersion": None},
        {**PARENT, "quality_sd": 0.16, "tilt_sd": 0.14},
    ]
    rows = []
    for i, spec in enumerate(specs):
        repetitions = []
        for scramble in range(3):
            model = EvidenceCheckedFilter(**spec, power=power, seed=seed + scramble * 10000)
            model.fit(data["matches"], data["cutoff"])
            checks = model.integration_checks
            repetitions.append(
                {
                    "laplace": model.log_evidence,
                    "importance_same_gaussian_priors": sum(r["importance"] for r in checks),
                    "correction": sum(r["correction"] for r in checks),
                    "min_ess_fraction": min(r["ess_fraction"] for r in checks),
                    "daily": checks,
                }
            )
        rows.append(
            {
                "specification": spec,
                "scrambles": repetitions,
                "correction_scramble_sd": float(
                    np.std([r["correction"] for r in repetitions], ddof=1)
                ),
            }
        )
        print(f"Daily integration specification {i + 1}/{len(specs)}", flush=True)
    return {
        "matches": len(data["matches"]),
        "cutoff": str(data["cutoff"]),
        "draws_per_daily_integral": 2**power,
        "specifications": rows,
        "scope": "Fresh population initialization on two historical seasons. Importance sampling "
        "reintegrates each daily likelihood under its unchanged production Gaussian prior. "
        "Scrambles assess integration noise. This isolates evidence integration error; "
        "it does not estimate exact full-history evidence or Gaussian filtering error.",
    }


def coverage(matches, replicates, seed, correct_moments=False, power=12):
    data = prepare(
        [
            m
            for m in matches
            if m.fixture.competition_id == "eng-premier-league"
            and date(2024, 8, 1) <= m.fixture.match_date < date(2024, 11, 1)
        ]
    )
    transform = relevant_functionals(data)
    rng = np.random.default_rng(seed)
    hits, z_scores, correlations = [], [], []
    for i in range(replicates):
        simulated, truth = synthetic_data(data, rng)
        if correct_moments:
            model = EvidenceCheckedFilter(
                **PARAMETERS, power=power, seed=seed + i * 1000, correct_moments=True
            ).fit(simulated["matches"], simulated["cutoff"])
            indices = [0, 1] + [
                2 + 2 * model.team_index[t] + d for t in data["teams"] for d in range(2)
            ]
            mean = model.mean[indices]
            covariance = model.covariance[np.ix_(indices, indices)]
        else:
            mean, covariance = production_posterior(simulated)
        projected_covariance = transform @ covariance @ transform.T
        sd = np.sqrt(np.diag(projected_covariance))
        z = transform @ (mean - truth) / sd
        hits.append(abs(z) <= norm.ppf(0.95))
        z_scores.append(z)
        correlations.append(projected_covariance[0, 1] / (sd[0] * sd[1]))
        if (i + 1) % 25 == 0:
            print(f"Functional coverage {i + 1}/{replicates}", flush=True)
    hits, z_scores = np.array(hits), np.array(z_scores)
    return {
        "replicates": replicates,
        "nominal": 0.9,
        "matches": len(data["matches"]),
        "parameters": PARAMETERS,
        "moment_corrected": correct_moments,
        "mean_league_common_tilt_correlation": float(np.mean(correlations)),
        "functionals": {
            name: {
                "coverage": float(hits[:, indices].mean()),
                "replicate_mean_se": float(
                    hits[:, indices].mean(axis=1).std(ddof=1) / np.sqrt(replicates)
                ),
                "mean_standardized_bias": float(z_scores[:, indices].mean()),
                "rms_standardized_error": float(np.sqrt(np.mean(z_scores[:, indices] ** 2))),
            }
            for name, indices in (
                ("league", [0]),
                ("common_tilt", [1]),
                ("league_plus_twice_common_tilt", [2]),
                ("match_log_scoring_rates", list(range(3, len(transform)))),
            )
        },
        "scope": "Prior-predictive synthetic 90-match subset with original fixed parameters. "
        "Scoring-rate functionals are at the final cutoff, with both rates for each "
        "subset pairing. Replicates, not correlated team/rate intervals, determine SE.",
    }


def sampled_sensitivity(matches, power, seed):
    data = prepare(
        [
            m
            for m in matches
            if m.fixture.competition_id == "eng-premier-league"
            and date(2024, 8, 1) <= m.fixture.match_date < date(2024, 11, 1)
        ]
    )
    print("Sampling fixed-dynamics reference for moment correction", flush=True)
    draws, diagnostics = sample_reference(data, seed=seed)
    transform = relevant_functionals(data)
    comparisons = {}
    for name, model in (
        ("laplace", QualityTiltFilter(**PARAMETERS)),
        (
            "moment_corrected",
            EvidenceCheckedFilter(**PARAMETERS, power=power, seed=seed, correct_moments=True),
        ),
    ):
        model.fit(data["matches"], data["cutoff"])
        indices = [0, 1] + [
            2 + 2 * model.team_index[t] + d for t in data["teams"] for d in range(2)
        ]
        mean, covariance = model.mean[indices], model.covariance[np.ix_(indices, indices)]
        comparisons[name] = {
            "state": compare_posterior(draws["final_state"], mean, covariance),
            "functionals": compare_posterior(
                draws["final_state"] @ transform.T,
                transform @ mean,
                transform @ covariance @ transform.T,
            ),
        }
    return {
        "sampling": diagnostics,
        "comparisons": comparisons,
        "scope": "Same final-time population-initialized posterior and fixed parameters. "
        "Functional order: league, common Tilt, league + twice common Tilt, "
        "then home/away log rates for the subset pairings.",
    }


def season_sensitivity(matches, power, seed, simulations):
    season = [
        m
        for m in matches
        if m.fixture.competition_id == "eng-premier-league" and m.fixture.season_id == "2024-2025"
    ]
    cutoff = date(2024, 11, 1)
    played = [m for m in season if m.available_on <= cutoff]
    remaining = [m.fixture for m in season if m.available_on > cutoff]
    teams = sorted({m.fixture.home_team_id for m in season})
    models = {
        "laplace": QualityTiltFilter(**PARAMETERS),
        "moment_corrected": EvidenceCheckedFilter(
            **PARAMETERS, power=power, seed=seed, correct_moments=True
        ),
    }
    result = {}
    for name, model in models.items():
        model.fit(played, cutoff)
        result[name] = simulate_season(model, played, remaining, teams, cutoff, simulations, seed)
        result[name]["next_match"] = {
            "match_id": remaining[0].match_id,
            "probabilities": model.predict_match(remaining[0]).probabilities,
            "log_rate_mean": model.forecast_moments(remaining[0])[0].tolist(),
            "log_rate_covariance": model.forecast_moments(remaining[0])[1].tolist(),
        }
        print(f"Season sensitivity: {name}", flush=True)
    return {
        "scope": "Same fresh population prior and fixed dynamics on 2024/25 opening results. "
        "Moment correction integrates daily posteriors then projects to Gaussian; "
        "it remains an approximation and is not a sampled full trajectory reference.",
        "models": result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/processed"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--power", type=int, default=12)
    parser.add_argument("--replicates", type=int, default=200)
    parser.add_argument("--simulations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument(
        "--sections",
        nargs="+",
        choices=[
            "grid_support",
            "integration",
            "coverage",
            "corrected_coverage",
            "sampled_sensitivity",
            "season_sensitivity",
        ],
        default=["grid_support", "integration", "coverage", "season_sensitivity"],
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    matches, _, manifest = load_processed(args.data)
    report = {"input_manifest": manifest, "seed": args.seed}
    for name, run in (
        ("grid_support", lambda: grid_support(matches)),
        ("integration", lambda: integrals(matches, args.power, args.seed)),
        ("coverage", lambda: coverage(matches, args.replicates, args.seed)),
        (
            "corrected_coverage",
            lambda: coverage(matches, args.replicates, args.seed, True, args.power),
        ),
        ("sampled_sensitivity", lambda: sampled_sensitivity(matches, args.power, args.seed)),
        (
            "season_sensitivity",
            lambda: season_sensitivity(matches, args.power, args.seed, args.simulations),
        ),
    ):
        if name not in args.sections:
            continue
        report[name] = run()
        write_json(args.output / "report.json", report)


if __name__ == "__main__":
    main()
