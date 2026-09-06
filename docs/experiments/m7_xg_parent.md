# M7 xG-informed parent batch

September 6, 2026. In progress; M2 remains unchanged. The full completion scope
is in [the work plan](../m7_work_plan.md); research decisions follow
[the research principles](../research_principles.md).

## Historical source audit

The [Understat league page](https://understat.com/league/EPL/2024) now requests
`getLeagueData/EPL/{year}` using `X-Requested-With: XMLHttpRequest`. The adapter
uses that same public website contract. Responses may contain gzip bytes; hashes
cover the original bytes, and parsing handles compression explicitly. This is an
undocumented external dependency. The manifest pins 12 responses under
`data/raw/understat/`; changed upstream bytes cannot silently replace them.
Keep these local raw files when moving the research workspace: if the provider
revises its response, a manifest alone cannot recover the original bytes.

The [machine-readable audit](m7/understat_audit.json) covers 4,560 matches,
380 per season from 2014/15 through 2025/26. All home/away team identities and
scores reconcile to the hashed canonical Football-Data table. Twenty-six
2015/16–2016/17 timestamps are midnight on the day after the canonical date.
The adapter uses an explicit correction registry bound to source hash, provider
match ID, original timestamp, canonical fixture ID and canonical date. It retains
the original timestamp and lists every correction in the audit. The cause of
these source timestamps is not established; no blanket timezone shift or fuzzy
fixture matching is applied. Other date mismatches fail the audit.

Observations retain Understat's match `xG`, including penalties, separately from
`npxG` and FPL xG. Zero is valid. The current snapshot is retrospective: next-day
availability is a historical evaluation assumption, not evidence of original
publication time or freedom from provider revisions. Source retrieval timestamps
are retained in the pinned manifest. Target-match realized xG must never enter a
deployable pre-match forecast. Provider season-level player summaries are present
but do not establish stable player-match coverage; that audit remains pending.

Reproduce the source audit and adapter checks:

```sh
uv run python scripts/audit_understat.py
uv run pytest tests/test_understat.py tests/test_data.py -q
```

Eleven adapter tests cover gzip, checksums, cache reuse, drift rejection, aliases,
zero/nonfinite/negative xG, dates, scores, duplicate/unfinished matches and the
exact-source correction boundary. The audit refuses to publish normalized
modeling inputs if any completed-season fixture remains unresolved.

## Remaining work

The identifiable state implementation and sampled-reference equivalence checks,
probabilistic joint goals/xG channel, chronological model comparisons,
high-information diagnostics, evolving season validation, player-source follow-up
and prospective archive refresh/verification remain required. Source coverage is
not evidence of model quality or a completed M7 parent.
