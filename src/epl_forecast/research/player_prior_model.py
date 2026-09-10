"""Joint club, feature-mapping and persistent-player inference for prior research."""

from copy import deepcopy

import numpy as np

from epl_forecast.models.gaussian import score_laplace_update
from epl_forecast.models.player_quality import BayesianPlayerQuality, PlayerQualityFilter
from epl_forecast.models.poisson import PoissonMixture
from epl_forecast.models.quality_tilt import BayesianQualityTilt, QualityTiltFilter
from epl_forecast.models.quality_tilt_scores import ScoreMixture
from epl_forecast.squads import ROLES


class TimeVaryingPlayerFilter(PlayerQualityFilter):
    def __init__(
        self,
        prior_features,
        include_rating=False,
        use_features=True,
        residual_sd=0.35,
        shared_mapping_sd=0.12,
        role_mapping_sd=0.08,
        **kwargs,
    ):
        self.prior_features = prior_features
        self.include_rating, self.use_features = include_rating, use_features
        self.shared_mapping_sd, self.role_mapping_sd = shared_mapping_sd, role_mapping_sd
        if any(not np.isfinite(sd) or sd <= 0 for sd in (shared_mapping_sd, role_mapping_sd)):
            raise ValueError("Mapping prior scales must be finite and positive")
        self.feature_names = prior_features.names(include_rating)
        self.mapping_dimensions = len(ROLES) * len(self.feature_names) if use_features else 0
        super().__init__(prior_features.history, player_sd=residual_sd, **kwargs)
        if self.dispersion is not None:
            raise ValueError("The bounded player-prior candidate uses independent Poisson")

    def __deepcopy__(self, memo):
        instance = object.__new__(type(self))
        memo[id(self)] = instance
        shared = {"prior_features", "player_history", "observations", "_history", "_seasons"}
        instance.__dict__ = {
            key: value if key in shared else deepcopy(value, memo)
            for key, value in self.__dict__.items()
        }
        return instance

    @property
    def mapping_slice(self):
        start = 2 + 2 * len(self.team_index)
        return slice(start, start + self.mapping_dimensions)

    def _reset(self):
        super()._reset()
        count = self.mapping_dimensions
        self.mean = np.r_[self.mean, np.zeros(count)]
        self.covariance = np.pad(self.covariance, ((0, count), (0, count)))
        if count:
            hierarchy = np.full((len(ROLES), len(ROLES)), self.shared_mapping_sd**2)
            hierarchy += np.eye(len(ROLES)) * self.role_mapping_sd**2
            self.covariance[2:, 2:] = np.kron(hierarchy, np.eye(len(self.feature_names)))
        self._innovation_weights = []

    def _ensure_team(self, team, season, day, competition=None):
        old_count = len(self.team_index)
        QualityTiltFilter._ensure_team(self, team, season, day, competition)
        if len(self.team_index) != old_count:
            boundary = 2 + 2 * old_count
            order = np.r_[
                np.arange(boundary),
                len(self.mean) - 2,
                len(self.mean) - 1,
                np.arange(boundary, len(self.mean) - 2),
            ]
            self.mean = self.mean[order]
            self.covariance = self.covariance[np.ix_(order, order)]
            self.player_index = {pid: index + 2 for pid, index in self.player_index.items()}

    def transition(self, years, dimensions):
        static = len(self.player_index) + self.mapping_dimensions
        decay, variance = QualityTiltFilter.transition(self, years, dimensions - static)
        return np.r_[decay, np.ones(static)], np.r_[variance, np.zeros(static)]

    def _prepare_observations(self, games):
        identities = set()
        for match in games:
            f = match.fixture
            for team in (f.home_team_id, f.away_team_id):
                identities.update(self.actual_weights(f, team))
                identities.update(self.prior_features.reference_weights(team, f.match_date))
        new = sorted(identities - self.player_index.keys())
        start = len(self.mean)
        self.player_index.update({pid: start + i for i, pid in enumerate(new)})
        self.mean = np.r_[self.mean, np.zeros(len(new))]
        self.covariance = np.pad(self.covariance, ((0, len(new)), (0, len(new))))
        if new:
            self.covariance[start:, start:] = np.eye(len(new)) * self.player_sd**2
        self._innovation_weights = []

    def features(self, pid, fixture, cutoff):
        return self.prior_features.for_player(
            pid, cutoff, fixture.competition_id, fixture.season_id, self.include_rating
        )

    def _centered_weights(self, fixture, cutoff, rng=None, size=1, oracle=False):
        weights = {}
        for team, sign in ((fixture.home_team_id, 1), (fixture.away_team_id, -1)):
            reference = self.prior_features.reference_weights(team, cutoff)
            if not reference:
                continue
            actual = (
                self.actual_weights(fixture, team)
                if rng is None
                else self.lineup_weights(fixture, team, rng, size, oracle)
            )
            if rng is None and not actual:
                continue
            for pid in sorted(actual.keys() | reference.keys()):
                change = np.broadcast_to(actual.get(pid, 0), (size,)) - reference.get(pid, 0)
                weights[pid] = weights.get(pid, np.zeros(size)) + sign * change
        return {pid: w for pid, w in weights.items() if np.any(np.abs(w) > 1e-14)}

    def _design(self, fixture, cutoff, weights, size):
        design = np.zeros((size, len(self.mean)))
        unknown, innovations = {}, {}
        for pid, weight in weights.items():
            features = self.features(pid, fixture, cutoff)
            if self.use_features:
                design[:, self.mapping_slice] += weight[:, None] * self.prior_features.design(
                    features
                )
            if pid in self.player_index:
                design[:, self.player_index[pid]] += weight
            else:
                unknown[pid] = weight
            innovations[pid] = weight * features.local_sd
        return design, unknown, innovations

    def _augment_design(self, design, match):
        f = match.fixture
        weights = self._centered_weights(f, f.match_date)
        player, unknown, innovations = self._design(f, f.match_date, weights, 1)
        if unknown:
            raise ValueError("Training player residuals were not initialized")
        design += np.array([[1], [-1]]) * player[0]
        self._innovation_weights.append({pid: float(w[0]) for pid, w in innovations.items()})

    def _update(self, design, goals):
        identities = sorted({pid for weights in self._innovation_weights for pid in weights})
        weights = np.array(
            [[w.get(pid, 0) for pid in identities] for w in self._innovation_weights]
        )
        local_covariance = weights @ weights.T
        eigenvalues, vectors = np.linalg.eigh(local_covariance)
        active = eigenvalues > 1e-12
        root = vectors[:, active] * np.sqrt(eigenvalues[active])
        count, old = root.shape[1], len(self.mean)
        mean = np.r_[self.mean, np.zeros(count)]
        covariance = np.pad(self.covariance, ((0, count), (0, count)))
        if count:
            covariance[old:, old:] = np.eye(count)
        local_design = np.repeat(root, 2, axis=0) * np.tile([1, -1], len(root))[:, None]
        mean, covariance, evidence = score_laplace_update(
            mean, covariance, np.column_stack([design, local_design]), goals, None
        )
        # Marginalize fixture-local uncertainty; only mapping and player residuals persist.
        self.mean, self.covariance = mean[:old], covariance[:old, :old]
        self.log_evidence += evidence

    def fit(self, matches, as_of):
        super().fit(matches, as_of)
        self.fit_diagnostics.update(
            {
                "player_prior": "role-specific time-local features + persistent residual + marginalized local uncertainty",
                "centering": "actual or sampled lineup minus prior five-match exposure reference",
                "mapping_features": list(self.feature_names) if self.use_features else [],
                "rating_ablation": self.include_rating,
                "residual_sd": self.player_sd,
                "shared_mapping_sd": self.shared_mapping_sd,
                "role_mapping_sd": self.role_mapping_sd,
                "scope": "research match evaluation only; no operational or season-path integration",
            }
        )
        return self

    def player_design(self, fixture, rng, size, oracle=False):
        weights = self._centered_weights(fixture, self.as_of, rng, size, oracle)
        return self._design(fixture, self.as_of, weights, size)

    def score_distribution(self, fixture, oracle=False):
        self.validate_fixture(fixture)
        snapshot = deepcopy(self)
        for team in (fixture.home_team_id, fixture.away_team_id):
            snapshot._ensure_team(team, fixture.season_id, self.as_of, fixture.competition_id)
        snapshot._advance(fixture.match_date)
        player, unknown, innovations = snapshot.player_design(
            fixture, np.random.default_rng(self.seed), self.lineup_draws, oracle
        )
        club = np.zeros((2, len(snapshot.mean)))
        club[:, :2] = [[1, 1], [1, 0]]
        for team, transform in zip(
            (fixture.home_team_id, fixture.away_team_id), self._team_transforms(), strict=True
        ):
            start = 2 + 2 * snapshot.team_index[team]
            club[:, start : start + 2] = transform
        variance = sum(
            (w**2 * self.player_sd**2 for w in unknown.values()), np.zeros(self.lineup_draws)
        )
        variance += sum((w**2 for w in innovations.values()), np.zeros(self.lineup_draws))
        active = np.flatnonzero(np.any(club != 0, axis=0) | np.any(player != 0, axis=0))
        mean, covariance = snapshot.mean[active], snapshot.covariance[np.ix_(active, active)]
        direction, scores = np.array([1, -1]), []
        for row, extra in zip(player[:, active], variance, strict=True):
            design = club[:, active] + direction[:, None] * row
            scores.append(
                PoissonMixture(
                    design @ mean,
                    design @ covariance @ design.T + extra * np.outer(direction, direction),
                    self.quadrature_order,
                )
            )
        return ScoreMixture(scores, np.full(len(scores), 1 / len(scores)))

    def player_prior(self, pid, fixture):
        features = self.features(pid, fixture, self.as_of)
        design = np.zeros(len(self.mean))
        if self.use_features:
            design[self.mapping_slice] = self.prior_features.design(features)
        feature_mean = float(design @ self.mean)
        index = self.player_index.get(pid)
        if index is not None:
            design[index] = 1
        residual_mean = float(self.mean[index]) if index is not None else 0.0
        active = np.flatnonzero(design)
        variance = (
            float(design[active] @ self.covariance[np.ix_(active, active)] @ design[active])
            + features.local_sd**2
        )
        if index is None:
            variance += self.player_sd**2
        return {
            "player_id": pid,
            "cutoff": str(self.as_of),
            "role": features.role,
            "effective_minutes": features.effective_minutes,
            "days_since_meaningful_minutes": features.days_since_meaningful_minutes,
            "latest_evidence_date": str(features.latest_evidence_date)
            if features.latest_evidence_date
            else None,
            "components": {
                "quality": {
                    "mean": feature_mean + residual_mean,
                    "sd": float(np.sqrt(variance)),
                    "feature_mean": feature_mean,
                    "residual_mean": residual_mean,
                    "local_sd": features.local_sd,
                }
            },
        }

    def lineup_summary(self, fixture):
        result = []
        for team in (fixture.home_team_id, fixture.away_team_id):
            expected = self.lineup_weights(
                fixture, team, np.random.default_rng(self.seed), self.lineup_draws
            )
            reference = self.prior_features.reference_weights(team, self.as_of)
            players = []
            for pid in sorted(expected.keys() | reference.keys()):
                prior = self.player_prior(pid, fixture)
                weight = float(np.mean(expected.get(pid, 0)))
                ref = reference.get(pid, 0)
                players.append(
                    {
                        **prior,
                        "expected_minutes": weight * 990,
                        "reference_minutes": ref * 990,
                        "centered_contribution": (weight - ref)
                        * prior["components"]["quality"]["mean"]
                        if reference
                        else 0.0,
                    }
                )
            result.append(
                {
                    "team_id": team,
                    "reference_available": bool(reference),
                    "players": players,
                    "expected_adjustment": sum(p["centered_contribution"] for p in players),
                }
            )
        return result

    def sample_forecast_state(self, rng, size=1):
        raise NotImplementedError(
            "Player-prior prototype supports chronological match evaluation only"
        )


