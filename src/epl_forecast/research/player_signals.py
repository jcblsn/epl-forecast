"""Coverage and stability audit of the available player signals.

Answers which API-FOOTBALL appearance fields and canonical Understat process
fields are dependable enough to enter a standalone player representation. It
reports availability, not predictive worth; a field that is well populated may
still carry no portable information.
"""

from collections import defaultdict

import numpy as np

APPEARANCE_FIELDS = (
    "minutes",
    "goals",
    "assists",
    "shots",
    "shots_on_target",
    "saves",
    "rating",
    "passes_total",
    "key_passes",
    "pass_accuracy",
    "tackles",
    "interceptions",
    "duels_total",
    "duels_won",
    "dribbles_attempted",
    "dribbles_successful",
    "fouls_drawn",
    "fouls_committed",
    "yellow_cards",
    "red_cards",
)
PROCESS_FIELDS = ("minutes", "xg", "xa", "shots")
ROLE_ORDER = ("GK", "DEF", "MID", "FWD", "UNK")


def _role(value):
    return value if value in ROLE_ORDER else "UNK"


def _split_half_correlation(series):
    """Odd/even split-half correlation of per-90 rates within a player-season.

    A field whose two halves of the same player-season disagree carries little
    stable player information regardless of how completely it is populated.
    """
    first, second = [], []
    for values in series:
        odd = [v for i, v in enumerate(values) if i % 2]
        even = [v for i, v in enumerate(values) if not i % 2]
        if len(odd) < 4 or len(even) < 4:
            continue
        first.append(float(np.mean(odd)))
        second.append(float(np.mean(even)))
    if len(first) < 20:
        return None, len(first)
    matrix = np.corrcoef(first, second)
    value = float(matrix[0, 1])
    if not np.isfinite(value):
        return None, len(first)
    # Spearman-Brown steps the split-half estimate up to full-length reliability.
    return float(2 * value / (1 + value)) if value > -1 else None, len(first)


def appearance_coverage(rows):
    groups = defaultdict(lambda: defaultdict(lambda: {"rows": 0, "minutes": 0.0, "observed": 0}))
    seasons = defaultdict(lambda: defaultdict(lambda: {"rows": 0, "observed": 0}))
    per_player = defaultdict(lambda: defaultdict(list))
    for row in rows:
        minutes = row.get("minutes")
        if minutes is None or minutes <= 0:
            continue
        role = _role(row.get("position"))
        key = (row["competition_id"], row["season_id"])
        for field in APPEARANCE_FIELDS:
            value = row.get(field)
            observed = value is not None
            cell = groups[field][role]
            cell["rows"] += 1
            cell["minutes"] += float(minutes)
            cell["observed"] += int(observed)
            season_cell = seasons[field][key]
            season_cell["rows"] += 1
            season_cell["observed"] += int(observed)
            if observed and field not in {"minutes", "rating", "pass_accuracy"}:
                per_player[field][(row["player_id"], row["season_id"])].append(
                    float(value) * 90 / float(minutes)
                )
            elif observed and field == "rating":
                per_player[field][(row["player_id"], row["season_id"])].append(float(value))
    reliability = {}
    for field, series in per_player.items():
        value, players = _split_half_correlation(list(series.values()))
        reliability[field] = {"split_half_reliability": value, "player_seasons": players}
    return {
        "by_role": {
            field: {
                role: {
                    "appearances": cell["rows"],
                    "observed": cell["observed"],
                    "observed_share": cell["observed"] / cell["rows"] if cell["rows"] else None,
                }
                for role, cell in sorted(roles.items())
            }
            for field, roles in sorted(groups.items())
        },
        "by_season": {
            field: {
                f"{key[0]}:{key[1]}": cell["observed"] / cell["rows"] if cell["rows"] else None
                for key, cell in sorted(cells.items())
            }
            for field, cells in sorted(seasons.items())
        },
        "reliability": dict(sorted(reliability.items())),
    }


def process_coverage(rows):
    by_season = defaultdict(lambda: {"rows": 0, "linked": 0, "matches": set(), "players": set()})
    by_role = defaultdict(lambda: defaultdict(int))
    per_player = defaultdict(lambda: defaultdict(list))
    invalid = defaultdict(int)
    for row in rows:
        cell = by_season[row["season_id"]]
        cell["rows"] += 1
        cell["matches"].add(row["match_id"])
        if row.get("player_id"):
            cell["linked"] += 1
            cell["players"].add(row["player_id"])
        by_role[_role(row.get("position"))][row["season_id"]] += 1
        minutes = row.get("minutes")
        if minutes is None or minutes < 0:
            invalid["minutes"] += 1
            continue
        for field in ("xg", "xa", "shots"):
            value = row.get(field)
            if value is None:
                invalid[field] += 1
            elif minutes > 0 and row.get("player_id"):
                per_player[field][(row["player_id"], row["season_id"])].append(
                    float(value) * 90 / float(minutes)
                )
    reliability = {}
    for field, series in per_player.items():
        value, players = _split_half_correlation(list(series.values()))
        reliability[field] = {"split_half_reliability": value, "player_seasons": players}
    return {
        "by_season": {
            season: {
                "records": cell["rows"],
                "linked_records": cell["linked"],
                "linked_share": cell["linked"] / cell["rows"] if cell["rows"] else None,
                "matches": len(cell["matches"]),
                "linked_players": len(cell["players"]),
            }
            for season, cell in sorted(by_season.items())
        },
        "by_role": {role: dict(sorted(cells.items())) for role, cells in sorted(by_role.items())},
        "missing_fields": dict(sorted(invalid.items())),
        "reliability": dict(sorted(reliability.items())),
    }


