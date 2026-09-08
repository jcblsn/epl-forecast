"""Understat league and player process observations, reconciled to canonical fixtures."""

import gzip
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from epl_forecast.data.api_football import team_registry
from epl_forecast.datasets import Dataset, publish
from epl_forecast.schema import fixture_id


def name_tokens(value):
    return " ".join(
        re.findall(
            "[a-z]+",
            unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode(),
        )
    )


def ingest(root, record, payload):
    body = json.loads(gzip.decompress(payload) if payload.startswith(b"\x1f\x8b") else payload)
    context = record["context"]
    data = Dataset(root)
    try:
        fixtures = {r["match_id"]: r for r in data.fixtures()}
        if context["kind"] == "league":
            year = context["season_start"]
            season, comp = f"{year}-{year + 1}", "eng-premier-league"
            aliases = team_registry()
            aliases.update(
                {
                    "Newcastle United": "newcastle-united",
                    "West Bromwich Albion": "west-bromwich-albion",
                }
            )
            corrections = {
                r["source_match_id"]: r
                for r in json.loads(
                    Path(__file__).with_name("understat_date_corrections.json").read_text()
                )
            }
            rows = []
            for r in body["dates"]:
                if not r.get("isResult"):
                    continue
                h, a = (aliases[r[side]["title"]] for side in ("h", "a"))
                key = fixture_id(comp, season, h, a)
                f = fixtures.get(key)
                if f is None:
                    raise ValueError(f"Understat fixture not in canonical schedule: {key}")
                if datetime.fromisoformat(r["datetime"]).date() != f["match_date"]:
                    correction = corrections.get(str(r["id"]), {})
                    if (
                        correction.get("match_id") != key
                        or correction.get("source_datetime") != r["datetime"]
                        or correction.get("canonical_date") != str(f["match_date"])
                    ):
                        raise ValueError(f"Understat date contradiction: {key}")
                if (int(r["goals"]["h"]), int(r["goals"]["a"])) != (
                    f["home_goals"],
                    f["away_goals"],
                ):
                    raise ValueError(f"Understat score contradiction: {key}")
                for side, team in [("h", h), ("a", a)]:
                    xg = float(r["xG"][side])
                    if not 0 <= xg < float("inf"):
                        raise ValueError("Invalid Understat xG")
                    rows.append(
                        {
                            "match_id": key,
                            "team_id": team,
                            "competition_id": comp,
                            "season_id": season,
                            "xg": xg,
                            "source_match_id": str(r["id"]),
                        }
                    )
            return publish(root, record, {"team_process": rows})
        key = context["match_id"]
        f = fixtures[key]
        known = {
            r["understat_id"]: r["player_id"]
            for r in data.rows("SELECT * FROM players WHERE understat_id IS NOT NULL")
        }
        appearances = data.rows(
            "SELECT a.*, p.name FROM appearances a JOIN players p USING(player_id) "
            "WHERE a.match_id=?",
            [key],
        )
        rows, identities = [], []
        for side, team in [("h", f["home_team_id"]), ("a", f["away_team_id"])]:
            for r in body["rosters"][side].values():
                uid = str(r["player_id"])
                candidates = {
                    p["player_id"]
                    for p in appearances
                    if p["team_id"] == team and name_tokens(p["name"]) == name_tokens(r["player"])
                }
                linked = known.get(uid)
                if len(candidates) == 1:
                    found = next(iter(candidates))
                    if linked and linked != found:
                        raise ValueError(f"Contradictory player mapping: Understat {uid}")
                    linked = found
                if linked:
                    identities.append(
                        {"player_id": linked, "understat_id": uid, "name": r["player"]}
                    )
                rows.append(
                    {
                        "match_id": key,
                        "team_id": team,
                        "competition_id": f["competition_id"],
                        "season_id": f["season_id"],
                        "player_id": linked,
                        "understat_id": uid,
                        "position": r["position"],
                        "minutes": int(r["time"]),
                        "xg": float(r["xG"]),
                        "xa": float(r["xA"]),
                        "shots": int(r["shots"]),
                    }
                )
        return publish(root, record, {"player_process": rows, "players": identities})
    finally:
        data.close()
