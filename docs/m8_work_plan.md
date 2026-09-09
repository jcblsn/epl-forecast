# Historical M8 team-process proposal

This retained proposal documents the parked M8 experiment and its generative
assumptions. Current architecture and work ordering live in the
[architecture work plan](architecture_next_phase.md). The earlier September 2026
batch froze M7-xg-v1 and kept M2 operational.
M7-v1 is the retained xG research model; M8 was the next team-process research
candidate. M8-v1 is now parked; [the report](experiments/m8_process.md) records why. M6-v1 is the retained first player-information formulation, not the
architectural parent. Existing M7 predictions, source pins, references and
prospective artifacts must remain intact.

## Generative proposal, before implementation

Retain the centered Quality/Tilt state, its full covariance and frozen dynamics.
For each team-match, let the state imply expected scoring process r = exp(eta).
Draw latent process packets N ~ Poisson(r / q), packet masses independently
Exponential(mean q), and total process X as their sum (zero when N = 0).
Draw goals G ~ Poisson(X) downstream of that realized process. Observe the
provider's aggregate xG as X in this first formulation. This is a working
measurement assumption to test, not a claim that Understat publishes truth.

Here q is the pooled scale of process fluctuations, not a scoring probability.
Packets are effective process increments, not literal shots: a Poisson scoring
realization may produce more than one goal per packet. Unlike M7, scoring is
conditioned on the process mass, rather than on a count with a fixed conversion
probability. E[X] = E[G] = r, Var(X) = 2rq, and Var(G) = r + 2rq.
The xG-zero atom has probability exp(-r/q); positive goals with zero process
remain outside support and require an explicit source/correctness audit.

With positive observed X, state information comes from its compound-Poisson
Gamma density; the conditional goal likelihood Poisson(G | X) diagnoses the
scoring assumption. With missing X, integrate both X and N: conditional on N,
goals have a negative-binomial distribution (and are zero for N = 0). No xG
imputation or independent goals/xG likelihood blend is allowed. Forecasts must
integrate process variation as well as state uncertainty and evolve future
team states. Target-match process observations are diagnostic/oracle only.

Aggregate data identify mean process r and, with repeated observations and
pooling, a process dispersion scale q. They do not identify separate physical
shot volume, chance quality, finishing or goalkeeper skill. Do not fit free
team-specific volume and quality trajectories. Use a strongly pooled prior on
q, learned only from earlier observations; no historical outcome-loss grid
optimization. Distinguish uncertainty in q from team-state uncertainty. The initial prior is
log(q) ~ Normal(log(0.25), 0.35²), integrated with five Gauss-Hermite nodes.
This regularizes a league-wide process scale around a modest overdispersion
(Var(G)/E[G] = 1.5 at the prior median), independently of historical score loss.
Check quadrature sensitivity and posterior boundary concentration before trusting
the scale uncertainty; five fixed nodes are an approximation, not exact inference.

Park this formulation if its conditional goals-given-xG checks are materially
miscalibrated, its joint predictive checks cannot reproduce zero/tail behavior,
its pooled dispersion is unstable across chronological regimes, or known-state
coverage/adaptation is materially worse than M7 without compensating evidence.
A tiny loss gain cannot override those failures. Report the consequences of
provider measurement error and test synthetic misspecification explicitly.

## Required work and completion evidence

| Work | Evidence required | Status |
| --- | --- | --- |
| Freeze M7; align research statuses | Existing retained artifacts; current README and research docs | Documentation aligned; retained M7 artifacts and source pins verified against baseline revision and hashes |
| Implement M8 generative model | Normalization, derivative, marginalization, cutoff and evolving-state checks | Implemented; 205-test regression suite passes |
| Chronological comparison | Identical fixtures for M8, M7, centered goals parent, M2 and pre-closing/closing markets; loss, NLL, Brier and calibration | 1,140 matched fixtures retained in `experiments/m8/chronological_diagnostics.json` |
| State and observation validity | Predictive xG/goals checks; known-state coverage, shocks, missing-xG sensitivity; sampled references in multiple regimes where reasonable | 1,140 predictive checks; 120 synthetic replicates across four regimes; two sampled references; five/nine-node sensitivity retained |
| Championship information audit | Pinned raw-field coverage, validity, semantics and stability by season; bridge test if usable | Post-2013 restricted bridge tested on nine promoted teams; evidence in batch report |
| Player-process foundation | Identity/role mapping, provider distinction, pooled attacking formulation and oracle versus forecast-lineup evidence once team structure settles | Sample mapping and design retained; fitting/oracle condition not triggered because M8 failed team-observation checks; no operational reliance on unresolved identities |
| Protect prospective forecasts | Reliable minimal scheduled capture, immutable before/after information archives, M2/M5/M6/M7 and successor records | Installed half-hourly collector; five verified model archives and scheduled unchanged-input followup retained |
| Batch decision | Concise report, compact evidence, explicit retention/parking decision and limits | M8-v1 parked; M7 retained; operational M2 and promotion bridge unchanged; report retained |

Commit and push at natural milestones. Keep market information outside structural
states. No player Tilt, symmetric defensive player effects, M7 constant tuning,
broad dynamics search, dashboards or notification/deployment project.