class TimeVaryingPlayerPrior(BayesianPlayerQuality):
    def __init__(self, prior_features, **kwargs):
        BayesianQualityTilt.__init__(self, independent_poisson=True)
        self.members = [
            TimeVaryingPlayerFilter(prior_features, **{**spec, "dispersion": None}, **kwargs)
            for spec in self.specifications
        ]

    def player_prior(self, pid, fixture):
        rows = [m.player_prior(pid, fixture) for m in self.members]
        moments = [r["components"]["quality"] for r in rows]
        means = np.array([m["mean"] for m in moments])
        mean = float(self.weights @ means)
        variance = float(
            self.weights @ np.array([m["sd"] ** 2 for m in moments])
            + self.weights @ (means - mean) ** 2
        )
        quality = {
            "mean": mean,
            "sd": float(np.sqrt(variance)),
            **{
                key: float(self.weights @ [m[key] for m in moments])
                for key in ("feature_mean", "residual_mean", "local_sd")
            },
        }
        return {**rows[0], "components": {"quality": quality}}

    def lineup_summary(self, fixture):
        summaries = [m.lineup_summary(fixture) for m in self.members]
        result = []
        for side in range(2):
            first = summaries[0][side]
            players = []
            for p in first["players"]:
                prior = self.player_prior(p["player_id"], fixture)
                players.append(
                    {
                        **p,
                        **prior,
                        "centered_contribution": (p["expected_minutes"] - p["reference_minutes"])
                        / 990
                        * prior["components"]["quality"]["mean"]
                        if first["reference_available"]
                        else 0.0,
                    }
                )
            result.append(
                {
                    **first,
                    "players": players,
                    "expected_adjustment": float(
                        self.weights @ [s[side]["expected_adjustment"] for s in summaries]
                    ),
                }
            )
        return result

    def sample_forecast_state(self, rng, size=1):
        raise NotImplementedError(
            "Player-prior prototype supports chronological match evaluation only"
        )