def pass_accuracy_semantics(rows):
    """Test the two candidate units for the raw provider string against passes_total.

    A percentage cannot exceed 100 and is unrelated to the pass count; a completed
    count cannot exceed the total and should track it closely. Whichever prediction
    survives every retained pair decides the unit.
    """
    values, above_hundred, non_numeric = [], 0, 0
    paired, exceeds_total, over_100_with_total = 0, 0, 0
    counts, totals = [], []
    for row in rows:
        raw = row.get("pass_accuracy")
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            non_numeric += 1
            continue
        values.append(value)
        above_hundred += value > 100
        total = row.get("passes_total")
        if total is not None:
            paired += 1
            exceeds_total += value > total
            over_100_with_total += value > 100
            counts.append(value)
            totals.append(float(total))
    correlation = None
    if len(counts) > 2:
        matrix = np.corrcoef(counts, totals)
        correlation = float(matrix[0, 1]) if np.isfinite(matrix[0, 1]) else None
    resolved = bool(paired) and exceeds_total == 0 and above_hundred > 0
    return {
        "observed": len(values) + non_numeric,
        "non_numeric": non_numeric,
        "above_100": above_hundred,
        "max": max(values) if values else None,
        "paired_with_passes_total": paired,
        "exceeds_passes_total": exceeds_total,
        "above_100_with_total": over_100_with_total,
        "correlation_with_passes_total": correlation,
        "resolved": resolved,
        "unit": "completed passes (count)" if resolved else "unresolved",
        "decision": (
            "admissible as a completed-pass count; it never exceeds passes_total and exceeds 100 "
            "where the total does, which excludes a percentage reading"
            if resolved
            else "excluded; the unit is still unresolved"
        ),
    }


def zero_encoding(process_rows, appearance_rows):
    """Distinguish a provider zero written as null from a genuinely unobserved field.

    API-FOOTBALL omits several count fields when the value is zero. Read as missing,
    the affected rates are computed over only the appearances where the event happened,
    which inflates every player's rate and compresses the differences between them.
    """
    process = {(r["match_id"], r["player_id"]): r for r in process_rows if r.get("player_id")}
    agreement = {}
    for field, mark in (("shots", "shots"), ("goals", None)):
        matched = [
            (row, process[(row["match_id"], row["player_id"])])
            for row in appearance_rows
            if row.get("minutes")
            and row.get("player_id")
            and (row["match_id"], row["player_id"]) in process
        ]
        if not matched or mark is None:
            continue
        null_rows = [(a, p) for a, p in matched if a.get(field) is None]
        agreement[field] = {
            "matched_appearances": len(matched),
            "provider_null": len(null_rows),
            "null_with_zero_independent_mark": sum(1 for _, p in null_rows if p[mark] == 0),
            "null_with_positive_independent_mark": sum(1 for _, p in null_rows if p[mark] > 0),
        }
    fields = ("goals", "assists", "shots", "shots_on_target", "saves", "key_passes", "tackles")
    always_written = {}
    detailed = [r for r in appearance_rows if r.get("passes_total") is not None]
    for field in fields:
        observed = sum(1 for r in detailed if r.get(field) is not None)
        always_written[field] = {
            "appearances_with_detailed_payload": len(detailed),
            "observed": observed,
            "observed_share": observed / len(detailed) if detailed else None,
        }
    return {
        "cross_provider_agreement": agreement,
        "within_detailed_payload": always_written,
        "conclusion": "Null is the provider's zero for these count fields, not an unobserved value. Rates must divide by all exposure, not only by exposure where the event occurred.",
    }


def publication_gap(rows):
    """Detailed statistics live in retained payloads but reach canonical rows by version."""
    versions = defaultdict(lambda: defaultdict(int))
    for row in rows:
        key = (row["competition_id"], row["season_id"])
        versions[key][row.get("normalization_version")] += 1
    return {
        f"{key[0]}:{key[1]}": dict(sorted(cells.items(), key=lambda kv: (kv[0] is not None, kv[0])))
        for key, cells in sorted(versions.items())
    }


def signal_audit(data, seasons=None):
    where = ""
    parameters = []
    if seasons:
        placeholders = ",".join("?" * len(seasons))
        where = f" WHERE season_id IN ({placeholders})"
        parameters = list(seasons)
    appearances = data.rows(f"SELECT * FROM appearances{where}", parameters)
    process = data.rows(f"SELECT * FROM player_process{where}", parameters)
    return {
        "scope": "Availability and within-player-season stability of retained fields. Not evidence of predictive value or of resolved measurement semantics.",
        "seasons": list(seasons) if seasons else "all",
        "appearances": appearance_coverage(appearances),
        "player_process": process_coverage(process),
        "pass_accuracy": pass_accuracy_semantics(appearances),
        "zero_encoding": zero_encoding(process, appearances),
        "publication_gap": publication_gap(appearances),
    }
