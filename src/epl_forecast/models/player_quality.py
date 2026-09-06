"""Joint dynamic club Quality/Tilt and population-pooled scalar player Quality."""

from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, time

import numpy as np

from epl_forecast.data.squads import PlayerHistory
from epl_forecast.lineups import sample_lineups
from epl_forecast.models.poisson import PoissonMixture
from epl_forecast.models.quality_tilt import QualityTiltFilter
from epl_forecast.models.quality_tilt_scores import GammaPoissonMixture, ScoreMixture


def player_identity(row):
    return (
        f"fpl:{row['fpl_player_code']}" if row.get("fpl_player_code") else row["player_season_id"]
    )


class PlayerQualityFilter(QualityTiltFilter):
    def __init__(
        self,
        history: PlayerHistory,
        player_sd=0.6,
        lineup_draws=64,
        seed=610,
        squads=None,
        kickoffs=None,
        **kwargs,
    ):
        if not np.isfinite(player_sd) or player_sd <= 0:
            raise ValueError("Player population SD must be finite and positive")
        if type(lineup_draws) is not int or lineup_draws < 1:
            raise ValueError("Lineup draws must be a positive integer")
        self.player_history = history
        self.player_sd, self.lineup_draws, self.seed = player_sd, lineup_draws, seed
        self.squads, self.kickoffs = squads or {}, kickoffs or {}
        self.observations = defaultdict(list)
        for row in history.rows:
            self.observations[row["match_id"], row["team_id"]].append(row)
        super().__init__(**{"dispersion": None, **kwargs})

    def _reset(self):
        super()._reset()
        self.player_index = {}

    def _ensure_team(self, team, season, day):
        old_teams, players = len(self.team_index), len(self.player_index)
        super()._ensure_team(team, season, day)
        if len(self.team_index) > old_teams and players:
            boundary = 2 + 2 * old_teams
            order = np.r_[
                np.arange(boundary),
                len(self.mean) - 2,
                len(self.mean) - 1,
                np.arange(boundary, len(self.mean) - 2),
            ]
            self.mean = self.mean[order]
            self.covariance = self.covariance[np.ix_(order, order)]
            self.player_index = {key: index + 2 for key, index in self.player_index.items()}

    def _prepare_observations(self, games):
        identities = set()
        for match in games:
            for team in (match.fixture.home_team_id, match.fixture.away_team_id):
                for row in self.observations[match.fixture.match_id, team]:
                    if float(row["minutes"]) > 0:
                        identities.add(player_identity(row))
        new = sorted(identities - self.player_index.keys())
        start = len(self.mean)
        self.player_index.update({key: start + i for i, key in enumerate(new)})
        if new:
            self.mean = np.r_[self.mean, np.zeros(len(new))]
            self.covariance = np.pad(self.covariance, ((0, len(new)), (0, len(new))))
            self.covariance[start:, start:] = np.eye(len(new)) * self.player_sd**2

    def actual_weights(self, fixture, team):
        rows = self.observations[fixture.match_id, team]
        total = sum(float(row["minutes"]) for row in rows)
        if not total:
            return {}
        return {
            player_identity(row): float(row["minutes"]) / total
            for row in rows
            if float(row["minutes"]) > 0
        }

    def _augment_design(self, design, match):
        for team, sign in ((match.fixture.home_team_id, 1), (match.fixture.away_team_id, -1)):
            for identity, weight in self.actual_weights(match.fixture, team).items():
                design[:, self.player_index[identity]] += np.array([sign, -sign]) * weight

    def transition(self, years, dimensions):
        count = len(self.player_index)
        decay, variance = super().transition(years, dimensions - count)
        return np.r_[decay, np.ones(count)], np.r_[variance, np.zeros(count)]

    def fit(self, matches, as_of):
        result = super().fit(matches, as_of)
        self.fit_diagnostics.update(
            {
                "player_quality": "joint club/player covariance; scalar minutes-share effects",
                "player_prior": {
                    "mean": 0,
                    "population_sd": self.player_sd,
                    "scale_policy": "fixed strongly pooled population hierarchy",
                },
                "players": len(self.player_index),
                "future_states": "calendar-time club states and fixture lineup draws",
                "lineup_draws": self.lineup_draws,
                "historical_limitation": "retrospective minutes; publication times unknown",
            }
        )
        return result

    def kickoff(self, fixture):
        return self.kickoffs.get(
            fixture.match_id, datetime.combine(fixture.match_date, time(15), UTC)
        )

    def squad(self, fixture, team):
        if team in self.squads:
            squad = self.squads[team]
            if squad.season_id != fixture.season_id:
                raise ValueError("Snapshot squad season does not match fixture")
            return squad
        return self.player_history.retrospective_squad(
            team, fixture.season_id, datetime.combine(self.as_of, time(), UTC)
        )

    def lineup_weights(self, fixture, team, rng, size, oracle=False):
        if oracle:
            return {
                key: np.full(size, value)
                for key, value in self.actual_weights(fixture, team).items()
            }
        draws = sample_lineups(self.squad(fixture, team), self.kickoff(fixture), rng, size)
        return {
            p.player_id: draws.minutes[:, i] / 990
            for i, p in enumerate(draws.candidates)
            if draws.minutes[:, i].any()
        }

    def player_design(self, fixture, rng, size, oracle=False):
        design, unknown = np.zeros((size, len(self.mean))), {}
        for team, sign in ((fixture.home_team_id, 1), (fixture.away_team_id, -1)):
            for identity, weights in self.lineup_weights(fixture, team, rng, size, oracle).items():
                if identity in self.player_index:
                    design[:, self.player_index[identity]] += sign * weights
                else:
                    unknown[identity] = unknown.get(identity, 0) + sign * weights
        return design, unknown

    def score_distribution(self, fixture, oracle=False):
        self.validate_fixture(fixture)
        snapshot = deepcopy(self)
        for team in (fixture.home_team_id, fixture.away_team_id):
            snapshot._ensure_team(team, fixture.season_id, self.as_of)
        snapshot._advance(fixture.match_date)
        player, unknown = snapshot.player_design(
            fixture, np.random.default_rng(self.seed), self.lineup_draws, oracle
        )
        club = np.zeros((2, len(snapshot.mean)))
        club[:, :2] = [[1, 1], [1, 0]]
        for team, transform in zip(
            (fixture.home_team_id, fixture.away_team_id), self._team_transforms(), strict=True
        ):
            index = 2 + 2 * snapshot.team_index[team]
            club[:, index : index + 2] = transform
        unknown_variance = sum(
            (w**2 * self.player_sd**2 for w in unknown.values()), np.zeros(self.lineup_draws)
        )
        scores = []
        direction = np.array([1, -1])
        for weights, variance in zip(player, unknown_variance, strict=True):
            design = club + direction[:, None] * weights
            mean = design @ snapshot.mean
            covariance = design @ snapshot.covariance @ design.T
            covariance += variance * np.outer(direction, direction)
            scores.append(
                PoissonMixture(mean, covariance, self.quadrature_order)
                if self.dispersion is None
                else GammaPoissonMixture(mean, covariance, self.quadrature_order, self.dispersion)
            )
        return ScoreMixture(scores, np.full(len(scores), 1 / len(scores)))

    def player_quality_difference(self, fixture, values, rng, unknown):
        design, missing = self.player_design(fixture, rng, len(values))
        difference = np.einsum("ij,ij->i", design, values)
        for identity, weight in missing.items():
            if identity not in unknown:
                unknown[identity] = rng.normal(0, self.player_sd, len(values))
            difference += weight * unknown[identity]
        return difference

    def lineup_summary(self, fixture):
        result = []
        for team in (fixture.home_team_id, fixture.away_team_id):
            weights = self.lineup_weights(
                fixture, team, np.random.default_rng(self.seed), self.lineup_draws
            )
            contributions = np.zeros(self.lineup_draws)
            players = []
            for identity, w in weights.items():
                index = self.player_index.get(identity)
                mean = float(self.mean[index]) if index is not None else 0.0
                sd = (
                    float(np.sqrt(self.covariance[index, index]))
                    if index is not None
                    else self.player_sd
                )
                contributions += w * mean
                players.append(
                    {
                        "player_id": identity,
                        "expected_minutes": float(w.mean() * 990),
                        "quality": mean,
                        "quality_sd": sd,
                        "expected_quality_contribution": float(w.mean() * mean),
                    }
                )
            state = self.team_state(team, fixture.season_id)
            result.append(
                {
                    "team_id": team,
                    "club_quality": float(state.mean[0]),
                    "expected_player_quality": float(contributions.mean()),
                    "lineup_selection_quality_sd": float(contributions.std()),
                    "players": players,
                }
            )
        return result
