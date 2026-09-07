"""Score forecasts integrating M8 process variation and joint state uncertainty."""

import numpy as np

from epl_forecast.models.poisson import PoissonMixture
from epl_forecast.models.process_observation import ProcessObservation


def process_goal_probabilities(rates, scale, maximum):
    rates = np.asarray(rates)
    probabilities = np.zeros((len(rates), maximum + 1))
    intensity = rates / (1 + scale)
    probabilities[:, 0] = np.exp(-intensity)
    jump = np.arange(1, maximum + 1) * (scale / (1 + scale)) ** np.arange(maximum)
    jump /= 1 + scale
    for n in range(1, maximum + 1):
        probabilities[:, n] = intensity / n * (probabilities[:, :n] @ jump[n - 1 :: -1])
    return probabilities


class ProcessScoreMixture(PoissonMixture):
    def __init__(self, log_mean, log_covariance, order=9, process_scale=0.25):
        super().__init__(log_mean, log_covariance, order)
        ProcessObservation([], [], process_scale)
        self.process_scale = process_scale

    def marginals(self, maximum):
        if type(maximum) is not int or maximum < 0:
            raise ValueError("max_goals must be a nonnegative integer")
        return tuple(
            process_goal_probabilities(rates, self.process_scale, maximum)
            for rates in (self.home_rates, self.away_rates)
        )

    def grid(self, max_goals=10):
        home, away = self.marginals(max_goals)
        grid = (home.T * self.weights) @ away
        return grid, max(0.0, 1.0 - float(grid.sum()))

    def outcome_probabilities(self):
        maximum = 16
        while True:
            home, away = self.marginals(maximum)
            retained = self.weights @ (home.sum(axis=1) * away.sum(axis=1))
            if 1 - retained < 1e-10:
                break
            if maximum >= 4096:
                raise RuntimeError("Process score tail failed to converge")
            maximum *= 2
        cumulative_home, cumulative_away = home.cumsum(axis=1), away.cumsum(axis=1)
        win = self.weights @ np.sum(home[:, 1:] * cumulative_away[:, :-1], axis=1)
        draw = self.weights @ np.sum(home * away, axis=1)
        loss = self.weights @ np.sum(away[:, 1:] * cumulative_home[:, :-1], axis=1)
        return tuple(np.array([win, draw, loss]) / retained)

    def log_probability(self, home_goals, away_goals):
        from scipy.special import logsumexp

        likelihood = ProcessObservation(
            [home_goals, away_goals], [np.nan, np.nan], self.process_scale
        )
        values = [
            likelihood(np.log([h, a]))[0]
            for h, a in zip(self.home_rates, self.away_rates, strict=True)
        ]
        return float(logsumexp(np.log(self.weights) + values))

    def sample(self, rng, size):
        component = rng.choice(len(self.weights), size=size, p=self.weights)
        rates = np.column_stack([self.home_rates[component], self.away_rates[component]])
        goals, _ = ProcessObservation([], [], self.process_scale).sample(np.log(rates), rng)
        return goals[:, 0], goals[:, 1]

    def diagnostics(self):
        home, away = self.marginals(5)
        total_below_six = np.array(
            [sum(home[:, h] * away[:, a] for h in range(6) for a in range(6 - h))]
        ).ravel()
        both_zero = home[:, 0] * away[:, 0]
        return {
            "p_total_goals_ge6": float(self.weights @ (1 - total_below_six)),
            "p_scoreless": float(self.weights @ both_zero),
            "p_both_score": float(self.weights @ (1 - home[:, 0] - away[:, 0] + both_zero)),
            "expected_home_goals": self.home_rate,
            "expected_away_goals": self.away_rate,
        }
