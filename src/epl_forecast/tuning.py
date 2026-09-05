from collections import defaultdict

from epl_forecast.evaluation import metrics


def select_by_prior_seasons(
    predictions: list[dict], first_test_season: str
) -> tuple[list[dict], list[dict]]:
    groups = defaultdict(lambda: defaultdict(list))
    for row in predictions:
        groups[row["season_id"]][row["model_id"]].append(row)
    model_ids = sorted({row["model_id"] for row in predictions})
    history = {model: [] for model in model_ids}
    selection, selected = [], []
    for season, candidates in sorted(groups.items()):
        if set(candidates) != set(model_ids):
            raise ValueError("Every tuning candidate must cover the same seasons")
        expected = {row["match_id"] for row in candidates[model_ids[0]]}
        outcomes = {row["match_id"]: row["outcome"] for row in candidates[model_ids[0]]}
        for rows in candidates.values():
            if len(rows) != len(expected) or {row["match_id"] for row in rows} != expected:
                raise ValueError("Tuning candidates must cover identical, distinct matches")
            if any(row["outcome"] != outcomes[row["match_id"]] for row in rows):
                raise ValueError("Tuning candidates disagree on observed outcomes")
        if season >= first_test_season:
            if not all(history.values()):
                raise ValueError("Selection requires at least one earlier season of predictions")
            prior_losses = {model: metrics(rows)[0]["log_loss"] for model, rows in history.items()}
            chosen = min(model_ids, key=lambda model: (prior_losses[model], model))
            score, _ = metrics(candidates[chosen])
            selection.append(
                {
                    "season_id": season,
                    "selected_model_id": chosen,
                    "selection_matches": len(history[chosen]),
                    "selection_through_season": max(row["season_id"] for row in history[chosen]),
                    "prior_log_loss": prior_losses[chosen],
                    **score,
                }
            )
            selected.extend(
                {**row, "model_id": "M2-prior-season-selection", "selected_model_id": chosen}
                for row in candidates[chosen]
            )
        for model, rows in candidates.items():
            history[model].extend(rows)
    if not selected:
        raise ValueError("No seasons available for chronological selection")
    return selection, selected
