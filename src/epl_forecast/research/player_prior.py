"""Cutoff-safe API-FOOTBALL player features for a joint research prior."""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from epl_forecast.datasets import Dataset, timestamp
from epl_forecast.squads import ROLES, PlayerHistory

LONDON = ZoneInfo("Europe/London")
COUNT_FIELDS = ("passes_total", "shots", "key_passes", "duels_won", "saves")


def london_date(value):
    return (
        timestamp(value).astimezone(LONDON).date() if isinstance(value, (str, datetime)) else value
    )


def day_cutoff(value):
    return datetime.combine(london_date(value), time(), LONDON)


@dataclass(frozen=True)
class PriorConfig:
    recent_half_life: float = 45.0
    long_half_life: float = 240.0
    shrinkage_minutes: float = 900.0
    pool_minutes: float = 9000.0
    local_sd_floor: float = 0.15
    local_sd_sparse: float = 0.45
    meaningful_minutes: float = 30.0

    def __post_init__(self):
        if any(not np.isfinite(v) or v <= 0 for v in vars(self).values()):
            raise ValueError("Prior configuration values must be finite and positive")
        if self.recent_half_life >= self.long_half_life:
            raise ValueError("Recent half-life must be shorter than long-run half-life")


@dataclass(frozen=True)
class PlayerFeatures:
    player_id: str
    cutoff: date
    role: str
    competition_id: str
    season_id: str
    values: tuple[float, ...]
    effective_minutes: float
    effective_matches: float
    relevant_minutes: float
    days_since_meaningful_minutes: int | None
    age: float | None
    local_sd: float
    observed_minutes: tuple[float, ...]
    latest_evidence_date: date | None
    evidence_matches: tuple[str, ...]


def load_prior_inputs(root):
    root = Path(root)
    manifest = json.loads((root / "input_manifest.json").read_text())
    for batch in manifest["manifests"]:
        r = batch["request"]
        if r["provider"] != "api_football" or r["context"].get("endpoint") not in {
            "fixtures",
            "players",
        }:
            raise ValueError(
                "Player-prior inputs must contain API-FOOTBALL fixtures and player profiles only"
            )
    data = Dataset(root, manifests=manifest["manifests"])
    try:
        data.verify()
        profiles = []
        profile_seasons = {
            b["request"]["source_sha256"]: int(b["request"]["context"]["season"])
            for b in data.manifests
            if b["request"]["context"].get("endpoint") == "players"
        }
        for row in data.rows("SELECT * FROM players_observations WHERE birth_date IS NOT NULL"):
            year = profile_seasons.get(row["source_sha256"])
            if year is not None:
                profiles.append({**row, "available_on": date(year + 1, 7, 1)})
        rows = data.player_history()
        return data.matches(), PlayerPriorFeatures(rows, profiles), manifest
    finally:
        data.close()


