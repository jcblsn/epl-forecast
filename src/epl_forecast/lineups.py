from dataclasses import dataclass
from datetime import datetime

import numpy as np

from epl_forecast.data.squads import ROLES, Candidate, Squad

FORMATIONS = ((1, 4, 4, 2), (1, 4, 3, 3), (1, 3, 5, 2), (1, 3, 4, 3), (1, 5, 4, 1))


@dataclass
class LineupDraws:
    candidates: tuple[Candidate, ...]
    starts: np.ndarray
    minutes: np.ndarray
    formations: np.ndarray

    def summary(self):
        return [
            {
                "player_id": player.player_id,
                "name": player.name,
                "position": player.position,
                "anonymous": player.anonymous,
                "history_fixtures": len(player.history),
                "start_probability": float(self.starts[:, i].mean()),
                "expected_minutes": float(self.minutes[:, i].mean()),
                "minutes_sd": float(self.minutes[:, i].std()),
            }
            for i, player in enumerate(self.candidates)
        ]


def availability_probability(player: Candidate, kickoff: datetime):
    assumption = player.availability
    if assumption is None or kickoff >= assumption.expires_at:
        return 1.0
    if kickoff < assumption.observed_at:
        raise ValueError("Cannot project availability before it was observed")
    if assumption.recovery == "step":
        return assumption.probability
    fraction = (kickoff - assumption.observed_at) / (assumption.expires_at - assumption.observed_at)
    return assumption.probability + (1 - assumption.probability) * fraction


def sample_lineups(squad: Squad, kickoff: datetime, rng, size=1):
    if kickoff.tzinfo is None or kickoff < squad.cutoff:
        raise ValueError("Lineup kickoff must be at or after the timezone-aware cutoff")
    if type(size) is not int or size < 1:
        raise ValueError("Lineup sample size must be a positive integer")
    candidates = list(squad.candidates)
    # Reserves are explicit unknown players, never the target fixture's participants.
    for role, count in zip(ROLES, (1, 5, 5, 3), strict=True):
        for index in range(count):
            candidates.append(
                Candidate(
                    f"unknown:{squad.team_id}:{role}:{index}",
                    "",
                    f"Unknown {role} {index + 1}",
                    squad.team_id,
                    role,
                    None,
                    "missing squad or unavailable replacement",
                    anonymous=True,
                )
            )
    n = len(candidates)
    starts, minutes = np.zeros((size, n), dtype=bool), np.zeros((size, n))
    formations = np.zeros((size, 4), dtype=int)
    weights = np.array([p.start_weight for p in candidates])
    availability = np.array([availability_probability(p, kickoff) for p in candidates])
    by_role = {
        role: np.array([i for i, p in enumerate(candidates) if p.position == role])
        for role in ROLES
    }

    def choose(indices, count):
        if not count:
            return np.array([], dtype=int)
        return rng.choice(
            indices, size=count, replace=False, p=weights[indices] / weights[indices].sum()
        )

    for draw in range(size):
        available = rng.random(n) < availability
        known = {
            role: np.array(
                [i for i in indices if available[i] and not candidates[i].anonymous], dtype=int
            )
            for role, indices in by_role.items()
        }
        shortages = [
            sum(
                max(0, count - len(known[role]))
                for role, count in zip(ROLES, formation, strict=True)
            )
            for formation in FORMATIONS
        ]
        possible = np.flatnonzero(np.array(shortages) == min(shortages))
        formation = FORMATIONS[rng.choice(possible)]
        formations[draw] = formation
        for role, count in zip(ROLES, formation, strict=True):
            selected = choose(known[role], min(count, len(known[role])))
            if len(selected) < count:
                unknown = [i for i in by_role[role] if candidates[i].anonymous]
                selected = np.r_[selected, unknown[: count - len(selected)]]
            starts[draw, selected] = True
            minutes[draw, selected] = 90
        bench_pool = np.array(
            [
                i
                for i, p in enumerate(candidates)
                if available[i] and not starts[draw, i] and not p.anonymous and p.position != "UNK"
            ],
            dtype=int,
        )
        bench = choose(bench_pool, min(9, len(bench_pool)))
        subbed = set()
        for incoming in rng.permutation(bench):
            role = candidates[incoming].position
            if len(subbed) == 5:
                break
            if rng.random() > (0.02 if role == "GK" else 0.65):
                continue
            outgoing = [i for i in by_role[role] if starts[draw, i] and i not in subbed]
            if not outgoing:
                continue
            outgoing = int(rng.choice(outgoing))
            past = [m for m, s in candidates[incoming].history if s == 0 and 0 < m < 90]
            duration = float(rng.choice(past)) if past else float(rng.integers(10, 31))
            duration = min(45, max(1, duration))
            minutes[draw, outgoing] = 90 - duration
            minutes[draw, incoming] = duration
            subbed.add(outgoing)
    return LineupDraws(tuple(candidates), starts, minutes, formations)
