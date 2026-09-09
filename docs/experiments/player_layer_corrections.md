# Corrected standalone player evidence

This supersedes the horizon, reliability and API-control claims in the original
[player-layer report](player_layer.md). It implements the steering memo's
correctness gate without reopening general feature tuning. The retained source
snapshot is unchanged.

## Corrections

The evaluator now passes the requested transfer horizon explicitly. Previously its
90-day headline trained a 90-day mapping but constructed 240-day transfer targets.
The evaluator also rejects a mismatched training/target horizon and excludes
calendar windows that extend beyond the retained observation period. The latest
process observation is 2026-09-06; the conservative exclusive data boundary is
2026-09-07. These checks apply to both transfer and chronological targets.

The reliability audit calls the same API mark decoder as the model. Provider-null
count fields become zero where the model considers the field published; genuinely
unpublished detailed fields remain unknown. The raw non-null coverage tables remain
raw evidence, separate from the corrected split-half series. Goals reliability
changes from 0.455 to 0.251, assists from 0.692 to 0.097, shots on target from 0.665
to 0.396, key passes from 0.552 to 0.431. Shot-volume reliability is almost unchanged,
0.607 to 0.605. The original audit's praise for stable assist counts was overstated.

`api_only` and its rating ablation now use API exposure and API staleness, with no
player-process coverage input. Their predictive residual strata also use API
history depth. Understat remains the supervised outcome and common target-role
offset; API-only describes the player predictors and evidence-depth uncertainty.
The new `api_depth_matched` control limits API history and API role populations to
the calendar window with eligible retained process history. It matches temporal
depth, not individual linkage completeness. All candidates use identical cases
within a horizon.

## What survives the correction

The full [cross-horizon tables](player_layer_corrections/report.md) and
[machine-readable results](player_layer_corrections/summary.json) retain every
candidate, slice, interval, calibration measure and additional matched API/rating
comparison. Lower CRPS is better. Horizons have different exposure and cohorts;
raw losses should not be compared across horizons.

Shooting remains portable. Against a pooled role prior, the long-run process
representation improves transfer CRPS by 0.118 [0.052, 0.197] over 61 90-day episodes,
0.230 [0.124, 0.355] over 76 180-day episodes and 0.273 [0.147, 0.419] over 70
240-day episodes. These are player-clustered 95% bootstrap intervals.

Creation is less certain. Its corresponding transfer improvements are 0.042
[0.015, 0.068], 0.045 [0.006, 0.086] and 0.058 [-0.001, 0.115]. The longer-horizon
interval includes zero. This supports a separate creation trait with weaker
portability confidence, not a claim that all attacking information is equally
portable.

API counts improve chronological creation, including the depth-matched control:
at 90 days the matched control improves CRPS by 0.0039 [0.0011, 0.0066]. But the
full-history API control no longer clearly improves transfer creation at any of
the three horizons. Matching calendar depth is worse than long-run process on
180/240-day transfer creation and shooting. Full API history still improves
transfer shot volume at all three horizons; its depth-matched counterpart does
not clearly do so. The older conclusion that API counts establish a superior
portable creation measure is withdrawn.

Context-share decomposition remains worse on transfer creation and shot volume
at all three horizons. For shooting its 90-day interval now includes zero, while
180/240-day losses remain clear. This preserves the decision to keep that
formulation out, with a more qualified short-horizon claim.

The naive xG+xA aggregate remains worse chronologically on each component, and on
transfer shooting at all horizons. Transfer creation alone does not resolve a
loss. This rejects that aggregation as a representation; it does not reject a
learned downstream scalar or an attacking mapping from separate traits.

## Decision and next gate

Freeze the existing long-run shooting and creation sufficient statistics as a
small distributional interface, with uncertainty, timing and provenance declared
in [the interface contract](../portable_player_interface.md). Do not polish the
leaderboard or tune more features. The next empirical question is whether a
chronologically learned attacking roster delta improves fixed M2 and M7 forecasts
when actual personnel change. No team-level value is claimed by this experiment.

These evaluations condition on observed target exposure, use retrospective club
changes as labels, and retain the original limited transfer population. They do
not establish causal value, forecast minutes, foreign-arrival priors or prospective
operational calibration. Fully elapsed calendar windows remove administrative
truncation; they do not create missing individual provider records.

## Reproduction and retained evidence

```sh
uv run --all-extras python scripts/evaluate_player_layer.py \
  --manifest runs/research-ready-v2-player-layer/manifest.json \
  --output runs/player-layer-complete-h90 --marks xg xa process_shots --horizon-days 90
```

Repeat with `h180`/`--horizon-days 180` and `h240`/`--horizon-days 240` in fresh output
directories. Then run:

```sh
uv run --all-extras python scripts/audit_player_signals.py \
  --manifest runs/research-ready-v2-player-layer/manifest.json \
  --output runs/player-signal-audit-corrected
uv run --all-extras python scripts/report_player_corrections.py \
  --output docs/experiments/player_layer_corrections
```

The [evidence archive](player_layer_corrections/evidence.tar.gz) retains all raw
per-case score CSVs, summaries, execution/provenance records, the signal audit and
the source snapshot manifest. Its [hash manifest](player_layer_corrections/manifest.json)
records every retained file. Final evaluations ran from `5fa952e`; source files
used to produce the evaluations are recoverable from that commit. The initial
horizon reruns without the full-window gate remain local historical runs and are
not the retained decision evidence.
