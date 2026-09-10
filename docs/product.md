# Operating the forecast product

M7 is the frozen structural model for both leagues. This page owns the product
layer around it: how a forecast is generated, what may be published, where old
forecasts live and how prospective performance accumulates. The
[MVP contract](mvp.md) owns what the forecast itself claims.

## One command

```sh
uv run epl-forecast operate
```

`operate` collects fresh provider data, runs the M7 product forecast for the
Premier League and the Championship, runs `scripts/verify_forecast_product.py`
against each archive, and publishes only if both archives pass. It then derives
the compact public documents, refreshes the snapshot index and rebuilds the
prospective ledger. Nothing is published from a failed or unverified run.

The run is gated the same way the research collector is: a snapshot is written
when the information fingerprint changes or twelve hours have passed, whichever
comes first. `--force` overrides the gate, `--no-collect` reuses the archive as
it stands, and `--interval-hours` changes the cadence.

To refresh on a schedule without intervention:

```sh
uv run epl-forecast operate --install-launch-agent
```

That installs `org.epl-forecast.operate`, which runs the same command every
twelve hours and writes `runs/product/operate.log`. Remove it with
`launchctl bootout gui/$UID/org.epl-forecast.operate`. Stop it while working on
the data layer; it takes the writer lock.

Forecast generation stays on this machine because it needs the private archive
under `data/`. GitHub Actions runs the checks and, when Pages is enabled, serves
the committed site; it never fetches provider data and never fits a model.

## What may be published

`configs/publication.toml` is the boundary. It declares every key allowed to
appear anywhere in a published document, the two keys allowed to carry a
digest, key substrings that may never appear, and value patterns that identify a
provider, a local file or a captured payload.

Published: H/D/A probabilities, exact-score grids for each club's next fixture,
full final-points and finishing-position distributions, expected and median
points and rank, reported intervals, event probabilities, the market-assisted
blend where one exists, timestamps, model identity and the verification result.

Private: everything under `data/` and `snapshots/`, request records, Parquet
partitions and their hashes, odds quotes and the decimal prices behind the
market-assisted blend, player and provider tables, source file names and
retrieval times, and the full run provenance in `runs/`.

The boundary is enforced three times: documents are assembled by allowlist
rather than by filtering, `check_publishable` re-checks each assembled document
before it is written, and `scripts/check_publishable.py` re-checks the whole
committed surface in CI. The allowlist is itself checked against the denylist,
so widening one without the other fails at load.

A snapshot is refused if it has no season projection or fewer than 1,000
simulated paths, so a smoke run cannot enter the archive as a product.

## The archive and the index

Each published snapshot is written once, under
`site/data/forecasts/<snapshot>/<competition>.json`, and never rewritten:
publishing the same content again is a no-op and publishing different content
under the same name raises. `site/data/index.json` lists every snapshot, newest
first, with the latest one named. Old forecasts are preserved exactly as
generated; they are never regenerated from newer data or newer code.

`scripts/backfill_publication.py` derives published documents from archives that
already exist, verifying each one as it stands. It is how the site is rebuilt if
`site/data` is lost, and it reports rather than repairs any archive that fails
verification or falls below the product floor.

The full private archive of each run — every CSV, the run provenance, the
verification report and the logs — stays under `runs/product/<snapshot>/`.

## The prospective ledger

`site/data/ledger.json` scores settled matches. Each match is scored once,
against the last snapshot generated strictly before its kickoff, so a forecast
never benefits from information published after the match started. Settled rows
carry the forecast, the outcome and the snapshot that produced it; the summary
reports log loss, Brier and classwise ECE overall and per competition.

The ledger is derived: it is rebuilt from the published forecasts and realized
results on every run, and rebuilding reproduces it. Season snapshots are listed
as pending, so rank, points and event scoring can run against them once a season
settles.

## The viewer

`site/` is a static page with no build step and no backend. It reads the
published JSON and nothing else.

```sh
uv run python -m http.server -d site 8000
```

It shows both league tables with expected rank and points and the headline event
probabilities, the full finishing-position matrix, per-club points and rank
distributions, upcoming fixtures with H/D/A and likeliest scores, and the
ledger. The snapshot selector loads any archived forecast. Every table column
sorts.

Pages deployment is off. `.github/workflows/pages.yml` runs only when started by
hand and publishes `site/` as committed, after re-checking the boundary. To go
public later, enable Pages for the repository and add the push trigger back.
