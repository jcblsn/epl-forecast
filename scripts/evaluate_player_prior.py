"""Matched chronological API-only player-prior, centering and rating experiments."""

import argparse
from collections import defaultdict
from datetime import date
from itertools import groupby
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import new_run_directory, write_csv
from epl_forecast.evaluation import metrics
from epl_forecast.models.player_quality import BayesianPlayerQuality
from epl_forecast.models.quality_tilt import BayesianQualityTilt
from epl_forecast.research.player_prior import load_prior_inputs
from epl_forecast.research.player_prior_model import TimeVaryingPlayerPrior
from epl_forecast.storage import file_hash, write_json

SLICES = (
    "opening_weeks",
    "transfers_newcomers",
    "promoted_clubs",
    "major_lineup_change",
    "returning_players",
    "goalkeeper_change",
    "little_history",
)


def labels(source, model, fixture, prior_matches):
    tags = set()
    previous_season = f"{int(fixture.season_id[:4]) - 1}-{int(fixture.season_id[:4])}"
    previous_pl = {
        team
        for m in prior_matches
        if m.fixture.season_id == previous_season
        and m.fixture.competition_id == fixture.competition_id
        for team in (m.fixture.home_team_id, m.fixture.away_team_id)
    }
    for team in (fixture.home_team_id, fixture.away_team_id):
        previous = [
            m for m in prior_matches if team in (m.fixture.home_team_id, m.fixture.away_team_id)
        ]
        if sum(m.fixture.season_id == fixture.season_id for m in previous) < 5:
            tags.add("opening_weeks")
        if previous_pl and team not in previous_pl:
            tags.add("promoted_clubs")
        actual = model.observations[fixture.match_id, team]
        past = model.observations[previous[-1].fixture.match_id, team] if previous else []
        starters = {r["player_id"] for r in actual if r["starts"] == 1}
        old_starters = {r["player_id"] for r in past if r["starts"] == 1}
        if len(starters) == len(old_starters) == 11 and len(old_starters - starters) >= 4:
            tags.add("major_lineup_change")
        if any(
            r["position"] == "GK" and r["starts"] == 1 and r["player_id"] not in starters
            for r in past
        ):
            tags.add("goalkeeper_change")
        for row in actual:
            if float(row["minutes"]) < 45:
                continue
            f = source.for_player(
                row["player_id"], fixture.match_date, fixture.competition_id, fixture.season_id
            )
            history = [
                r
                for r in source.history.by_player[row["player_id"]]
                if r["match_id"] in set(f.evidence_matches)
            ]
            if not history or history[-1]["team_id"] != team:
                tags.add("transfers_newcomers")
            if f.effective_minutes < 450:
                tags.add("little_history")
            if f.days_since_meaningful_minutes is not None and (
                f.days_since_meaningful_minutes >= 60
                or (len(history) >= 3 and all(float(r["minutes"]) == 0 for r in history[-2:]))
            ):
                tags.add("returning_players")
    return "|".join(sorted(tags))


