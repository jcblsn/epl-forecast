import argparse
from datetime import date
from pathlib import Path

import numpy as np
from scipy.stats import norm

from epl_forecast.data.normalize import load_processed
from epl_forecast.research.quality_tilt_reference import (
    PARAMETERS,
    compare_posterior,
    prepare,
    production_posterior,
    sample_reference,
    synthetic_data,
)
from epl_forecast.storage import write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/processed"))
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 8, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2024, 11, 1))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=600)
    parser.add_argument("--samples", type=int, default=800)
    parser.add_argument("--chains", type=int, default=4)
    parser.add_argument("--coverage-replicates", type=int, default=200)
    parser.add_argument("--sampled-coverage-replicates", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260906)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    matches, _, manifest = load_processed(args.data)
    data = prepare(
        [
            m
            for m in matches
            if m.fixture.competition_id == "eng-premier-league"
            and args.start <= m.fixture.match_date < args.end
        ]
    )
    report = {
        "seed": args.seed,
        "start": str(args.start),
        "end": str(args.end),
        "matches": len(data["matches"]),
        "teams": data["teams"],
        "cutoff": str(data["cutoff"]),
        "fixed_parameters": PARAMETERS,
        "scope": "Fresh population priors on a historical subset; no promotion bridge.",
        "data_manifest": manifest,
    }
    mean, covariance = production_posterior(data)
    kwargs = dict(warmup=args.warmup, samples=args.samples, chains=args.chains)
    print("Sampling historical posterior with fixed dynamics", flush=True)
    draws, diagnostics = sample_reference(data, seed=args.seed, **kwargs)
    report["fixed_parameters_reference"] = {
        "sampling": diagnostics,
        "comparison": compare_posterior(draws["final_state"], mean, covariance),
    }
    write_json(args.output / "report.json", report)
    print("Sampling historical posterior with uncertain dynamics and dispersion", flush=True)
    draws, diagnostics = sample_reference(data, seed=args.seed + 1, infer_parameters=True, **kwargs)
    means, covariances = [], []
    for i in np.linspace(0, len(draws["final_state"]) - 1, 100, dtype=int):
        m, c = production_posterior(data, {k: float(draws[k][i]) for k in PARAMETERS})
        means.append(m)
        covariances.append(c)
    mixture_mean = np.mean(means, axis=0)
    mixture_covariance = np.mean(covariances, axis=0) + np.cov(np.array(means).T, bias=True)
    report["inferred_parameters_reference"] = {
        "sampling": diagnostics,
        "comparison": compare_posterior(draws["final_state"], mixture_mean, mixture_covariance),
        "comparison_note": (
            "Production conditional filters integrated over 100 NUTS "
            "hyperparameter draws; not the production discrete ensemble."
        ),
    }
    write_json(args.output / "report.json", report)
    rng = np.random.default_rng(args.seed)
    filter_coverage, sampled_coverage, sample_diagnostics = [], [], []
    for replicate in range(args.coverage_replicates):
        simulated, truth = synthetic_data(data, rng)
        mean, covariance = production_posterior(simulated)
        sd = np.sqrt(np.diag(covariance))
        filter_coverage.append(np.abs(truth - mean) <= norm.ppf(0.95) * sd)
        if replicate < args.sampled_coverage_replicates:
            print(
                f"Sampled synthetic coverage {replicate + 1}/{args.sampled_coverage_replicates}",
                flush=True,
            )
            draws, diagnostics = sample_reference(
                simulated, seed=args.seed + 2 + replicate, **kwargs
            )
            low, high = np.quantile(draws["final_state"], [0.05, 0.95], axis=0)
            sampled_coverage.append((truth >= low) & (truth <= high))
            sample_diagnostics.append(diagnostics)
        if (replicate + 1) % 25 == 0:
            print(f"Filter coverage {replicate + 1}/{args.coverage_replicates}", flush=True)

    def coverage(rows):
        values = np.array(rows)
        if not len(values):
            return None
        return {
            "replicates": len(values),
            "nominal": 0.9,
            "quality": float(values[:, 2::2].mean()),
            "tilt": float(values[:, 3::2].mean()),
            "league": float(values[:, 0].mean()),
            "home": float(values[:, 1].mean()),
            "per_parameter": values.mean(axis=0).tolist(),
            "replicate_mean_se": float(values.mean(axis=1).std(ddof=1) / np.sqrt(len(values))),
        }

    report["synthetic_coverage"] = {
        "filter": coverage(filter_coverage),
        "reference": coverage(sampled_coverage),
        "reference_diagnostics": sample_diagnostics,
        "note": (
            "Prior-predictive simulation with known fixed dynamics; team intervals "
            "within a replicate are correlated. Short subset and limited reference "
            "replicates do not establish full-season calibration."
        ),
    }
    write_json(args.output / "report.json", report)
    print(f"Wrote {args.output / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
