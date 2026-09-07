from datetime import date

import numpy as np

from epl_forecast.research.process_bridge import shot_prior


def test_future_bridge_targets_do_not_change_prior():
    rows = []
    for year in range(2015, 2025):
        row = {"season_id": f"{year}-{year + 1}", "available_on": f"{year + 1}-06-01"}
        for dimension in ("attack", "defense"):
            row.update(
                {
                    f"championship_{dimension}": 0.2,
                    f"championship_{dimension}_variance": 0.02,
                    f"entry_{dimension}": -0.3,
                    f"entry_{dimension}_variance": 0.02,
                }
            )
        rows.append(row)
    source = {"mean": np.array([0.15, 0.1]), "variance": np.array([0.01, 0.02])}
    cutoff, season = date(2023, 8, 1), "2023-2024"
    left, count, _ = shot_prior(rows, source, cutoff, season)
    for row in rows[-2:]:
        row["entry_attack"] = 20
    right, _, _ = shot_prior(rows, source, cutoff, season)
    assert count == 8
    np.testing.assert_array_equal(left.mean, right.mean)
    np.testing.assert_array_equal(left.covariance, right.covariance)
    assert np.diag(left.covariance).min() >= 0.25**2