def summarize(records, output):
    regimes = sorted({r["regime"] for r in records})
    reference = {r["match_id"]: r for r in records if r["regime"] == "team_parent"}
    summary, calibration = [], []
    for regime in regimes:
        for tag in ("all", *SLICES):
            rows = [
                r
                for r in records
                if r["regime"] == regime and (tag == "all" or tag in r["slices"].split("|"))
            ]
            if rows:
                scores, bins = metrics(rows)
                changes = np.array(
                    [
                        [r[k] - reference[r["match_id"]][k] for k in ("p_home", "p_draw", "p_away")]
                        for r in rows
                    ]
                )
                scores.update(
                    mean_absolute_probability_change=float(np.abs(changes).mean()),
                    max_absolute_probability_change=float(np.abs(changes).max()),
                )
                calibration.extend({"regime": regime, "slice": tag, **b} for b in bins)
            else:
                scores = {
                    key: None
                    for key in (
                        "log_loss",
                        "brier",
                        "classwise_ece",
                        "score_nll",
                        "mean_absolute_probability_change",
                        "max_absolute_probability_change",
                    )
                }
                scores.update(matches=0, score_matches=0)
            summary.append({"regime": regime, "slice": tag, **scores})
    write_csv(output / "summary.csv", list(summary[0]), summary)
    write_csv(output / "calibration.csv", list(calibration[0]), calibration)
    by_regime = {
        regime: {r["match_id"]: r for r in records if r["regime"] == regime} for regime in regimes
    }
    paired = []
    for candidate, parent in (
        ("prior_deployable", "team_parent"),
        ("prior_oracle", "team_parent"),
        ("prior_deployable", "legacy_deployable"),
        ("prior_oracle", "legacy_oracle"),
        ("prior_deployable", "centered_control_deployable"),
        ("prior_oracle", "centered_control_oracle"),
        ("prior_oracle", "prior_deployable"),
        ("rating_deployable", "prior_deployable"),
        ("rating_oracle", "prior_oracle"),
    ):
        for tag in ("all", *SLICES):
            rows = [
                r
                for r in by_regime[candidate].values()
                if tag == "all" or tag in r["slices"].split("|")
            ]
            if not rows:
                continue
            for metric in ("outcome_log_loss", "score_nll"):
                days = defaultdict(list)
                for row in rows:
                    days[row["match_date"]].append(
                        row[metric] - by_regime[parent][row["match_id"]][metric]
                    )
                sums = np.array([sum(v) for _, v in sorted(days.items())])
                counts = np.array([len(v) for _, v in sorted(days.items())])
                indices = np.random.default_rng(910).integers(len(days), size=(2000, len(days)))
                samples = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
                paired.append(
                    {
                        "candidate": candidate,
                        "parent": parent,
                        "slice": tag,
                        "metric": metric,
                        "matches": len(rows),
                        "difference": float(sums.sum() / counts.sum()),
                        "day_bootstrap_q025": float(np.quantile(samples, 0.025)),
                        "day_bootstrap_q975": float(np.quantile(samples, 0.975)),
                    }
                )
    write_csv(output / "paired_comparisons.csv", list(paired[0]), paired)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-start", type=date.fromisoformat, default=date(2023, 7, 1))
    parser.add_argument("--season", default="2024-2025")
    parser.add_argument("--draws", type=int, default=32)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    new_run_directory(args.output)
    matches, source, manifest = load_prior_inputs(args.inputs)
    matches = sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id))
    targets = [
        m
        for m in matches
        if m.fixture.season_id == args.season and m.fixture.competition_id == "eng-premier-league"
    ]
    if args.limit:
        targets = targets[: args.limit]
    if not targets:
        raise ValueError("No target fixtures")
    models = {
        "team_parent": BayesianQualityTilt(independent_poisson=True),
        "legacy": BayesianPlayerQuality(source.history, lineup_draws=args.draws),
        "centered_control": TimeVaryingPlayerPrior(
            source, lineup_draws=args.draws, use_features=False
        ),
        "prior": TimeVaryingPlayerPrior(source, lineup_draws=args.draws),
        "rating": TimeVaryingPlayerPrior(source, lineup_draws=args.draws, include_rating=True),
    }
    run = {
        "status": "running",
        "arguments": {
            k: str(v) if isinstance(v, (Path, date)) else v for k, v in vars(args).items()
        },
        "input_manifest_sha256": file_hash(args.inputs / "input_manifest.json"),
        "input_batches": len(manifest["manifests"]),
        "features": vars(source.config),
        "target_matches": [m.fixture.match_id for m in targets],
        "source_policy": "API-FOOTBALL only, including all parent training scores; no odds, predictions or other providers",
        "cutoff_policy": "Each fit and feature pool excludes same London date; target minutes only enter labeled oracle distributions and retrospective slices",
        "matched_control": "Same centered player model and evidence-dependent local variance with feature mapping disabled",
        "scope": "Four original independent-Poisson M5 dynamics specifications; expanding match history from train-start",
        "historical_limitations": [
            "Retrospective observations do not establish historical publication times",
            "Candidate membership uses prior appearances and 0.7 previous-season carry-forward; no backdated current squad, injury or transfer captures",
            "Player birthdays use only profiles labeled to completed prior seasons; original publication timing is unknown",
            "Sparse event rates are conditional on provider observation, with explicit coverage and exposure; null never means zero",
            "Shared scalar player Quality still affects both goal rates oppositely; this prototype does not validate that representation",
            "Local uncertainty law is fixed research regularization, not a calibrated player measurement-error model",
        ],
        "slice_policy": "Overlapping retrospective participation diagnostics, not cutoff-known transfer or injury news",
    }
    write_json(args.output / "run.json", run)
    records, player_rows = [], []
    for day, games in groupby(targets, key=lambda m: m.fixture.match_date):
        training = [
            m for m in matches if args.train_start <= m.fixture.match_date and m.available_on <= day
        ]
        for name, model in models.items():
            model.fit(training, day)
            print(f"Fitted {name} through {day}", flush=True)
        for match in games:
            f = match.fixture
            primary = models["prior"].members[0]
            for team in (f.home_team_id, f.away_team_id):
                actual = primary.observations[f.match_id, team]
                if (
                    sum(r["starts"] == 1 for r in actual) != 11
                    or not 850 <= sum(float(r["minutes"]) for r in actual) <= 1100
                ):
                    raise ValueError(f"Incomplete target minute evidence: {f.match_id} {team}")
            distributions = {"team_parent": models["team_parent"].predict_match(f).scores}
            for name, model in models.items():
                if name != "team_parent":
                    distributions[f"{name}_deployable"] = model.predict_match(f).scores
                    distributions[f"{name}_oracle"] = model.oracle_distribution(f)
            tags = labels(source, primary, f, [m for m in matches if m.available_on <= day])
            for regime, scores in distributions.items():
                probabilities = scores.outcome_probabilities()
                score_log = float(scores.log_probability(match.home_goals, match.away_goals))
                records.append(
                    {
                        "match_id": f.match_id,
                        "match_date": str(day),
                        "season_id": f.season_id,
                        "regime": regime,
                        "deployable": not regime.endswith("oracle"),
                        "p_home": float(probabilities[0]),
                        "p_draw": float(probabilities[1]),
                        "p_away": float(probabilities[2]),
                        "outcome": match.outcome,
                        "home_goals": match.home_goals,
                        "away_goals": match.away_goals,
                        "outcome_log_loss": float(
                            -np.log(probabilities["HDA".index(match.outcome)])
                        ),
                        "score_nll": -score_log,
                        "score_log_probability": score_log,
                        "slices": tags,
                    }
                )
            rng = np.random.default_rng(primary.seed)
            for team in (f.home_team_id, f.away_team_id):
                expected = primary.lineup_weights(f, team, rng, args.draws)
                reference = source.reference_weights(team, day)
                actual = primary.actual_weights(f, team)
                for pid in sorted(expected.keys() | reference.keys() | actual.keys()):
                    prior = models["prior"].player_prior(pid, f)
                    quality = prior["components"]["quality"]
                    control = models["centered_control"].player_prior(pid, f)["components"][
                        "quality"
                    ]
                    rating = models["rating"].player_prior(pid, f)["components"]["quality"]
                    legacy = float(
                        models["legacy"].weights
                        @ [
                            m.mean[m.player_index[pid]] if pid in m.player_index else 0
                            for m in models["legacy"].members
                        ]
                    )
                    player_rows.append(
                        {
                            "match_id": f.match_id,
                            "cutoff": str(day),
                            "team_id": team,
                            "player_id": pid,
                            "role": prior["role"],
                            "expected_minutes": float(np.mean(expected.get(pid, 0)) * 990),
                            "reference_minutes": reference.get(pid, 0) * 990,
                            "oracle_minutes_share": actual.get(pid, 0),
                            "mean": quality["mean"],
                            "sd": quality["sd"],
                            "feature_mean": quality["feature_mean"],
                            "residual_mean": quality["residual_mean"],
                            "local_sd": quality["local_sd"],
                            "centered_control_mean": control["mean"],
                            "legacy_mean": legacy,
                            "rating_mean": rating["mean"],
                            "change_from_control": quality["mean"] - control["mean"],
                            "change_from_legacy": quality["mean"] - legacy,
                            "effective_minutes": prior["effective_minutes"],
                            "days_since_meaningful_minutes": prior["days_since_meaningful_minutes"],
                            "latest_evidence_date": prior["latest_evidence_date"],
                        }
                    )
        write_csv(args.output / "predictions.csv", list(records[0]), records)
        write_csv(args.output / "player_priors.csv", list(player_rows[0]), player_rows)
        write_json(
            args.output / "progress.json",
            {"through": str(day), "fixtures": len(records) // 9, "target_fixtures": len(targets)},
        )
        print(
            f"Evaluated {len(records) // 9}/{len(targets)} matched fixtures through {day}",
            flush=True,
        )
    summarize(records, args.output)
    run.update(
        status="complete",
        evaluated_matches=len(records) // 9,
        fits={name: model.fit_diagnostics for name, model in models.items()},
    )
    run["artifacts"] = {
        name: file_hash(args.output / name)
        for name in (
            "predictions.csv",
            "player_priors.csv",
            "summary.csv",
            "calibration.csv",
            "paired_comparisons.csv",
        )
    }
    write_json(args.output / "run.json", run)


if __name__ == "__main__":
    main()
