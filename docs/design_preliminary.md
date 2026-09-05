# Open Premier League forecasting model

## Objective

Build the strongest practical Premier League forecasting and season-simulation
model possible using free data. Produce current, interpretable probabilities for
matches and the season table. Reproducible experimentation improves and validates
the model; it is supporting infrastructure, not the primary product.

The first historical milestone is complete. [E001](experiments/E001.md) established
the normalized data, benchmarks and season simulator. [E002](experiments/E002.md)
added an Elo benchmark. Their results remain useful; their formal experiment
protocols are not a template required for every subsequent idea.

## Product

The working system should collect point-in-time sources, estimate team strength,
forecast individual matches and simulate the remaining Premier League season.
Expose full H/D/A probabilities, exact-score probabilities, expected final points,
position distributions, title and relegation chances, and explicitly conditional
European qualification where cup/slot assumptions are supplied.

A generated JSON/CSV forecast and simple static HTML page are enough initially.
Archive each actual forecast before kickoff so forward performance accumulates
while the model improves. Capture valuable perishable data even before deciding
whether to use it. Current [live behavior](live.md) and the
[implementation plan](implementation_plan.md) describe the running system.

## Data

Prefer free, accessible sources with useful coverage and definitions. Keep raw
responses separate from normalized data and record observation times and hashes.
Use canonical team identities and fixture IDs that survive postponements.

Model inputs must have been available before their forecast cutoff. Historical
results use conservative daily batches because older kickoff times are missing.
Live source timestamps support a more precise record of schedule changes,
availability and odds. Captured full-time scores can update a live season table
without entering a model fitted at the start of that day.

The [data inventory](data_inventory.md) documents existing PL and Championship
history and optional sources. Championship continuity and cached PL shot fields
are inexpensive modeling opportunities. xG, players, managers, injuries, tactical
style, rest and bookmaker information remain testable layers, not mandatory
architectural components.

## Modeling and simulation

Keep the simple common model interface. Scores and outcomes should be forecast
without passing result labels into prediction. M2 attack/defense Poisson is the
current score model; M0/M1/M3 remain benchmarks. Specific models and starting
parameters are choices to investigate, not commitments.

Improve the current model before adding large frameworks: tune decay and ridge,
use Championship information for promotion priors, test lagged shots, then try a
small low-score/distribution correction. Dynamic attack and defense should
address evolving strength and uncertainty when the evidence and implementation
justify it. Player contributions may later decompose strength into squad and
persistent team/system effects.

The simulator fixes known scores and samples each remaining fixture once. Keep
probability, points and goals arithmetic correct and label qualification
assumptions. It currently conditions on one fitted strength vector. Sampling
parameter/state uncertainty is a higher priority than more table-rule edge cases.

## Model development

Use `idea → implement quickly → rolling temporal CV → inspect errors → iterate`.
All historical seasons can contribute development evidence, including periods
previously named validation or holdout. When reporting a tuned strategy, select
hyperparameters using only earlier seasons, then test the next season. Real
pre-kickoff archives from September 2026 onward form the forward test.

Track proper scores, per-season behavior, calibration and observed-score
likelihood. Compare markets on matched fixtures and disclose their information
horizons. A candidate with similar standalone scores can still add complementary
information to an ensemble.

Exploratory ideas need a concise table and conclusion. Do not require frozen
protocols, arbitrary minimum improvements, confidence-interval gates or fresh
repository reconstruction for every candidate. Use ablations, uncertainty analysis
and more documentation for promising results. Retain negative results without
making their writeups the main work.

## Engineering

Use ordinary Python modules, NumPy/SciPy, uv, Ruff and pytest. Keep leakage,
identity, probability and simulation arithmetic tests. Preserve the raw data and
basic provenance quietly. Check normalization determinism when its code changes;
run full clean reproduction occasionally and at release time.

Avoid infrastructure without an immediate product or modeling use: model registry
services, workflow engines, feature stores, elaborate APIs and distributed
training are unnecessary here. A static forecast page and simple snapshot command
are useful now. No automated betting is part of the project.

The [research queue](next_experiments.md) orders current opportunities. Success
means a useful, continually improving forecasting model with an honest forward
record, supported by experiments that make iteration cheap.
