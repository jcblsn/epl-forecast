from datetime import timedelta

import numpy as np

from epl_forecast.models.quality_tilt import QualityTiltFilter

PARAMETERS = {
    "quality_retention": 0.9,
    "quality_sd": 0.12,
    "tilt_retention": 0.65,
    "tilt_sd": 0.10,
    "dispersion": 20.0,
}


def prepare(matches):
    ordered = sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id))
    teams = sorted({t for m in ordered for t in (m.fixture.home_team_id, m.fixture.away_team_id)})
    cutoff = ordered[-1].fixture.match_date + timedelta(days=1)
    dates = sorted({m.fixture.match_date for m in ordered} | {cutoff})
    day_index, team_index = {d: i for i, d in enumerate(dates)}, {t: i for i, t in enumerate(teams)}
    design = np.zeros((len(ordered), 2, 2 + 2 * len(teams)))
    entry = np.full(len(teams), len(dates))
    for i, match in enumerate(ordered):
        design[i, :, :2] = [[1, 1], [1, 0]]
        for team, transform in zip(
            (match.fixture.home_team_id, match.fixture.away_team_id),
            QualityTiltFilter()._team_transforms(),
            strict=True,
        ):
            index = team_index[team]
            design[i, :, 2 + 2 * index : 4 + 2 * index] = transform
            entry[index] = min(entry[index], day_index[match.fixture.match_date])
    return {
        "matches": ordered,
        "teams": teams,
        "dates": dates,
        "cutoff": cutoff,
        "design": design,
        "day_index": np.array([day_index[m.fixture.match_date] for m in ordered]),
        "years": np.array(
            [(b - a).days / 365.25 for a, b in zip(dates[:-1], dates[1:], strict=True)]
        ),
        "active": np.array([np.repeat(i > entry, 2) for i in range(1, len(dates))]),
        "goals": np.array([[m.home_goals, m.away_goals] for m in ordered]),
    }


def reference_model(data, infer_parameters=False):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from jax import lax
    from jax.scipy.special import gammaln

    if infer_parameters:
        rq = numpyro.sample("quality_retention", dist.Beta(9, 1.5))
        rt = numpyro.sample("tilt_retention", dist.Beta(4, 2))
        sq = numpyro.sample("quality_sd", dist.LogNormal(np.log(0.12), 0.5))
        st = numpyro.sample("tilt_sd", dist.LogNormal(np.log(0.10), 0.5))
        k = numpyro.sample("dispersion", dist.LogNormal(np.log(20.0), 1.0))
    else:
        rq, rt, sq, st, k = (
            PARAMETERS[key]
            for key in (
                "quality_retention",
                "tilt_retention",
                "quality_sd",
                "tilt_sd",
                "dispersion",
            )
        )
    n = len(data["teams"])
    dimension = 2 + 2 * n
    mean = jnp.r_[jnp.log(jnp.array([1.2, 1.3])), jnp.zeros(2 * n)]
    sd = jnp.r_[jnp.full(2, 0.25), jnp.full(2 * n, 0.4 / np.sqrt(2))]
    initial_z = numpyro.sample("initial_z", dist.Normal(0, 1).expand([dimension]).to_event(1))
    initial = mean + sd * initial_z
    innovations = numpyro.sample(
        "innovations", dist.Normal(0, 1).expand([len(data["years"]), dimension]).to_event(2)
    )
    rho = jnp.tile(jnp.array([rq, rt]), n)
    annual_sd = jnp.tile(jnp.array([sq, st]), n)
    years = jnp.asarray(data["years"])[:, None]
    factor = rho**years
    variance = annual_sd**2 * (-jnp.expm1(2 * jnp.log(rho) * years)) / (1 - rho**2)
    active = jnp.asarray(data["active"])
    decay = jnp.concatenate([jnp.ones((len(years), 2)), jnp.where(active, factor, 1)], axis=1)
    innovation_sd = jnp.concatenate(
        [
            jnp.sqrt(years) * jnp.array([0.04, 0.025]),
            jnp.where(active, jnp.sqrt(variance), 0),
        ],
        axis=1,
    )

    def advance(state, inputs):
        retention, scale, noise = inputs
        next_state = retention * state + scale * noise
        return next_state, next_state

    _, trajectory = lax.scan(advance, initial, (decay, innovation_sd, innovations))
    trajectory = jnp.concatenate([initial[None, :], trajectory], axis=0)
    eta = jnp.einsum("mij,mj->mi", jnp.asarray(data["design"]), trajectory[data["day_index"]])
    goals = jnp.asarray(data["goals"])
    totals = goals.sum(axis=1)
    rate_total = jnp.exp(eta).sum(axis=1)
    logp = (
        gammaln(k + totals)
        - gammaln(k)
        - gammaln(goals + 1).sum(axis=1)
        + (goals * eta).sum(axis=1)
        - totals * jnp.log(k + rate_total)
        - k * jnp.log1p(rate_total / k)
    )
    numpyro.factor("scores", logp.sum())
    numpyro.deterministic("final_state", trajectory[-1])


