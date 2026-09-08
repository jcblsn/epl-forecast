"""FPL's narrow prospective availability signal; never historical squads or statistics."""

import json

from epl_forecast.data.api_football import team_registry
from epl_forecast.data.understat_ingest import name_tokens
from epl_forecast.datasets import Dataset, publish

URL = "https://fantasy.premierleague.com/api/bootstrap-static/"


def ingest(root, record, payload):
    b = json.loads(payload)
    aliases = team_registry()
    aliases.update(
        {
            "Spurs": "tottenham-hotspur",
            "Man Utd": "manchester-united",
            "Man City": "manchester-city",
            "Nott'm Forest": "nottingham-forest",
        }
    )
    teams = {t["id"]: aliases[t["name"]] for t in b["teams"]}
    current = next((e["id"] for e in b["events"] if e["is_current"]), None)
    upcoming = next((e["id"] for e in b["events"] if e["is_next"]), None)
    data = Dataset(root)
    try:
        players = data.rows("SELECT * FROM players")
        known = {p["fpl_code"]: p["player_id"] for p in players if p["fpl_code"]}
        rows, mappings = [], []
        for p in b["elements"]:
            if p["element_type"] not in (1, 2, 3, 4):
                continue
            code = str(p["code"])
            pid = known.get(code)
            full = name_tokens(p["first_name"] + " " + p["second_name"])
            candidates = {
                r["player_id"]
                for r in players
                if r["name"]
                and name_tokens(r["name"]) == full
                and r["birth_date"] is not None
                and str(r["birth_date"]) == p.get("birth_date")
            }
            if len(candidates) == 1:
                candidate = next(iter(candidates))
                if pid and candidate != pid:
                    raise ValueError(f"Conflicting FPL code mapping: {code}")
                pid = candidate
            if pid:
                mappings.append({"player_id": pid, "fpl_code": code, "name": p["web_name"]})
            rows.append(
                {
                    "player_id": pid,
                    "fpl_code": code,
                    "team_id": teams[p["team"]],
                    "competition_id": "eng-premier-league",
                    "season_id": record["context"]["season_id"],
                    "scope": "fpl_round",
                    "status": p["status"],
                    "reason": p["news"],
                    "chance_this_round": p.get("chance_of_playing_this_round"),
                    "chance_next_round": p.get("chance_of_playing_next_round"),
                    "current_round": current,
                    "next_round": upcoming,
                    "news_added": p.get("news_added"),
                }
            )
        return publish(root, record, {"availability": rows, "players": mappings})
    finally:
        data.close()
