import pytest

from epl_forecast.research.scoreboard import build_scoreboard


def row(model, match, season, outcome, probability, score=None):
    other = (1 - probability) / 2
    values = {"H": (probability, other, other), "D": (other, probability, other)}[outcome]
    return {
        "model_id": model,
        "match_id": match,
        "season_id": season,
        "outcome": outcome,
        "p_home": values[0],
        "p_draw": values[1],
        "p_away": values[2],
        "score_log_probability": score,
    }


def test_scoreboard_uses_exact_common_population_and_scales_improvement():
    predictions = []
    markets = []
    for match, season, outcome in [("a", "2024-2025", "H"), ("b", "2025-2026", "D")]:
        predictions.extend(
            [
                row("M2", match, season, outcome, 0.5, -2),
                row("candidate", match, season, outcome, 0.6, -1.8),
            ]
        )
        markets.extend(
            [
                row("pre", match, season, outcome, 0.7),
                row("close", match, season, outcome, 0.8),
            ]
        )
    predictions.append(row("candidate", "candidate-only", "2025-2026", "H", 0.9))
    result = build_scoreboard(
        predictions, markets, ["M2", "candidate"], "M2", "pre", "close", ["M2", "candidate"]
    )
    assert len(result["matched_fixture_ids"]) == 2
    assert result["best_retained_structural_model"] == "candidate"
    comparison = result["comparisons"][1]
    assert comparison["candidate_minus_m2_log_loss"] == pytest.approx(-0.1823215568)
    assert comparison["fraction_m2_to_preclosing_market_gap_closed"] == pytest.approx(
        0.1823215568 / 0.3364722366
    )
    assert comparison["geometric_realized_probability_change_vs_m2"] == pytest.approx(0.2)
    assert len(result["by_season"]) == 8


def test_scoreboard_rejects_missing_or_noncompetitive_markets():
    predictions = [row("M2", "a", "2024-2025", "H", 0.6)]
    markets = [row("pre", "a", "2024-2025", "H", 0.5)]
    with pytest.raises(ValueError, match="missing"):
        build_scoreboard(predictions, markets, ["M2"], "M2", "pre", "close", ["M2"])