class PlayerPriorFeatures:
    def __init__(self, rows, profiles=(), config=None):
        if any(r.get("provider") != "api_football" for r in rows):
            raise ValueError("Player features require API-FOOTBALL appearances only")
        self.history = PlayerHistory([dict(r) for r in rows])
        self.config = config or PriorConfig()
        self.fields = (*COUNT_FIELDS, "rating")
        self.profiles = defaultdict(list)
        for profile in profiles:
            if profile.get("provider") != "api_football":
                raise ValueError("Player profiles require API-FOOTBALL provenance")
            self.profiles[profile["player_id"]].append(dict(profile))
        rows = self.history.rows
        self.days = np.array([london_date(r["kickoff_time"]).toordinal() for r in rows])
        self.eligible = np.array(
            [
                max(
                    self.days[i] + 1,
                    london_date(r["retrieved_at"]).toordinal() + 1
                    if r.get("evidence_basis") != "retrospective"
                    else 0,
                )
                for i, r in enumerate(rows)
            ]
        )
        self.minutes = np.array([float(r["minutes"]) for r in rows])
        if not np.isfinite(self.minutes).all() or (self.minutes < 0).any():
            raise ValueError("Invalid player exposure")
        self.statistics = np.array(
            [
                [np.nan if r.get(field) is None else float(r[field]) for field in self.fields]
                for r in rows
            ]
        ).reshape(len(rows), len(self.fields))
        if np.isinf(self.statistics).any() or (self.statistics < 0).any():
            raise ValueError("Invalid player statistic")
        self.roles = np.array([r["position"] or "UNK" for r in rows], dtype=str)
        self.competitions = np.array([r["competition_id"] for r in rows], dtype=str)
        self.seasons = np.array([r["season_id"] for r in rows], dtype=str)
        indices = defaultdict(list)
        self.by_team = defaultdict(list)
        for i, row in enumerate(rows):
            indices[row["player_id"]].append(i)
            self.by_team[row["team_id"]].append(i)
        self.by_player = {pid: np.array(values, dtype=int) for pid, values in indices.items()}
        self._pools, self._features, self._references = {}, {}, {}

    @staticmethod
    def names(include_rating=False):
        fields = (*COUNT_FIELDS, "rating") if include_rating else COUNT_FIELDS
        return tuple(f"{window}_{field}" for window in ("recent", "long") for field in fields) + (
            "role_intercept",
            "log_effective_minutes",
            "staleness",
            "coverage",
            "age",
            "competition_level",
        )

    def _moments(self, mask, cutoff):
        indices = np.flatnonzero(mask & (self.eligible <= cutoff.toordinal()) & (self.minutes > 0))
        minutes = self.minutes[indices]
        values = self.statistics[indices]
        observed = np.isfinite(values)
        decay = 2 ** (-(cutoff.toordinal() - self.days[indices]) / self.config.long_half_life)
        weights = decay[:, None] * minutes[:, None] * observed
        rates = np.nan_to_num(values) * (90 / minutes[:, None])
        rates[:, -1] = np.nan_to_num(values[:, -1])
        return weights.sum(axis=0), (weights * rates).sum(axis=0), (weights * rates**2).sum(axis=0)

    def _pool(self, cutoff, role, competition, season):
        key = cutoff, role, competition, season
        if key not in self._pools:
            role_mask = (
                self.roles == role if role in ROLES else np.ones(len(self.roles), dtype=bool)
            )
            # Each level borrows from its parent; only earlier fixture dates enter any level.
            mean, second = np.zeros(len(self.fields)), np.ones(len(self.fields))
            for mask in (
                role_mask,
                role_mask & (self.competitions == competition),
                role_mask & (self.competitions == competition) & (self.seasons == season),
            ):
                exposure, total, squares = self._moments(mask, cutoff)
                strength = self.config.pool_minutes
                mean = (total + strength * mean) / (exposure + strength)
                second = (squares + strength * second) / (exposure + strength)
            sd = np.sqrt(np.maximum(second - mean**2, 0.1**2))
            self._pools[key] = mean, sd
        return self._pools[key]

    def for_player(self, player_id, cutoff, competition, season, include_rating=False):
        cutoff = london_date(cutoff)
        key = player_id, cutoff, competition, season, include_rating
        if key in self._features:
            return self._features[key]
        indices = self.by_player.get(player_id, np.array([], dtype=int))
        indices = indices[self.eligible[indices] <= cutoff.toordinal()]
        last = self.history.rows[indices[-1]] if len(indices) else None
        role = (last["position"] or "UNK") if last else "UNK"
        source_competition = last["competition_id"] if last else competition
        mean, sd = self._pool(cutoff, role, source_competition, season)
        active = indices[self.minutes[indices] > 0]
        minutes = self.minutes[active]
        age_days = cutoff.toordinal() - self.days[active]
        values = self.statistics[active]
        observed = np.isfinite(values)
        count = len(self.fields) if include_rating else len(COUNT_FIELDS)
        vector, exposures = [], []
        for half_life in (self.config.recent_half_life, self.config.long_half_life):
            decay = 2 ** (-age_days / half_life)
            weighted_minutes = decay[:, None] * minutes[:, None] * observed
            denominator = weighted_minutes.sum(axis=0)
            total = (decay[:, None] * np.nan_to_num(values) * 90).sum(axis=0)
            total[-1] = (weighted_minutes[:, -1] * np.nan_to_num(values[:, -1])).sum()
            rate = (total + self.config.shrinkage_minutes * mean) / (
                denominator + self.config.shrinkage_minutes
            )
            vector.extend(np.clip((rate[:count] - mean[:count]) / sd[:count], -3, 3))
            exposures.append(denominator)
        long_weights = 2 ** (-age_days / self.config.long_half_life) * minutes / 90
        effective_minutes = float(long_weights.sum() * 90)
        effective_matches = (
            float(long_weights.sum() ** 2 / (long_weights @ long_weights)) if len(active) else 0.0
        )
        relevant = [0, 4] if role == "GK" else [0, 1, 2, 3]
        if include_rating:
            relevant.append(5)
        relevant_minutes = float(np.mean(exposures[-1][relevant]))
        coverage = relevant_minutes / effective_minutes if effective_minutes else 0.0
        meaningful = indices[self.minutes[indices] >= self.config.meaningful_minutes]
        stale = int(cutoff.toordinal() - self.days[meaningful[-1]]) if len(meaningful) else None
        birthdays = {
            p["birth_date"]
            for p in self.profiles.get(player_id, [])
            if p["available_on"] <= cutoff
            and (
                p.get("evidence_basis") == "retrospective"
                or timestamp(p["retrieved_at"]) <= day_cutoff(cutoff)
            )
        }
        age = None
        if len(birthdays) == 1 and last:
            birthday = next(iter(birthdays))
            birthday = date.fromisoformat(birthday) if isinstance(birthday, str) else birthday
            age = (cutoff - birthday).days / 365.25
            if not 14 <= age <= 55:
                age = None
        vector.extend(
            [
                1.0,
                np.log1p(effective_minutes / self.config.shrinkage_minutes),
                min(stale / 90, 3) if stale is not None else 0.0,
                coverage,
                np.clip((age - 27) / 5, -3, 3) if age is not None else 0.0,
                float(source_competition == "eng-championship"),
            ]
        )
        local_sd = np.sqrt(
            self.config.local_sd_floor**2
            + self.config.local_sd_sparse**2
            * self.config.shrinkage_minutes
            / (self.config.shrinkage_minutes + relevant_minutes)
        )
        result = PlayerFeatures(
            player_id,
            cutoff,
            role,
            source_competition,
            season,
            tuple(float(v) for v in vector),
            effective_minutes,
            effective_matches,
            relevant_minutes,
            stale,
            age,
            float(local_sd),
            tuple(float(v) for v in exposures[-1][:count]),
            date.fromordinal(int(self.days[indices[-1]])) if len(indices) else None,
            tuple(self.history.rows[i]["match_id"] for i in indices),
        )
        self._features[key] = result
        return result

    def design(self, features):
        values = np.array(features.values)
        result = np.zeros((len(ROLES), len(values)))
        if features.role in ROLES:
            result[ROLES.index(features.role)] = values
        else:
            result[:] = values / len(ROLES)
        return result.ravel()

    def reference_weights(self, team, cutoff, max_matches=5):
        cutoff = london_date(cutoff)
        key = team, cutoff, max_matches
        if key not in self._references:
            matches = defaultdict(list)
            for i in self.by_team.get(team, []):
                if self.eligible[i] <= cutoff.toordinal() and self.minutes[i] > 0:
                    matches[self.history.rows[i]["match_id"]].append(i)
            latest = sorted(matches, key=lambda mid: (self.days[matches[mid][0]], mid))[
                -max_matches:
            ]
            weights, mass = defaultdict(float), 0.0
            for mid in latest:
                indices = matches[mid]
                decay = 2 ** (
                    -(cutoff.toordinal() - self.days[indices[0]]) / self.config.recent_half_life
                )
                total = self.minutes[indices].sum()
                mass += decay
                for i in indices:
                    weights[self.history.rows[i]["player_id"]] += decay * self.minutes[i] / total
            self._references[key] = (
                {pid: float(w / mass) for pid, w in sorted(weights.items())} if mass else {}
            )
        return dict(self._references[key])
