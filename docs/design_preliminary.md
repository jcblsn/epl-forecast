# Open Premier League Forecasting Model

## Objective

Build a transparent, reproducible Premier League forecasting system using only free data.

The long-term aim is a model that can estimate team strength, forecast individual matches, and simulate the remainder of a season while also serving as a framework for testing which football signals genuinely improve prediction.

Do not attempt to reproduce any existing model exactly. Nate Silver's PELE, ClubElo, Dixon-Coles models, dynamic Bayesian football models, and player-value models should be treated as useful references.

## Core principle

Implementation update (2026-09-05): the initial milestone now has a data audit,
versioned benchmarks, chronological evaluation and a historical season simulator.
See [data inventory](data_inventory.md), [normalized schema](match_schema.md),
[implementation plan](implementation_plan.md), [model conventions](modeling.md),
and [initial results](experiments/E001.md). The subsequent [Elo comparison](experiments/E002.md)
did not meet its gate for replacing the Poisson reference. These documents record
decisions and evidence; the later research phases below remain open.

Do not make important modeling decisions before inspecting the available data.

In particular, do not commit prematurely to:

* a specific statistical model;
* xG as a required input;
* player-level modeling;
* a particular score distribution;
* a specific definition of "Tilt" or tactical style;
* manager, injury, or fixture-congestion effects;
* bookmaker information as an input;
* particular historical seasons or leagues;
* specific hyperparameters.

Build the project so these can be tested incrementally.

Every additional source or modeling feature should justify its inclusion through leakage-safe out-of-sample performance, interpretability, or both.

## Initial scope

Start with men's English league football, prioritizing the Premier League and using the Championship where useful for promoted-team continuity.

The first usable system should support:

1. ingesting and normalizing historical match data;
2. generating pre-match probabilities for home win, draw, and away win;
3. generating a score distribution where supported by the model;
4. evaluating forecasts chronologically;
5. simulating remaining Premier League fixtures into final-table distributions.

Do not build a frontend initially.

## Data philosophy

Prefer sources that are:

* free;
* historically available;
* reasonably stable;
* timestampable;
* reproducible;
* legally/operationally suitable for automated use.

Keep raw source data immutable and separate from processed data.

Record source, retrieval time, season, and relevant provenance wherever practical.

Avoid look-ahead leakage. A historical forecast must only use information that would have been available before that match.

Before implementing substantial modeling work, produce a short data inventory describing:

* available datasets;
* date coverage;
* leagues covered;
* important fields;
* missingness;
* historical consistency;
* likely leakage risks;
* reliability of continued access.

Treat richer sources such as xG, player data, availability information, and odds as optional layers until their historical coverage has been verified.

## Architecture

Keep four concerns separate.

### 1. Data layer

Responsible for acquiring, storing, validating, and normalizing raw information.

Use canonical IDs for teams, competitions, seasons, matches, and—if later needed—players.

### 2. Modeling layer

Expose a common forecasting interface so different models can be compared without changing the surrounding system.

A model should conceptually support:

`fit(data_as_of_time)`

`predict_match(home, away, context)`

and return probabilistic forecasts.

Begin with simple benchmarks before implementing more complex models.

Likely benchmark families include:

* Elo;
* Poisson / Dixon-Coles;
* simple attack-defense models.

More advanced candidates can later include:

* dynamic Bayesian/state-space attack and defense;
* a separate match-openness or Tilt component;
* negative-binomial or correlated score models;
* player/squad-informed priors.

Do not assume any advanced version will outperform the simpler models.

### 3. Evaluation layer

This is a first-class part of the project, not an afterthought.

Use chronological / rolling-origin evaluation.

Track at minimum:

* log loss;
* Brier score;
* calibration;
* predictive likelihood of observed scores where applicable.

Where historical bookmaker odds are available, retain them initially as an external benchmark rather than automatically feeding them into the model.

Every meaningful model change should be evaluated against prior versions.

Maintain a results table resembling:

| Model | Description | Data used | Log loss | Brier | Calibration |
| ----- | ----------- | --------- | -------- | ----- | ----------- |

### 4. Simulation layer

