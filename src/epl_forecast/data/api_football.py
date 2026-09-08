"""API-Football v3 ingestion for English league research."""

import csv
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from epl_forecast.data.capture import SourceAccessError
from epl_forecast.datasets import publish
from epl_forecast.schema import fixture_id

BASE = "https://v3.football.api-sports.io/"
LEAGUES = {39: "eng-premier-league", 40: "eng-championship"}
ROLES = {
    "G": "GK",
    "D": "DEF",
    "M": "MID",
    "F": "FWD",
    "Goalkeeper": "GK",
    "Defender": "DEF",
    "Midfielder": "MID",
    "Attacker": "FWD",
}


def player_id(value):
    return f"p{int(value)}" if value is not None else None


def request(fetcher, endpoint, params=None, **kwargs):
    url = BASE + endpoint + ("?" + urlencode(sorted((params or {}).items())) if params else "")
    record, payload = fetcher.get(
        "api_football", url, context={"endpoint": endpoint, **(params or {})}, **kwargs
    )
    return record, json.loads(payload)


def preflight(fetcher):
    record, body = request(fetcher, "status")
    status = body["response"]
    result = {
        "subscription": status["subscription"],
        "requests": status["requests"],
        "retrieved_at": record["retrieved_at"],
    }
    if not status["subscription"]["active"] or status["requests"]["limit_day"] < 7500:
        raise SourceAccessError("API-Football Pro is required for historical backfill")
    fetcher.remaining = status["requests"]["limit_day"] - status["requests"]["current"]
    return result


