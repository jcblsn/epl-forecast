import math
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from epl_forecast.artifacts import new_run_directory, write_csv
from epl_forecast.live import LiveSeason, timestamp
from epl_forecast.market import market_assisted_probabilities
from epl_forecast.models.base import ForecastModel
from epl_forecast.schema import Match
from epl_forecast.simulation import EuropeScenario, simulate_season
from epl_forecast.storage import file_hash, write_json


def flatten_rows(rows):
    nested = {key for row in rows for key, value in row.items() if isinstance(value, (dict, list))}
    flat = [{key: value for key, value in row.items() if key not in nested} for row in rows]
    return flat, list(dict.fromkeys(key for row in flat for key in row))


def check_freshness(live: LiveSeason, max_age_hours: float) -> None:
    if not math.isfinite(max_age_hours) or max_age_hours <= 0:
        raise ValueError("Maximum snapshot age must be positive and finite")
    now = datetime.now(UTC)
    if live.observed_at > now:
        raise ValueError("Snapshot observation time is in the future")
    observed = timestamp(live.manifest["fixtures_retrieved_at"])
    age = (now - observed).total_seconds() / 3600
    if age > max_age_hours:
        raise ValueError(f"Fixture data is {age:.1f} hours old; collect fresh data")


def current_table(live: LiveSeason, adjustments: list[dict]) -> dict[str, dict]:
    table = {team: {"played": 0, "current_points": 0} for team in live.teams}
    for match in live.played:
        home, away = table[match.fixture.home_team_id], table[match.fixture.away_team_id]
        home["played"] += 1
        away["played"] += 1
        home["current_points"] += 3 if match.outcome == "H" else int(match.outcome == "D")
        away["current_points"] += 3 if match.outcome == "A" else int(match.outcome == "D")
    for adjustment in adjustments:
        table[adjustment["team_id"]]["current_points"] += adjustment["points"]
    return table


