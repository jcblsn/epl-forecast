"""Provider-independent squad and exposure inputs for lineup models."""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from epl_forecast.datasets import timestamp

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
    season_id: str
    name: str
    team_id: str
    position: str
    membership_observed_at: datetime | None
    membership_basis: str
    history: tuple[tuple[float, float | None], ...] = ()
    availability: Availability | None = None
    anonymous: bool = False
    membership_probability: float = 1.0

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
            if not 0 <= player.membership_probability <= 1:
                raise ValueError("Invalid membership probability")
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


class PlayerHistory:
    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: (timestamp(r["kickoff_time"]), r["player_id"]))
        self.by_player, self.by_season = defaultdict(list), defaultdict(list)
        seen = set()
        for r in self.rows:
            key = r["match_id"], r["player_id"]
            if key in seen:
                raise ValueError("Duplicate player fixture in history")
            seen.add(key)
            self.by_player[r["player_id"]].append(r)
            self.by_season[r["season_id"]].append(r)

    @staticmethod
    def _past(row, cutoff, strict):
        if timestamp(row["kickoff_time"]).date() >= timestamp(cutoff).date():
            return False
        observed = row.get("retrieved_at")
        if strict or (observed and row.get("evidence_basis") != "retrospective"):
            return observed is not None and timestamp(observed) <= cutoff
        return True

    def exposure(self, player, cutoff, strict=False):
        timestamp(cutoff)
        rows = [r for r in self.by_player.get(player, []) if self._past(r, cutoff, strict)]
        return tuple((float(r["minutes"]), r["starts"]) for r in rows[-5:])

    def retrospective_squad(self, team, season, cutoff, carry_forward=False):
        timestamp(cutoff)
        latest = {}
        for r in self.by_season.get(season, []):
            if self._past(r, cutoff, False):
                latest[r["player_id"]] = r
        candidates = []
        for pid, r in sorted(latest.items()):
            if r["team_id"] == team:
                history = tuple(
                    (float(h["minutes"]), h["starts"])
                    for h in self.by_season[season]
                    if h["player_id"] == pid and self._past(h, cutoff, False)
                )[-5:]
                candidates.append(
                    Candidate(
                        pid,
                        season,
                        r["player_name"],
                        team,
                        r["position"] or "UNK",
                        None,
                        "last prior fixture; retrospective participation proxy",
                        history,
                    )
                )
        if carry_forward:
            previous = f"{int(season[:4]) - 1}-{int(season[:4])}"
            last = {}
            for r in self.by_season.get(previous, []):
                if self._past(r, cutoff, False):
                    last[r["player_id"]] = r
            final_day = max((timestamp(r["kickoff_time"]) for r in last.values()), default=None)
            for pid, r in sorted(last.items()):
                if (
                    pid in latest
                    or r["team_id"] != team
                    or (final_day - timestamp(r["kickoff_time"])).days > 45
                ):
                    continue
                candidates.append(
                    Candidate(
                        pid,
                        previous,
                        r["player_name"],
                        team,
                        r["position"] or "UNK",
                        None,
                        "unverified previous-season membership prior",
                        self.exposure(pid, cutoff),
                        membership_probability=0.7,
                    )
                )
        return Squad(team, season, cutoff, tuple(candidates), "retrospective prior-fixture proxy")


def captured_squads(data, cutoff, history=None):
    cutoff = timestamp(cutoff)
    scope_times = {}
    for m in data.manifests:
        r = m["request"]
        c = r["context"]
        if r["provider"] == "api_football" and c.get("endpoint") == "players/squads":
            time = timestamp(r["retrieved_at"])
            scope = str(c["team"])
            if time <= cutoff:
                scope_times[scope] = max(time, scope_times.get(scope, time))
    players = {r["player_id"]: r for r in data.rows("SELECT * FROM players")}
    latest_fpl = max(
        (
            timestamp(m["request"]["retrieved_at"])
            for m in data.manifests
            if m["request"]["provider"] == "fpl"
            and timestamp(m["request"]["retrieved_at"]) <= cutoff
        ),
        default=None,
    )
    availability = {
        r["player_id"]: r
        for r in data.rows(
            "SELECT * FROM availability_observations WHERE provider='fpl' AND retrieved_at=?",
            [latest_fpl],
        )
        if r["player_id"]
    }
    grouped = defaultdict(list)
    for r in data.rows("SELECT * FROM memberships WHERE basis='captured_squad'"):
        observed = r["retrieved_at"]
        if observed != scope_times.get(r["scope"]) or observed > cutoff:
            continue
        pid = r["player_id"]
        signal = availability.get(pid)
        assumption = None
        if signal and signal["chance_next_round"] is not None:
            # This is an explicit model scenario, not a provider recovery-date claim.
            assumption = Availability(
                signal["retrieved_at"],
                signal["chance_next_round"] / 100,
                signal["retrieved_at"] + timedelta(days=28),
                "captured round probability; 28-day scenario",
                "linear",
            )
        grouped[r["team_id"], r["season_id"]].append(
            Candidate(
                pid,
                r["season_id"],
                players.get(pid, {}).get("name") or pid,
                r["team_id"],
                r["position"] or "UNK",
                observed,
                "captured current squad",
                history.exposure(pid, cutoff) if history else (),
                assumption,
            )
        )
    return {
        team: Squad(
            team,
            season,
            cutoff,
            tuple(sorted(rows, key=lambda r: r.player_id)),
            "captured current squad; historical exposure retrospective",
        )
        for (team, season), rows in grouped.items()
    }