def team_registry():
    with Path(__file__).with_name("teams.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    aliases = {r["source_name"]: r["team_id"] for r in rows}
    aliases.update({r["team_name"]: r["team_id"] for r in rows})
    aliases.update(
        {
            "Manchester United": "manchester-united",
            "Manchester City": "manchester-city",
            "Newcastle": "newcastle-united",
            "Wolves": "wolverhampton-wanderers",
            "Tottenham": "tottenham-hotspur",
            "West Brom": "west-bromwich-albion",
            "QPR": "queens-park-rangers",
            "Sheffield Utd": "sheffield-united",
            "Leeds": "leeds-united",
            "Leicester": "leicester-city",
            "Norwich": "norwich-city",
            "Swansea": "swansea-city",
            "Cardiff": "cardiff-city",
            "Hull City": "hull-city",
            "Birmingham": "birmingham-city",
            "Stoke City": "stoke-city",
            "Huddersfield": "huddersfield-town",
            "Bolton": "bolton-wanderers",
            "Blackburn": "blackburn-rovers",
            "Nottingham Forest": "nottingham-forest",
            "Brighton": "brighton-hove-albion",
            "West Ham": "west-ham-united",
            "Wigan": "wigan-athletic",
            "Ipswich": "ipswich-town",
            "Derby": "derby-county",
            "Preston": "preston-north-end",
            "Luton": "luton-town",
            "Milton Keynes Dons": "milton-keynes-dons",
            "Peterborough": "peterborough-united",
            "Charlton": "charlton-athletic",
            "Rotherham": "rotherham-united",
            "Wycombe": "wycombe-wanderers",
        }
    )
    return aliases


def team_key(team, required=False):
    if team.get("id") is None:
        return None
    found = team_registry().get(team["name"])
    if found:
        return found
    if required:
        raise ValueError(f"Unmapped league team: {team['id']} {team['name']}")
    return f"af-team-{team['id']}"


def normalize(record, body, root):
    endpoint, context = record["context"]["endpoint"], record["context"]
    tables = {}

    def add(table, row):
        tables.setdefault(table, []).append(row)

    for item in body["response"]:
        if endpoint == "leagues":
            league = item["league"]["id"]
            for s in item["seasons"]:
                add(
                    "competition_seasons",
                    {
                        "competition_id": LEAGUES[league],
                        "season_id": f"{s['year']}-{s['year'] + 1}",
                        "expected_matches": 380 if league == 39 else 552,
                        "coverage": json.dumps(s["coverage"], sort_keys=True),
                    },
                )
        elif endpoint == "teams":
            t = item["team"]
            add("teams", {"team_id": team_key(t, True), "api_id": t["id"], "name": t["name"]})
        elif endpoint == "fixtures":
            league = item["league"]
            if league["id"] not in LEAGUES:
                continue
            season = f"{league['season']}-{league['season'] + 1}"
            comp = LEAGUES[league["id"]]
            stage = "regular" if league["round"].startswith("Regular Season") else "playoff"
            h, a = (team_key(item["teams"][s], True) for s in ("home", "away"))
            f = item["fixture"]
            key = (
                fixture_id(comp, season, h, a)
                if stage == "regular"
                else f"{comp}:{season}:playoff:{f['id']}"
            )
            status = f["status"]["short"]
            finished = status in ("FT", "AET", "PEN", "AWD", "WO")
            state = (
                "finished"
                if finished
                else "in_progress"
                if status in ("1H", "HT", "2H", "ET", "BT", "P", "INT", "SUSP", "LIVE")
                else "postponed"
                if status in ("PST", "CANC", "ABD")
                else "scheduled"
            )
            kickoff = f["date"]
            add(
                "fixtures",
                {
                    "match_id": key,
                    "competition_id": comp,
                    "season_id": season,
                    "stage": stage,
                    "home_team_id": h,
                    "away_team_id": a,
                    "api_id": f["id"],
                    "match_date": str(
                        datetime.fromisoformat(kickoff).astimezone(ZoneInfo("Europe/London")).date()
                    ),
                    "kickoff_time": kickoff,
                    "status": state,
                    "home_goals": item["goals"]["home"] if finished else None,
                    "away_goals": item["goals"]["away"] if finished else None,
                },
            )
            base = {
                "match_id": key,
                "competition_id": comp,
                "season_id": season,
                "kickoff_time": kickoff,
            }
            lineup = {}
            for side in item.get("lineups", []):
                team = team_key(side["team"], True)
                for collection, starts in [("startXI", 1), ("substitutes", 0)]:
                    for p in side[collection]:
                        p = p["player"]
                        if p["id"] is None:
                            continue
                        pid = player_id(p["id"])
                        lineup[pid] = {
                            **base,
                            "team_id": team,
                            "player_id": pid,
                            "position": ROLES.get(p.get("pos"), "UNK"),
                            "starts": starts,
                        }
                        add("players", {"player_id": pid, "api_id": p["id"], "name": p["name"]})
            for side in item.get("players", []):
                team = team_key(side["team"], True)
                for entry in side["players"]:
                    p, s = entry["player"], entry["statistics"][0]
                    if p["id"] is None:
                        continue
                    pid = player_id(p["id"])
                    row = lineup.setdefault(
                        pid,
                        {
                            **base,
                            "team_id": team,
                            "player_id": pid,
                            "position": ROLES.get(s["games"]["position"], "UNK"),
                        },
                    )
                    if finished:
                        row.update(
                            {
                                "minutes": s["games"]["minutes"],
                                "goals": s["goals"]["total"],
                                "assists": s["goals"]["assists"],
                                "saves": s["goals"]["saves"],
                                "shots": s["shots"]["total"],
                                "shots_on_target": s["shots"]["on"],
                                "yellow_cards": s["cards"]["yellow"],
                                "red_cards": s["cards"]["red"],
                            }
                        )
                    add("players", {"player_id": pid, "api_id": p["id"], "name": p["name"]})
            for row in lineup.values():
                add("appearances", row)
        elif endpoint == "players":
            p = item["player"]
            pid = player_id(p["id"])
            add(
                "players",
                {
                    "player_id": pid,
                    "api_id": p["id"],
                    "name": p["name"],
                    "birth_date": p.get("birth", {}).get("date"),
                },
            )
            for s in item["statistics"]:
                if (
                    s["league"]["id"] != context["league"]
                    or s["league"]["season"] != context["season"]
                ):
                    continue
                add(
                    "memberships",
                    {
                        "player_id": pid,
                        "team_id": team_key(s["team"], True),
                        "season_id": f"{context['season']}-{context['season'] + 1}",
                        "competition_id": LEAGUES[context["league"]],
                        "position": ROLES.get(s["games"]["position"], "UNK"),
                        "basis": "retrospective_season_participation",
                        "scope": str(context["league"]),
                    },
                )
        elif endpoint == "players/squads":
            for p in item["players"]:
                pid = player_id(p["id"])
                add("players", {"player_id": pid, "api_id": p["id"], "name": p["name"]})
                add(
                    "memberships",
                    {
                        "player_id": pid,
                        "team_id": team_key(item["team"], True),
                        "season_id": record["context"]["season_id"],
                        "competition_id": record["context"]["competition_id"],
                        "position": ROLES.get(p["position"], "UNK"),
                        "basis": "captured_squad",
                        "scope": str(item["team"]["id"]),
                    },
                )
        elif endpoint == "injuries":
            comp = LEAGUES[item["league"]["id"]]
            p, f = item["player"], item["fixture"]
            add(
                "availability",
                {
                    "player_id": player_id(p["id"]),
                    "team_id": team_key(item["team"], True),
                    "competition_id": comp,
                    "season_id": f"{item['league']['season']}-{item['league']['season'] + 1}",
                    "scope": f"fixture:{f['id']}",
                    "status": p["type"],
                    "reason": p["reason"],
                },
            )
        elif endpoint == "sidelined":
            add(
                "availability",
                {
                    "player_id": player_id(context["player"]),
                    "scope": "interval",
                    "status": "sidelined",
                    "reason": item["type"],
                    "start_date": item.get("start"),
                    "end_date": item.get("end") if item.get("end") not in ("Unknown", "") else None,
                },
            )
        elif endpoint == "transfers":
            for t in item["transfers"]:
                add(
                    "transfers",
                    {
                        "player_id": player_id(item["player"]["id"]),
                        "transfer_date": t["date"],
                        "from_team_id": team_key(t["teams"]["out"]),
                        "to_team_id": team_key(t["teams"]["in"]),
                        "transfer_type": t["type"],
                    },
                )
    for table, rows in tables.items():
        if table == "players":
            merged = {}
            for r in rows:
                merged.setdefault(r["player_id"], {}).update(r)
            tables[table] = list(merged.values())
        else:
            tables[table] = list({json.dumps(r, sort_keys=True): r for r in rows}.values())
    return publish(root, record, tables)