def render_forecast(forecast: dict) -> str:
    names = forecast["team_names"]
    simulation = forecast["simulation"]
    championship = forecast["competition_id"] == "eng-championship"
    uncertainty_note = (
        "These probabilities include uncertainty in current team strength and match randomness. "
        "Each simulated season holds its sampled strengths fixed; "
        "transfers and injuries are omitted."
        if forecast.get("state_uncertainty") == "posterior"
        else "Team strengths are held fixed; these probabilities include match randomness and omit "
        "uncertainty in team strength, transfers and injuries."
    )
    if forecast.get("future_state_evolution"):
        uncertainty_note = (
            "These probabilities include current Quality/Tilt uncertainty, uncertain dynamics, "
            "future changes in strength and match tempo. Transfers and injuries are omitted."
        )
    if forecast.get("fit_diagnostics", {}).get("player_quality"):
        uncertainty_note = (
            "These probabilities include joint club and player Quality uncertainty, future "
            "club strength changes, lineup selection and captured expiring availability. "
            "Future transfers and newly arising injuries are not modeled. Club/player "
            "contributions and lineup uncertainty are included in the full forecast JSON."
        )
    prior_note = (
        "Promoted clubs start from Championship-informed distributions. Strength uncertainty "
        "is available in the team strengths download."
        if forecast.get("state_uncertainty") == "posterior"
        else "Clubs without PL history start at 1."
    )
    table = ""
    if simulation:
        rows = []
        for team in sorted(simulation["teams"], key=lambda row: row["mean_position"]):
            cells = [
                escape(names[team["team_id"]]),
                str(team["played"]),
                str(team["current_points"]),
                f"{team['mean_position']:.1f}",
                f"{int(team['position_quantiles_05_50_95'][0])}–{int(team['position_quantiles_05_50_95'][2])}",
                f"{team['mean_points']:.1f}",
                f"{int(team['points_quantiles_05_50_95'][0])}–{int(team['points_quantiles_05_50_95'][2])}",
                f"{team['title_probability']:.1%}",
            ]
            if championship:
                cells.extend(
                    [
                        f"{team['automatic_promotion_probability']:.1%}",
                        f"{team['playoff_qualification_probability']:.1%}",
                        f"{team['promotion_probability']:.1%}",
                    ]
                )
            else:
                cells.extend(
                    [f"{team['top_four_probability']:.1%}", f"{team['top_five_probability']:.1%}"]
                )
            cells.append(f"{team['relegation_probability']:.1%}")
            rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
        event_headers = (
            "<th>Automatic promotion</th><th>Playoffs</th><th>Promotion</th>"
            if championship
            else "<th>Top four</th><th>Top five</th>"
        )
        table = (
            "<div class='scroll'><table><thead><tr><th>Team</th><th>Played</th>"
            "<th>Points now</th><th>Expected rank</th><th>90% rank interval</th>"
            "<th>Expected final points</th><th>90% points interval</th><th>Title</th>"
            + event_headers
            + "<th>Relegation</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )
    else:
        table = f"<p>{escape(forecast['simulation_unavailable_reason'])}</p>"
    matches = []
    for match in forecast["matches"]:
        if not match["next_match_for_teams"]:
            continue
        assisted = match["market_assisted_probabilities"]
        cells = [
            escape(match["kickoff_time"] or "To be scheduled"),
            escape(names[match["home_team_id"]]),
            escape(names[match["away_team_id"]]),
            f"{match['p_home']:.1%}",
            f"{match['p_draw']:.1%}",
            f"{match['p_away']:.1%}",
            "—" if assisted is None else f"{assisted['p_home']:.1%}",
            "—" if assisted is None else f"{assisted['p_draw']:.1%}",
            "—" if assisted is None else f"{assisted['p_away']:.1%}",
            f"{match['score_distribution']['home_rate']:.2f}",
            f"{match['score_distribution']['away_rate']:.2f}",
        ]
        matches.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    strengths = []
    for team in sorted(forecast["team_strengths"], key=lambda row: -row["attack_log_rate"]):
        strengths.append(
            f"<tr><td>{escape(names[team['team_id']])}</td>"
            f"<td>{team['attack_multiplier']:.2f}</td>"
            f"<td>{team['defense_multiplier']:.2f}</td>"
            f"<td>{team['training_matches']}</td></tr>"
        )
    quality_table = ""
    if forecast["team_strengths"] and "quality" in forecast["team_strengths"][0]:
        quality_rows = []
        for team in sorted(forecast["team_strengths"], key=lambda row: -row["quality"]):
            quality_rows.append(
                f"<tr><td>{escape(names[team['team_id']])}</td>"
                f"<td>{team['quality']:.3f}</td><td>{team['quality_sd']:.3f}</td>"
                f"<td>{team['tilt']:.3f}</td><td>{team['tilt_sd']:.3f}</td></tr>"
            )
        quality_table = (
            "<h2>Quality and Tilt</h2><p>Quality measures relative strength; positive Tilt "
            "raises both teams' expected goals. SD measures uncertainty "
            "in each log-rate rating.</p>"
            "<div class='scroll'><table><thead><tr><th>Team</th><th>Quality</th>"
            "<th>Quality SD</th><th>Tilt</th><th>Tilt SD</th></tr></thead><tbody>"
            + "".join(quality_rows)
            + "</tbody></table></div>"
        )
    europe = ""
    if simulation and simulation["europe_scenario"]:
        scenario = escape(simulation["europe_scenario"]["name"])
        europe_rows = []
        for team in sorted(simulation["teams"], key=lambda row: row["mean_position"]):
            probabilities = team["conditional_europe_probabilities"]
            europe_rows.append(
                f"<tr><td>{escape(names[team['team_id']])}</td>"
                + "".join(
                    f"<td>{probabilities[key]:.1%}</td>"
                    for key in ("champions_league", "europa_league", "conference_league")
                )
                + "</tr>"
            )
        europe = (
            f"<h2>Conditional European qualification</h2><p>{scenario}</p>"
            "<p>Assumes no additional English UEFA titleholders or eligibility exclusions.</p>"
            "<div class='scroll'><table><thead><tr><th>Team</th><th>Champions League</th>"
            "<th>Europa League</th><th>Conference League</th></tr></thead><tbody>"
            + "".join(europe_rows)
            + "</tbody></table></div>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(forecast["competition_name"])} {escape(forecast["season_id"])} forecast</title>
<style>
body {{font:16px/1.5 system-ui,sans-serif;max-width:1120px;margin:32px auto;padding:0 20px;
color:#17242c;background:#fafbf9}} h1,h2 {{line-height:1.2}} h2 {{margin-top:36px}}
p {{max-width:900px}} a {{color:#12654f}} .scroll {{overflow-x:auto}}
table {{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;background:white}}
th,td {{text-align:right;padding:9px 12px;border-bottom:1px solid #dce3dd;white-space:nowrap}}
th:first-child,td:first-child {{text-align:left}} th {{background:#edf3ee}}
.note {{color:#52616b;font-size:14px}} details {{margin-top:24px}}
</style></head><body>
<h1>{escape(forecast["competition_name"])} {escape(forecast["season_id"])}</h1>
<p>Probabilistic match forecasts and the expected final table.
Model: {escape(forecast["model"]["id"])}.</p>
<p class="note">Season state captured {escape(forecast["state_observed_at"])}.
Forecast generated {escape(forecast["generated_at"])}. Times are UTC.
Full-time scores include today's completed games; results use captured provider reports.
Team strengths use results before {escape(forecast["model_results_cutoff"])} (London date).</p>
<h2>Season forecast</h2>{table}
<p class="note">Top four and top five are league positions. European qualification also
depends on cup results and allocated places. {escape(uncertainty_note)}</p>
{europe}
<h2>Next match for each team</h2>
<div class="scroll"><table><thead><tr><th>Kickoff (UTC)</th><th>Home</th><th>Away</th>
<th>Structural H</th><th>Structural D</th><th>Structural A</th>
<th>Market-assisted H</th><th>Market-assisted D</th><th>Market-assisted A</th>
<th>Home goals</th><th>Away goals</th>
</tr></thead><tbody>{"".join(matches)}</tbody></table></div>
<p class="note">Market-assisted probabilities use the latest captured pre-closing prices
available at the forecast cutoff. A dash means no suitable quote was available. Goals and
exact-score matrices come from the structural model; season simulation does not use markets.
All remaining match probabilities and matrices, with omitted tail mass, are in the JSON download.</p>
{quality_table}
<details><summary>Current attack and defense strengths</summary>
<p class="note">Attack above 1 raises scoring rates; defense above 1 reduces the opponent's
rate. Both use the model's league reference. {escape(prior_note)}</p>
<div class="scroll"><table><thead><tr><th>Team</th><th>Attack</th><th>Defense</th>
<th>Training matches</th></tr></thead><tbody>{"".join(strengths)}</tbody></table></div></details>
<p><a href="forecast.json">Full forecast JSON</a> · <a href="matches.csv">Match CSV</a> ·
<a href="table.csv">Season CSV</a> · <a href="team_strengths.csv">Team strengths CSV</a></p>
<p class="note">Source data:
<a href="https://www.api-football.com/">API-Football</a> and
<a href="https://football-data.co.uk/">Football-Data</a>. Use and redistribution
are subject to each provider's terms.</p>
</body></html>
"""


def export_forecast(
    live: LiveSeason,
    model: ForecastModel,
    training: list[Match],
    run: dict,
    output: Path,
    simulations: int,
    seed: int,
    max_goals: int,
    adjustments: list[dict],
    europe: EuropeScenario | None = None,
    market_quotes: list[dict] | None = None,
    market_pool: dict | None = None,
) -> dict:
    new_run_directory(output)
    in_progress = [
        row["match_id"]
        for row in live.details.values()
        if row["status"] in {"in_progress", "awaiting_result"}
    ]
    unscheduled = [
        row["match_id"] for row in live.details.values() if row["status"] == "unscheduled"
    ]
    simulation = None
    if not in_progress and not unscheduled:
        simulation = simulate_season(
            model,
            live.played,
            live.remaining,
            list(live.teams),
            model.as_of,
            simulations,
            seed,
            adjustments,
            europe,
            results_observed_at=live.observed_at,
        )
        table = current_table(live, adjustments)
        for row in simulation["teams"]:
            row.update(table[row["team_id"]])
    matches = []
    market_quotes = market_quotes or []
    selected_quotes = {}
    if market_pool:
        for quote in market_quotes:
            if quote["family"] != market_pool["market_family"]:
                continue
            if quote["match_id"] in selected_quotes:
                raise ValueError(f"Duplicate current market quote: {quote['match_id']}")
            selected_quotes[quote["match_id"]] = quote
    for fixture in live.remaining:
        if fixture.match_id in in_progress:
            continue
        prediction = model.predict_match(fixture)
        grid, tail = prediction.scores.grid(max_goals)
        structural = {
            "p_home": float(prediction.probabilities[0]),
            "p_draw": float(prediction.probabilities[1]),
            "p_away": float(prediction.probabilities[2]),
        }
        assistance = (
            market_assisted_probabilities(
                prediction.probabilities, selected_quotes[fixture.match_id], market_pool
            )
            if fixture.match_id in selected_quotes
            else None
        )
        matches.append(
            {
                **live.details[fixture.match_id],
                "model_forecast_date": str(fixture.match_date),
                **structural,
                "structural_probabilities": structural,
                "market_assisted_probabilities": assistance,
                "market_assisted_p_home": None if assistance is None else assistance["p_home"],
                "market_assisted_p_draw": None if assistance is None else assistance["p_draw"],
                "market_assisted_p_away": None if assistance is None else assistance["p_away"],
                "primary_probability_source": "structural",
                "primary_p_home": structural["p_home"],
                "primary_p_draw": structural["p_draw"],
                "primary_p_away": structural["p_away"],
                **(
                    {"player_quality": model.lineup_summary(fixture)}
                    if hasattr(model, "lineup_summary")
                    else {}
                ),
                "score_distribution": {
                    "probability_source": "structural",
                    "home_rate": prediction.scores.home_rate,
                    "away_rate": prediction.scores.away_rate,
                    "grid_home_rows_away_columns": grid.tolist(),
                    "omitted_probability": tail,
                    **(
                        {"uncertainty_components": prediction.scores.uncertainty_components()}
                        if hasattr(prediction.scores, "uncertainty_components")
                        else {}
                    ),
                },
            }
        )
    matches.sort(key=lambda row: (row["kickoff_time"] or "9999", row["match_id"]))
    generated = datetime.now(UTC)
    seen = set()
    for row in matches:
        eligible = row["kickoff_time"] and timestamp(row["kickoff_time"]) > generated
        next_for = (
            [team for team in (row["home_team_id"], row["away_team_id"]) if team not in seen]
            if eligible
            else []
        )
        row["next_match_for_teams"] = next_for
        seen.update(next_for)
    strengths = []
    for team in live.teams:
        index = model.team_index.get(team)
        state = (
            model.team_summary(team, live.season_id)
            if hasattr(model, "team_summary")
            else {
                "team_id": team,
                "attack_log_rate": float(model.attack[index]) if index is not None else 0.0,
                "defense_log_rate": float(model.defense[index]) if index is not None else 0.0,
            }
        )
        attack, defense = state["attack_log_rate"], state["defense_log_rate"]
        strengths.append(
            {
                **state,
                "attack_multiplier": math.exp(attack),
                "defense_multiplier": math.exp(defense),
                "training_matches": sum(
                    team in (m.fixture.home_team_id, m.fixture.away_team_id) for m in training
                ),
            }
        )
    forecast = {
        "schema_version": 1,
        "season_id": live.season_id,
        "generated_at": generated.isoformat(),
        "state_observed_at": live.observed_at.isoformat(),
        "model_results_cutoff": str(model.as_of),
        "model": run["model"],
        "state_uncertainty": "posterior" if hasattr(model, "sample_forecast_state") else "fixed",
        "future_state_evolution": bool(getattr(model, "fit_diagnostics", {}).get("future_states")),
        "fit_diagnostics": getattr(model, "fit_diagnostics", {}),
        "training_matches": len(training),
        "training_date_max": str(max(m.fixture.match_date for m in training)),
        "league_away_goal_rate": math.exp(float(model.intercept)),
        "home_scoring_multiplier": math.exp(float(model.home_advantage)),
        "team_names": live.teams,
        "team_strengths": strengths,
        "matches": matches,
        "market_assistance": None
        if market_pool is None
        else {
            **market_pool,
            "available_match_forecasts": sum(
                row["market_assisted_probabilities"] is not None for row in matches
            ),
            "season_simulation_uses_market": False,
        },
        "simulation": simulation,
        "simulation_unavailable_reason": (
            "Season projection awaits full-time results for in-progress or overdue fixtures; "
            "this model does not forecast games in play."
            if in_progress
            else "Season projection awaits fixture dates required for future state evolution."
            if unscheduled
            else None
        ),
        "fixtures_awaiting_results": in_progress,
        "results_crosschecked": live.results_crosschecked,
        "competition_id": live.competition_id,
        "competition_name": "Championship"
        if live.competition_id == "eng-championship"
        else "Premier League",
        "sources": live.manifest["files"],
        "source_errors": live.manifest["errors"],
    }
    write_json(output / "forecast.json", forecast)
    write_json(output / "run.json", run)
    flat_matches, match_fields = flatten_rows(matches)
    for name, rows, fields in (
        ("team_strengths.csv", strengths, list(strengths[0])),
        ("fixtures.csv", list(live.details.values()), list(next(iter(live.details.values())))),
        (
            "matches.csv",
            flat_matches,
            match_fields if matches else ["match_id", "p_home", "p_draw", "p_away"],
        ),
        (
            "table.csv",
            [
                {
                    **{
                        key: value
                        for key, value in row.items()
                        if not isinstance(value, (dict, list))
                    },
                    **row.get("conditional_europe_probabilities", {}),
                }
                for row in sorted(simulation["teams"], key=lambda row: row["mean_position"])
            ]
            if simulation
            else [],
            [
                key
                for key, value in simulation["teams"][0].items()
                if not isinstance(value, (dict, list))
            ]
            + list(simulation["teams"][0].get("conditional_europe_probabilities", {}))
            if simulation
            else ["team_id", "mean_points"],
        ),
    ):
        write_csv(output / name, fields, rows)
    (output / "index.html").write_text(render_forecast(forecast))
    hashes = {path.name: file_hash(path) for path in sorted(output.iterdir()) if path.is_file()}
    archived = datetime.now(UTC)
    write_json(
        output / "archive.json",
        {
            "archived_at": archived.isoformat(),
            "files": hashes,
            "forward_match_ids": [
                row["match_id"]
                for row in matches
                if row["status"] == "scheduled"
                and row["kickoff_time"]
                and timestamp(row["kickoff_time"]) > archived
            ],
            "forward_policy": (
                "Archive completed before captured kickoff, with fixture unstarted in snapshot. "
                "Rescheduled fixtures must be checked against later snapshots when scoring."
            ),
        },
    )
    return forecast