def sample_reference(
    data, seed=20260906, warmup=600, samples=800, chains=4, infer_parameters=False
):
    import jax
    from numpyro.diagnostics import summary
    from numpyro.infer import MCMC, NUTS

    jax.config.update("jax_enable_x64", True)
    sampler = MCMC(
        NUTS(reference_model, target_accept_prob=0.9),
        num_warmup=warmup,
        num_samples=samples,
        num_chains=chains,
        chain_method="sequential",
        progress_bar=False,
    )
    sampler.run(jax.random.key(seed), data, infer_parameters)
    draws = {k: np.asarray(v) for k, v in sampler.get_samples().items()}
    chain_draws = {k: np.asarray(v) for k, v in sampler.get_samples(group_by_chain=True).items()}
    diagnostics = summary(chain_draws)
    important = {k: v for k, v in diagnostics.items() if k in PARAMETERS or k == "final_state"}
    report = {
        "chains": chains,
        "warmup": warmup,
        "samples_per_chain": samples,
        "divergences": int(sampler.get_extra_fields()["diverging"].sum()),
        "max_rhat": float(max(np.max(v["r_hat"]) for v in important.values())),
        "min_effective_samples": float(min(np.min(v["n_eff"]) for v in important.values())),
        "parameters": {
            k: {
                "mean": float(v.mean()),
                "sd": float(v.std()),
                "q05": float(np.quantile(v, 0.05)),
                "q95": float(np.quantile(v, 0.95)),
            }
            for k, v in draws.items()
            if k in PARAMETERS
        },
    }
    return draws, report


def production_posterior(data, parameters=None):
    model = QualityTiltFilter(**(parameters or PARAMETERS)).fit(data["matches"], data["cutoff"])
    indices = [0, 1] + [2 + 2 * model.team_index[t] + d for t in data["teams"] for d in range(2)]
    return model.mean[indices], model.covariance[np.ix_(indices, indices)]


def compare_posterior(draws, mean, covariance):
    sampled_mean, sampled_covariance = draws.mean(axis=0), np.cov(draws.T)
    sampled_sd, sd = np.sqrt(np.diag(sampled_covariance)), np.sqrt(np.diag(covariance))
    sampled_corr = sampled_covariance / np.outer(sampled_sd, sampled_sd)
    correlation = covariance / np.outer(sd, sd)
    return {
        "mean_difference_rms": float(np.sqrt(np.mean((mean - sampled_mean) ** 2))),
        "max_mean_difference_in_reference_sd": float(
            np.max(np.abs(mean - sampled_mean) / sampled_sd)
        ),
        "median_sd_ratio_filter_to_reference": float(np.median(sd / sampled_sd)),
        "min_sd_ratio": float(np.min(sd / sampled_sd)),
        "max_sd_ratio": float(np.max(sd / sampled_sd)),
        "correlation_difference_rms": float(np.sqrt(np.mean((correlation - sampled_corr) ** 2))),
        "filter_mean": mean.tolist(),
        "reference_mean": sampled_mean.tolist(),
        "filter_sd": sd.tolist(),
        "reference_sd": sampled_sd.tolist(),
    }


def synthetic_data(template, rng):
    from dataclasses import replace

    model = QualityTiltFilter(**PARAMETERS)
    dimension = template["design"].shape[-1]
    values = (
        np.r_[np.log([1.2, 1.3]), np.zeros(dimension - 2)]
        + rng.normal(size=dimension)
        * np.r_[np.full(2, 0.25), np.full(dimension - 2, 0.4 / np.sqrt(2))]
    )
    trajectory = [values.copy()]
    for years, active in zip(template["years"], template["active"], strict=True):
        decay, variance = model.transition(years, dimension)
        decay[2:] = np.where(active, decay[2:], 1)
        variance[2:] = np.where(active, variance[2:], 0)
        values = decay * values + rng.normal(size=dimension) * np.sqrt(variance)
        trajectory.append(values.copy())
    trajectory = np.array(trajectory)
    rates = np.exp(np.einsum("mij,mj->mi", template["design"], trajectory[template["day_index"]]))
    tempo = rng.gamma(PARAMETERS["dispersion"], 1 / PARAMETERS["dispersion"], len(rates))
    goals = rng.poisson(rates * tempo[:, None])
    matches = [
        replace(m, home_goals=int(g[0]), away_goals=int(g[1]))
        for m, g in zip(template["matches"], goals, strict=True)
    ]
    return {**template, "matches": matches, "goals": goals}, trajectory[-1]
