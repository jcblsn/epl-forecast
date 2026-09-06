from datetime import date, timedelta

from epl_forecast.schema import Match


def training_matches(matches: list[Match], config: dict, spec: dict, as_of: date) -> list[Match]:
    """Select information once for CLI and evaluation; zero window means expanding history."""
    days = spec.get("train_window_days", config["train_window_days"])
    if type(days) is not int or days < 0:
        raise ValueError("Training window must be nonnegative integer days")
    earliest = as_of - timedelta(days=days) if days else date.min
    competitions = spec.get("train_competitions", [config["competition_id"]])
    if not competitions or config["competition_id"] not in competitions:
        raise ValueError("Training competitions must include the forecast competition")
    training = sorted(
        (
            m
            for m in matches
            if m.fixture.competition_id in competitions
            and earliest <= m.fixture.match_date
            and m.available_on <= as_of
        ),
        key=lambda m: (m.fixture.match_date, m.fixture.match_id),
    )
    primary = sum(m.fixture.competition_id == config["competition_id"] for m in training)
    if primary < config["min_train_matches"]:
        raise ValueError(f"Only {primary} training matches in forecast competition before {as_of}")
    return training
