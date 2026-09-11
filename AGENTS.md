# Working in this repository

## Writing

Use ASD-STE100 Simplified Technical English for all public facing natural language text in the repo, including documents and comments.

Text in markdown files should not be hard wrapped.

## Verifying

Run `scripts/verify.sh` — it formats, then lints, then tests. Order matters: `ruff check` before `ruff format` aborts on fixable layout findings.

Ruff E501 is disabled, so the formatter owns line length in Python. Do not hand-split string literals to satisfy a line limit.

## Data

- Fetch through `src/epl_forecast/data/capture.py`, never a web-reader tool. Football-Data 503s through readers and on the `www` host.
- Retained Understat payloads are gzip; decompress on the `\x1f\x8b` magic byte. Legacy FPL archives (2016–19) are Latin-1, not UTF-8.
- Team identity comes from `data/teams.csv` verbatim — extend the reviewed registry rather than inventing a slug.
- Preserve raw provider evidence. When a source is internally inconsistent, mark the field unknown and surface it in the audit; do not normalize it away.