Given current model state and remaining fixtures, simulate the remainder of the Premier League many times.

Produce distributions for:

* final position;
* points;
* goal difference;
* title probability;
* relevant European qualification probabilities;
* relegation probability.

Keep simulation logic separate from match prediction.

Eventually distinguish randomness in match outcomes from uncertainty about underlying team strength if the selected statistical model supports this naturally.

## Development sequence

### Phase 0 — Data audit

Identify and inspect viable free data.

Do not build sophisticated models yet.

Deliver:

* data inventory;
* normalized match schema;
* initial historical dataset;
* notes on leakage and coverage.

### Phase 1 — Evaluation harness

Create chronological train/predict/evaluate infrastructure before optimizing models.

Implement trivial and simple benchmarks so the pipeline can be validated.

### Phase 2 — Strong team-level baseline

Implement and compare a small set of established team-level approaches.

The purpose is to establish how much predictive performance is achievable without richer data.

Select a baseline based on evidence, not preference.

### Phase 3 — Dynamic team model

Investigate whether team attack and defense should evolve through time rather than being represented by a single static rating.

Consider Bayesian/state-space approaches, but select implementation details only after inspecting dataset size and computational requirements.

### Phase 4 — Scoring model experiments

Compare reasonable score-generating distributions.

Possible candidates include:

* independent Poisson;
* Dixon-Coles;
* bivariate/correlated Poisson;
* negative-binomial variants.

Judge them primarily by held-out predictive performance and calibration.

### Phase 5 — Optional information layers

Only after the team-level system is working, investigate incremental value from:

* xG;
* shots or other match statistics;
* player/squad information;
* player availability;
* promoted-team information;
* manager changes;
* rest / fixture congestion;
* tactical openness / Tilt.

Each should be implemented as an experiment that can be enabled or removed cleanly.

### Phase 6 — Market model

If sufficiently complete historical odds exist, create a separate market-implied forecast.

Compare:

1. structural football model;
2. market forecast;
3. combined forecast.

Do not assume combination improves accuracy. Estimate its value chronologically.

## Player modeling

Player-level modeling is a potentially important later feature, but it should not block the initial system.

If historical minutes, lineups, or suitable proxies prove sufficiently complete, investigate hierarchical player contributions to attacking and defensive strength.

The desired conceptual decomposition is:

`team strength = player contribution + persistent team/system contribution`

This could eventually allow the model to react naturally to transfers, injuries, and squad turnover.

Do not implement this until the historical data can support leakage-safe estimation.

## Research discipline

Treat the project as a sequence of experiments rather than a march toward a predetermined architecture.

Prefer:

`baseline → modification → backtest → keep/reject`

over accumulating features.

Maintain reproducible model versions such as:

* M0 — trivial baseline
* M1 — Elo
* M2 — score model
* M3 — dynamic attack/defense
* M4 — additional feature

The numbering should describe actual experimental history rather than this proposed sequence.

Record rejected experiments as well as successful ones.

## Engineering priorities

Favor:

* simple Python;
* modular components;
* reproducible scripts;
* deterministic data transformations;
* configuration rather than hard-coded assumptions;
* tests around data leakage and simulation rules;
* cached/raw datasets rather than repeated network dependence.

Avoid premature infrastructure.

Do not initially build:

* a website;
* elaborate APIs;
* distributed processing;
* real-time ingestion;
* extensive visualization;
* automated betting functionality.

A notebook is acceptable for exploration, but production model logic should migrate into normal modules with tests.

## First milestone

The first meaningful milestone is not a sophisticated prediction model.

It is a repository in which we can:

1. download/load a credible historical dataset;
2. reproduce the same processed dataset deterministically;
3. run a chronological forecasting experiment;
4. compare at least two simple models;
5. report their probabilistic accuracy;
6. simulate a Premier League season from one of them.

Once that exists, inspect the empirical results and available richer data before deciding what the next modeling layer should be.

## Success criterion

The project succeeds if it becomes a trustworthy experimental framework capable of answering:

> Does adding this information or modeling assumption make Premier League forecasts meaningfully better?

The eventual forecasting model should emerge from those experiments rather than being specified in advance.
