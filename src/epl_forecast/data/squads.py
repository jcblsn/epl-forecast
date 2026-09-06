"""Cutoff-specific squad evidence; retrospective observations are explicitly labeled."""

import csv
import gzip
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from epl_forecast.data.live import fpl_teams, read_live_snapshot, timestamp

ROLES = ("GK", "DEF", "MID", "FWD")


@dataclass(frozen=True)
class Availability:
    observed_at: datetime
    probability: float
    expires_at: datetime
    source: str
    recovery: str = "step"

    def __post_init__(self):
        if self.observed_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("Availability timestamps require timezones")
        if not 0 <= self.probability <= 1 or self.expires_at <= self.observed_at:
            raise ValueError("Invalid availability probability or expiry")
        if self.recovery not in {"step", "linear"}:
            raise ValueError("Unknown availability recovery law")


@dataclass(frozen=True)
class Candidate:
    player_id: str
    player_season_id: str
    name: str
    team_id: str
    position: str
    membership_observed_at: datetime | None
    membership_basis: str
    history: tuple[tuple[float, float | None], ...] = ()
    availability: Availability | None = None
    anonymous: bool = False

    @property
    def start_weight(self):
        starts = [m / 90 if s is None else s for m, s in self.history[-5:]]
        return (sum(starts) + 0.6) / (len(starts) + 2)


@dataclass(frozen=True)
class Squad:
    team_id: str
    season_id: str
    cutoff: datetime
    candidates: tuple[Candidate, ...]
    evidence: str
    source_sha256: str | None = None

    def __post_init__(self):
        if self.cutoff.tzinfo is None:
            raise ValueError("Squad cutoff requires timezone")
        if len({p.player_id for p in self.candidates}) != len(self.candidates):
            raise ValueError("Duplicate squad identity")
        for player in self.candidates:
            if player.team_id != self.team_id or player.position not in (*ROLES, "UNK"):
                raise ValueError("Invalid candidate team or position")
            if player.membership_observed_at and player.membership_observed_at > self.cutoff:
                raise ValueError("Squad membership was observed after cutoff")
            if player.availability and player.availability.observed_at > self.cutoff:
                raise ValueError("Availability was observed after cutoff")

    def with_availability(self, player_id: str, assumption: Availability):
        if player_id not in {p.player_id for p in self.candidates}:
            raise ValueError("Availability scenario player is outside the candidate squad")
        return replace(
            self,
            candidates=tuple(
                replace(p, availability=assumption) if p.player_id == player_id else p
                for p in self.candidates
            ),
        )


def load_player_history(path: Path) -> list[dict]:
    with gzip.open(path, "rt", newline="") as stream:
        return list(csv.DictReader(stream))


class PlayerHistory:
    def __init__(self, rows: list[dict]):
        self.rows = sorted(rows, key=lambda r: (r["kickoff_time"], r["player_season_id"]))
        self.by_season = defaultdict(list)
        self.by_code = defaultdict(list)
        identities, element_codes = defaultdict(set), defaultdict(set)
        seen = set()
        for row in self.rows:
            key = row["match_id"], row["player_season_id"]
            if key in seen:
                raise ValueError("Duplicate player fixture in history")
            seen.add(key)
            self.by_season[row["season_id"]].append(row)
            code = row.get("fpl_player_code")
            if code:
                identities[row["season_id"], code].add(row["player_season_id"])
                element_codes[row["player_season_id"]].add(code)
                self.by_code[code].append(row)
        if any(len(ids) > 1 for ids in (*identities.values(), *element_codes.values())):
            raise ValueError("Ambiguous player code within a season")

    @staticmethod
    def _past(row, cutoff, strict):
        if timestamp(row["kickoff_time"]).date() >= cutoff.astimezone(UTC).date():
            return False
        observed = row.get("historical_observed_at")
        if observed:
            return timestamp(observed) <= cutoff
        return not strict

    def exposure(self, code, cutoff, strict=False):
        if cutoff.tzinfo is None:
            raise ValueError("Exposure cutoff requires timezone")
        rows = [r for r in self.by_code.get(str(code), []) if self._past(r, cutoff, strict)]
        return tuple(
            (float(r["minutes"]), float(r["starts"]) if r["starts"] != "" else None)
            for r in rows[-5:]
        )

    def retrospective_squad(self, team, season, cutoff):
        if cutoff.tzinfo is None:
            raise ValueError("Squad cutoff requires timezone")
        latest, history = {}, defaultdict(list)
        for row in self.by_season.get(season, []):
            if not self._past(row, cutoff, strict=False):
                continue
            identity = row["player_season_id"]
            latest[identity] = row
            history[identity].append(
                (float(row["minutes"]), float(row["starts"]) if row["starts"] != "" else None)
            )
        candidates = []
        for identity, row in sorted(latest.items()):
            if row["team_id"] != team:
                continue
            candidates.append(
                Candidate(
                    f"fpl:{row['fpl_player_code']}" if row.get("fpl_player_code") else identity,
                    identity,
                    row["player_name"],
                    team,
                    row.get("position") or "UNK",
                    None,
                    f"last prior fixture {row['match_id']}; publication time unknown",
                    tuple(history[identity][-5:]),
                )
            )
        return Squad(team, season, cutoff, tuple(candidates), "retrospective prior-fixture proxy")


def snapshot_squads(directory: Path, cutoff: datetime, history: PlayerHistory | None = None):
    manifest = read_live_snapshot(directory)
    source = next(f for f in manifest["files"] if f["name"] == "fpl_bootstrap.json")
    observed = timestamp(source["retrieved_at"])
    if cutoff.tzinfo is None or observed > cutoff:
        raise ValueError("Squad snapshot was collected after cutoff")
    bootstrap = json.loads((directory / "fpl_bootstrap.json").read_text())
    mapping, _ = fpl_teams(bootstrap)
    players = defaultdict(list)
    codes, elements = set(), set()
    for row in bootstrap["elements"]:
        code, element = str(row["code"]), str(row["id"])
        if code in codes or element in elements:
            raise ValueError("Ambiguous snapshot player identity")
        codes.add(code)
        elements.add(element)
        if row["element_type"] not in range(1, 5):
            continue
        if row.get("removed") or row["status"] == "u":
            continue
        team = mapping[row["team"]]
        chance = row.get("chance_of_playing_next_round")
        probability = (
            float(chance) / 100
            if chance is not None
            else {"a": 1.0, "d": 0.5, "i": 0.0, "s": 0.0, "n": 0.0}.get(row["status"], 0.5)
        )
        players[team].append(
            Candidate(
                f"fpl:{code}",
                f"{manifest['season_id']}:{element}",
                row["web_name"],
                team,
                ROLES[row["element_type"] - 1],
                observed,
                "captured FPL squad proxy; official registration not independently verified",
                history.exposure(code, cutoff) if history else (),
                Availability(
                    observed, probability, observed + timedelta(days=28), "FPL snapshot", "linear"
                ),
            )
        )
    return {
        team: Squad(
            team,
            manifest["season_id"],
            cutoff,
            tuple(sorted(players[team], key=lambda p: p.player_id)),
            "timestamped FPL squad; exposure may use retrospective corrected histories",
            source["sha256"],
        )
        for team in mapping.values()
    }
