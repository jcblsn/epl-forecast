"""Standalone, cutoff-safe representations of portable player attacking process.

This layer estimates what appears to travel with a player. It is deliberately not
connected to any club, match or season model: every candidate predicts a player's
own subsequent process given exposure, so that the representation can be judged on
player evidence before anything consumes it.

Two provider semantics discovered by the signal audit are load-bearing here.
API-FOOTBALL omits several count fields when the value is zero, so a rate must
divide by all exposure rather than only by the appearances where the event
occurred. The retained pass-accuracy string is a completed-pass count, not a
percentage.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date

import numpy as np

from epl_forecast.research.player_prior import london_date
from epl_forecast.squads import ROLES

# Written by the provider even when the value is zero.
DENSE_API_FIELDS = ("assists", "yellow_cards", "red_cards")
# Omitted by the provider when zero; present in every retained normalization.
SPARSE_API_FIELDS = ("goals", "shots", "shots_on_target", "saves")
# Omitted when zero and only published by the later normalization.
DETAILED_API_FIELDS = (
    "key_passes",
    "passes_total",
    "tackles",
    "interceptions",
    "duels_won",
    "dribbles_successful",
)
DETAIL_MARKERS = ("rating", "passes_total", "duels_total", "pass_accuracy")
PROCESS_MARKS = ("xg", "xa", "process_shots", "xg_plus_xa")
TARGETS = ("xg", "xa")
LEAGUE_REFERENCE_XG = 1.4


@dataclass(frozen=True)
class LayerConfig:
    recent_half_life: float = 45.0
    long_half_life: float = 240.0
    rate_prior_matches: float = 10.0
    pool_prior_matches: float = 50.0
    team_prior_matches: float = 8.0
    feature_clip: float = 2.5

    def __post_init__(self):
        if self.recent_half_life >= self.long_half_life:
            raise ValueError("Recent half-life must be shorter than long-run half-life")
        if any(not np.isfinite(v) or v <= 0 for v in vars(self).values()):
            raise ValueError("Layer configuration values must be finite and positive")


def observation_rows(data, competitions=("eng-premier-league",)):
    """One row per appearance with the marks each provider actually published.

    Understat process marks are attached only where the canonical player-process
    record links to the same canonical player; unlinked process records stay out
    rather than being collapsed onto a guessed identity.
    """
    placeholders = ",".join("?" * len(competitions))
    rows = data.rows(
        "WITH team AS (SELECT match_id, team_id, xg FROM team_process "
        "WHERE provider='understat' AND xg IS NOT NULL), "
        "regular AS (SELECT DISTINCT match_id FROM fixtures WHERE stage='regular'), "
        "proc AS (SELECT match_id, player_id, min(minutes) AS minutes, sum(xg) AS xg, "
        "sum(xa) AS xa, sum(shots) AS shots, count(*) AS records FROM player_process "
        "WHERE player_id IS NOT NULL GROUP BY 1,2) "
        "SELECT a.*, p.name AS player_name, t.xg AS team_xg, o.xg AS opponent_xg, "
        "pr.xg AS process_xg, pr.xa AS process_xa, pr.shots AS process_shots, "
        "pr.minutes AS process_minutes, pr.records AS process_records "
        "FROM appearances a "
        "LEFT JOIN players p USING(player_id) "
        "JOIN regular f USING(match_id) "
        "LEFT JOIN team t ON t.match_id=a.match_id AND t.team_id=a.team_id "
        "LEFT JOIN team o ON o.match_id=a.match_id AND o.team_id<>a.team_id "
        "LEFT JOIN proc pr ON pr.match_id=a.match_id AND pr.player_id=a.player_id "
        f"WHERE a.minutes>0 AND a.competition_id IN ({placeholders}) "
        "ORDER BY a.kickoff_time, a.player_id",
        list(competitions),
    )
    seen = set()
    result = []
    for row in rows:
        key = row["match_id"], row["player_id"]
        if key in seen:
            raise ValueError(f"Duplicate appearance for {key}")
        seen.add(key)
        result.append(row)
    return result


def api_mark_values(row):
    """Marks and their availability, applying the resolved zero-versus-missing rule."""
    detailed = any(row.get(field) is not None for field in DETAIL_MARKERS)
    values, available = {}, {}
    for field in DENSE_API_FIELDS + SPARSE_API_FIELDS:
        raw = row.get(field)
        values[field] = float(raw or 0.0)
        available[field] = True
    for field in DETAILED_API_FIELDS:
        raw = row.get(field)
        values[field] = float(raw or 0.0)
        available[field] = detailed
    accuracy = row.get("pass_accuracy")
    try:
        completed = float(accuracy) if accuracy is not None else 0.0
    except (TypeError, ValueError):
        completed = 0.0
        detailed = False
    values["passes_completed"] = completed
    available["passes_completed"] = detailed
    rating = row.get("rating")
    # Stored as rating x exposure so that total/exposure is a minutes-weighted mean.
    values["rating"] = float(rating) * float(row["minutes"]) / 90.0 if rating is not None else 0.0
    available["rating"] = rating is not None
    return values, available


def _mark_values(row):
    values, available = api_mark_values(row)
    # More than one Understat record mapped to the same canonical player in one match is
    # an unresolved identity, not evidence to be summed.
    linked = row.get("process_records") == 1
    values["xg"] = float(row["process_xg"]) if linked else 0.0
    values["xa"] = float(row["process_xa"]) if linked else 0.0
    values["process_shots"] = float(row["process_shots"]) if linked else 0.0
    # Retained only to test whether the conventional sum carries what its parts do.
    values["xg_plus_xa"] = values["xg"] + values["xa"]
    for mark in PROCESS_MARKS:
        available[mark] = linked
    return values, available


API_MARKS = (
    *DENSE_API_FIELDS,
    *SPARSE_API_FIELDS,
    *DETAILED_API_FIELDS,
    "passes_completed",
    "rating",
)
ALL_MARKS = (*API_MARKS, *PROCESS_MARKS)


class PlayerLayer:
    """Cutoff-safe exponentially weighted player, role and club process aggregates."""

    def __init__(self, rows, config=None):
        self.config = config or LayerConfig()
        self.rows = list(rows)
        if not self.rows:
            raise ValueError("Player layer requires retained appearances")
        self.days = np.array([london_date(r["kickoff_time"]).toordinal() for r in self.rows])
        order = np.argsort(self.days, kind="stable")
        self.rows = [self.rows[i] for i in order]
        self.days = self.days[order]
        self.eligible = np.array(
            [
                max(
                    self.days[i] + 1,
                    london_date(r["retrieved_at"]).toordinal() + 1
                    if r.get("evidence_basis") != "retrospective"
                    else 0,
                )
                for i, r in enumerate(self.rows)
            ]
        )
        self.exposure = np.array([float(r["minutes"]) / 90.0 for r in self.rows])
        if not np.isfinite(self.exposure).all() or (self.exposure <= 0).any():
            raise ValueError("Player layer requires positive exposure")
        marks = [_mark_values(r) for r in self.rows]
        self.values = {m: np.array([v[m] for v, _ in marks]) for m in ALL_MARKS}
        self.available = {m: np.array([a[m] for _, a in marks]) for m in ALL_MARKS}
        self.roles = np.array([r["position"] or "UNK" for r in self.rows], dtype=object)
        self.teams = np.array([r["team_id"] for r in self.rows], dtype=object)
        self.team_xg = np.array(
            [np.nan if r["team_xg"] is None else float(r["team_xg"]) for r in self.rows]
        )
        self.by_player = defaultdict(list)
        self.by_team_match = {}
        for i, row in enumerate(self.rows):
            self.by_player[row["player_id"]].append(i)
        self.by_player = {k: np.array(v, dtype=int) for k, v in self.by_player.items()}
        team_matches = {}
        for i, row in enumerate(self.rows):
            key = row["team_id"], row["match_id"]
            if key not in team_matches:
                team_matches[key] = i
        self.team_match_index = defaultdict(list)
        for (team, _), i in sorted(team_matches.items(), key=lambda kv: kv[1]):
            self.team_match_index[team].append(i)
        self.team_match_index = {
            k: np.array(v, dtype=int) for k, v in self.team_match_index.items()
        }
        self._pools, self._team = {}, {}

    def _weights(self, indices, cutoff, half_life):
        return 2 ** (-(cutoff - self.days[indices]) / half_life)

    def _eligible_indices(self, indices, cutoff):
        return indices[self.eligible[indices] <= cutoff]

    def population(self, cutoff, mark, start_day=0):
        """Role-level rate per 90 and dispersion from every earlier eligible appearance."""
        key = cutoff, mark, start_day
        if key in self._pools:
            return self._pools[key]
        indices = np.flatnonzero(
            (self.eligible <= cutoff) & self.available[mark] & (self.days >= start_day)
        )
        weights = self._weights(indices, cutoff, self.config.long_half_life)
        exposure = weights * self.exposure[indices]
        counts = weights * self.values[mark][indices]
        league = counts.sum() / exposure.sum() if exposure.sum() > 0 else 0.0
        by_role, roles = {}, self.roles[indices]
        prior = self.config.pool_prior_matches
        for role in (*ROLES, "UNK"):
            mask = roles == role
            role_exposure, role_counts = exposure[mask].sum(), counts[mask].sum()
            by_role[role] = float((role_counts + prior * league) / (role_exposure + prior))
        residual = counts.sum() - exposure.sum() * league
        variance = float(
            (weights * (self.values[mark][indices] - self.exposure[indices] * league) ** 2).sum()
            / max(exposure.sum(), 1.0)
        )
        dispersion = max(variance / league, 1e-3) if league > 0 else 1.0
        result = {
            "league": float(league),
            "by_role": by_role,
            "dispersion": float(dispersion),
            "exposure": float(exposure.sum()),
            "residual": float(residual),
        }
        self._pools[key] = result
        return result

    def team_environment(self, team, cutoff):
        """Club attacking process rate per match, shrunk toward the league reference."""
        key = team, cutoff
        if key in self._team:
            return self._team[key]
        indices = self.team_match_index.get(team, np.array([], dtype=int))
        indices = self._eligible_indices(indices, cutoff)
        indices = indices[np.isfinite(self.team_xg[indices])]
        weights = self._weights(indices, cutoff, self.config.long_half_life)
        prior = self.config.team_prior_matches
        total = (weights * self.team_xg[indices]).sum()
        mass = weights.sum()
        value = (total + prior * LEAGUE_REFERENCE_XG) / (mass + prior)
        result = {"rate": float(value), "matches": float(mass), "observed": int(len(indices))}
        self._team[key] = result
        return result

    def aggregate(self, player_id, cutoff, mark, half_life, start_day=0):
        """Exponentially weighted exposure, mark total and opportunity for one player."""
        indices = self.by_player.get(player_id, np.array([], dtype=int))
        indices = self._eligible_indices(indices, cutoff)
        indices = indices[self.available[mark][indices] & (self.days[indices] >= start_day)]
        weights = self._weights(indices, cutoff, half_life)
        exposure = float((weights * self.exposure[indices]).sum())
        total = float((weights * self.values[mark][indices]).sum())
        environment = self.team_xg[indices]
        finite = np.isfinite(environment)
        opportunity = float(
            (weights[finite] * self.exposure[indices][finite] * environment[finite]).sum()
        )
        environment_exposure = float((weights[finite] * self.exposure[indices][finite]).sum())
        return {
            "exposure": exposure,
            "total": total,
            "opportunity": opportunity,
            "environment_exposure": environment_exposure,
            "appearances": int(len(indices)),
            "last_day": int(self.days[indices[-1]]) if len(indices) else None,
        }

    def role(self, player_id, cutoff):
        indices = self._eligible_indices(
            self.by_player.get(player_id, np.array([], dtype=int)), cutoff
        )
        if not len(indices):
            return "UNK"
        recent = indices[-10:]
        roles, counts = np.unique(self.roles[recent], return_counts=True)
        return str(roles[np.argmax(counts)])

    def club(self, player_id, cutoff):
        indices = self._eligible_indices(
            self.by_player.get(player_id, np.array([], dtype=int)), cutoff
        )
        return str(self.teams[indices[-1]]) if len(indices) else None


@dataclass(frozen=True)
class PlayerState:
    """Everything a candidate may read about one player at one cutoff."""

    player_id: str
    player_name: str | None
    cutoff: date
    role: str
    club: str | None
    target_club: str | None
    recent: dict
    long: dict
    share: dict
    environment: dict
    api: dict
    population: dict
    staleness: float | None

    def rate(self, mark, window="long"):
        return (self.recent if window == "recent" else self.long)[mark]["rate"]


def _shrunk(total, exposure, prior_mean, prior_strength):
    return (total + prior_strength * prior_mean) / (exposure + prior_strength)


def player_state(layer, player_id, cutoff, target_club=None):
    config = layer.config
    day = cutoff.toordinal()
    role = layer.role(player_id, day)
    club = layer.club(player_id, day)
    target_club = target_club or club
    recent, long, share = {}, {}, {}
    population = {}
    for mark in (*PROCESS_MARKS, *API_MARKS):
        pool = layer.population(day, mark)
        population[mark] = pool
        prior_mean = pool["by_role"].get(role, pool["league"])
        for half_life, store in (
            (config.recent_half_life, recent),
            (config.long_half_life, long),
        ):
            aggregate = layer.aggregate(player_id, day, mark, half_life)
            strength = config.rate_prior_matches
            store[mark] = {
                **aggregate,
                "prior_mean": float(prior_mean),
                "rate": float(
                    _shrunk(aggregate["total"], aggregate["exposure"], prior_mean, strength)
                ),
                "raw_rate": float(aggregate["total"] / aggregate["exposure"])
                if aggregate["exposure"] > 0
                else None,
            }
        # The opportunity share generalises to any mark: how much of the attacking
        # process the club generated while he played does this player account for.
        aggregate = long[mark]
        pool_share = prior_mean / LEAGUE_REFERENCE_XG
        strength = config.rate_prior_matches * LEAGUE_REFERENCE_XG
        share[mark] = {
            "share": float(
                _shrunk(aggregate["total"], aggregate["opportunity"], pool_share, strength)
            ),
            "raw_share": float(aggregate["total"] / aggregate["opportunity"])
            if aggregate["opportunity"] > 0
            else None,
            "pool_share": float(pool_share),
            "opportunity": float(aggregate["opportunity"]),
        }
        recent_aggregate = recent[mark]
        share[f"recent_{mark}"] = {
            "share": float(
                _shrunk(
                    recent_aggregate["total"],
                    recent_aggregate["opportunity"],
                    pool_share,
                    strength,
                )
            ),
            "pool_share": float(pool_share),
            "opportunity": float(recent_aggregate["opportunity"]),
        }
    environment = {
        "player": float(
            long["xg"]["opportunity"] / long["xg"]["environment_exposure"]
            if long["xg"]["environment_exposure"] > 0
            else LEAGUE_REFERENCE_XG
        ),
        "current_club": layer.team_environment(club, day) if club else None,
        "target_club": layer.team_environment(target_club, day) if target_club else None,
    }
    last_day = long["xg"]["last_day"] or long["assists"]["last_day"]
    indices = layer._eligible_indices(  # noqa: SLF001 - same-module accessor
        layer.by_player.get(player_id, np.array([], dtype=int)), day
    )
    name = layer.rows[indices[-1]].get("player_name") if len(indices) else None
    process_indices = np.flatnonzero(layer.available["xg"] & (layer.eligible <= day))
    process_start = int(layer.days[process_indices[0]]) if len(process_indices) else day
    matched = {"long": {}, "recent": {}}
    for mark in API_FEATURE_MARKS:
        pool = layer.population(day, mark, start_day=process_start)
        prior_mean = pool["by_role"].get(role, pool["league"])
        for window, half_life in (
            ("long", config.long_half_life),
            ("recent", config.recent_half_life),
        ):
            aggregate = layer.aggregate(player_id, day, mark, half_life, start_day=process_start)
            matched[window][mark] = {
                **aggregate,
                "prior_mean": float(prior_mean),
                "rate": float(
                    _shrunk(
                        aggregate["total"],
                        aggregate["exposure"],
                        prior_mean,
                        config.rate_prior_matches,
                    )
                ),
            }
    return PlayerState(
        player_id=player_id,
        player_name=name,
        cutoff=cutoff,
        role=role,
        club=club,
        target_club=target_club,
        recent=recent,
        long=long,
        share=share,
        environment=environment,
        api={
            "appearances": int(len(indices)),
            "depth_matched": matched,
            "process_window_start": str(date.fromordinal(process_start)),
        },
        population=population,
        staleness=float(day - last_day) if last_day else None,
    )


API_FEATURE_MARKS = ("goals", "shots", "shots_on_target", "assists", "key_passes")

CANDIDATES = {
    "pooled_role": (),
    "combined_long": ("combined_rate",),
    "recent_raw": ("recent_rate",),
    "long_run": ("long_rate",),
    "recent_long": ("recent_rate", "long_rate"),
    "long_plus_env": ("long_rate", "target_environment"),
    "context_share": ("long_share", "target_environment"),
    "context_share_recent": ("long_share", "recent_share", "target_environment"),
    "api_only": ("api_long", "api_recent", "api_exposure", "api_staleness"),
    "api_depth_matched": ("api_long", "api_recent", "api_exposure", "api_staleness"),
    "api_rating": ("api_long", "api_recent", "api_exposure", "api_staleness", "rating"),
}
CANDIDATE_NOTES = {
    "pooled_role": "Role population rate only; the player contributes nothing.",
    "combined_long": "Long-run rate of the summed xG+xA mark, testing whether the conventional aggregate carries what the separate component does.",
    "recent_raw": "Recent shrunk per-90 rate, the naive form of 'he is in form'.",
    "long_run": "Long-horizon shrunk per-90 rate.",
    "recent_long": "Both horizons, so recent information must earn its weight.",
    "long_plus_env": "Long-run raw rate together with the club environment it will play in.",
    "context_share": "Portable share of team attacking process times the target club environment.",
    "context_share_recent": "Share on both horizons times the target club environment.",
    "api_only": "The V1 API-only feature family: no Understat process evidence.",
    "api_depth_matched": "API-only features and uncertainty restricted to the calendar window with retained process history; identical evaluation cases.",
    "api_rating": "The V1 API-only family plus the proprietary rating, as an ablation.",
}


def _log_ratio(value, reference, clip):
    if value is None or reference is None or value <= 0 or reference <= 0:
        return 0.0
    return float(np.clip(np.log(value / reference), -clip, clip))


def feature_block(state, block, mark):
    config_clip = 2.5
    pool = state.population[mark]
    prior_mean = pool["by_role"].get(state.role, pool["league"])
    if block == "recent_rate":
        return [("recent_rate", _log_ratio(state.rate(mark, "recent"), prior_mean, config_clip))]
    if block == "long_rate":
        return [("long_rate", _log_ratio(state.rate(mark, "long"), prior_mean, config_clip))]
    if block == "combined_rate":
        combined = state.population["xg_plus_xa"]
        reference = combined["by_role"].get(state.role, combined["league"])
        return [
            (
                "combined_rate",
                _log_ratio(state.rate("xg_plus_xa", "long"), reference, config_clip),
            )
        ]
    if block == "long_share":
        entry = state.share[mark]
        return [("long_share", _log_ratio(entry["share"], entry["pool_share"], config_clip))]
    if block == "recent_share":
        entry = state.share[f"recent_{mark}"]
        return [("recent_share", _log_ratio(entry["share"], entry["pool_share"], config_clip))]
    if block == "target_environment":
        target = state.environment["target_club"]
        rate = target["rate"] if target else LEAGUE_REFERENCE_XG
        return [("target_environment", _log_ratio(rate, LEAGUE_REFERENCE_XG, config_clip))]
    if block in ("api_long", "api_recent"):
        window = "long" if block == "api_long" else "recent"
        features = []
        for field in API_FEATURE_MARKS:
            entry = (state.long if window == "long" else state.recent)[field]
            features.append(
                (
                    f"{block}_{field}",
                    _log_ratio(entry["rate"], entry["prior_mean"], config_clip),
                )
            )
        return features
    if block == "api_exposure":
        exposure = state.long["assists"]["exposure"]
        return [
            ("log_exposure", float(np.log1p(exposure) - np.log1p(10.0))),
        ]
    if block == "api_staleness":
        last_day = state.long["assists"]["last_day"]
        stale = state.cutoff.toordinal() - last_day if last_day is not None else None
        return [("staleness", float(min(stale, 270) / 90) if stale is not None else 0.0)]
    if block == "rating":
        return [
            (
                f"rating_{window}",
                _log_ratio(
                    (state.long if window == "long" else state.recent)["rating"]["rate"],
                    (state.long if window == "long" else state.recent)["rating"]["prior_mean"],
                    config_clip,
                ),
            )
            for window in ("long", "recent")
        ]
    raise ValueError(f"Unknown feature block: {block}")


def design(state, candidate, mark):
    if candidate == "api_depth_matched":
        state = replace(
            state,
            long=state.api["depth_matched"]["long"],
            recent=state.api["depth_matched"]["recent"],
        )
    blocks = CANDIDATES[candidate]
    features = []
    for block in blocks:
        features.extend(feature_block(state, block, mark))
    return [name for name, _ in features], np.array([value for _, value in features])
