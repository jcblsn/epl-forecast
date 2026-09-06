"""Retrospective player observations; archive collection times are not match times."""

import csv
import io
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from epl_forecast.schema import fixture_id

OBSERVATIONS = (
    "minutes",
    "starts",
    "goals_scored",
    "assists",
    "goals_conceded",
    "clean_sheets",
    "saves",
    "own_goals",
    "penalties_missed",
    "penalties_saved",
    "yellow_cards",
    "red_cards",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "expected_goals_conceded",
    "clearances_blocks_interceptions",
    "recoveries",
    "tackles",
    "defensive_contribution",
    "attempted_passes",
    "completed_passes",
    "key_passes",
    "big_chances_created",
    "big_chances_missed",
)


def read_player_csv(path: Path) -> tuple[list[dict], str]:
    payload = path.read_bytes()
    encoding = "utf-8-sig"
    try:
        text = payload.decode(encoding)
    except UnicodeDecodeError:
        encoding = "latin-1"
        text = payload.decode(encoding)
    return list(csv.DictReader(io.StringIO(text))), encoding


def normalize_player_matches(
    season: str,
    rows: list[dict],
    players: list[dict],
    team_ids: dict[str, str],
    source_sha256: str,
    fixtures: list[dict] | None = None,
) -> tuple[list[dict], dict]:
    season_id = f"{int(season[:4])}-{int(season[:4]) + 1}"
    metadata = {row["id"]: row for row in players}
    if len(metadata) != len(players):
        raise ValueError("Duplicate season player IDs")
    fixture_map = {row["id"]: row for row in fixtures or []}
    opponents = defaultdict(set)
    for row in rows:
        opponents[row["fixture"], row["was_home"]].add(row["opponent_team"])
    if any(len(values) != 1 for values in opponents.values()):
        raise ValueError("Ambiguous fixture-side club mapping")
    accepted, counts = {}, Counter()
    clubs = defaultdict(set)
    for number, row in enumerate(rows, 2):
        player = metadata.get(row["element"], {})
        if player.get("element_type") == "5" or row.get("position") == "AM":
            counts["manager_rows_excluded"] += 1
            continue
        if row.get("team_h_score", "") == "" or row.get("team_a_score", "") == "":
            counts["unplayed_rows_excluded"] += 1
            continue
        home = row["was_home"]
        if home not in {"True", "False"}:
            raise ValueError("Invalid home flag")
        other_side = "False" if home == "True" else "True"
        side = opponents.get((row["fixture"], other_side))
        if not side:
            raise ValueError("Cannot reconstruct club from opposite fixture side")
        club = next(iter(side))
        kickoff = datetime.fromisoformat(row["kickoff_time"])
        if kickoff.tzinfo is None:
            raise ValueError("Player kickoff must include timezone")
        kickoff = kickoff.astimezone(UTC)
        fixture = fixture_map.get(row["fixture"])
        if fixture:
            expected_club = fixture["team_h" if home == "True" else "team_a"]
            expected_opponent = fixture["team_a" if home == "True" else "team_h"]
            if (club, row["opponent_team"]) != (expected_club, expected_opponent):
                raise ValueError("Club reconstruction disagrees with fixture archive")
        minutes = int(row["minutes"])
        if not 0 <= minutes <= 120:
            raise ValueError("Invalid minutes")
        starts = row.get("starts", "")
        if starts not in {"", "0", "1"}:
            raise ValueError("Invalid starts")
        normalized = {
            "season_id": season_id,
            "source_season_id": season,
            "player_season_id": f"{season_id}:{row['element']}",
            "fpl_element_id": row["element"],
            "fpl_player_code": player.get("code", ""),
            "player_name": row["name"],
            "fpl_fixture_id": row["fixture"],
            "kickoff_time": kickoff.isoformat(),
            "team_id": team_ids[club],
            "opponent_team_id": team_ids[row["opponent_team"]],
            "match_id": fixture_id(
                "eng-premier-league",
                season_id,
                team_ids[club if home == "True" else row["opponent_team"]],
                team_ids[row["opponent_team"] if home == "True" else club],
            ),
            "was_home": home,
            "source_sha256": source_sha256,
            "source_row": number,
            "historical_observed_at": "",
            **{field: row.get(field, "") for field in OBSERVATIONS},
        }
        key = (row["element"], row["fixture"])
        if key in accepted:
            old = accepted[key]
            if any(old[k] != v for k, v in normalized.items() if k != "source_row"):
                raise ValueError(f"Conflicting completed player-match rows: {season} {key}")
            counts["identical_duplicates_excluded"] += 1
            continue
        accepted[key] = normalized
        clubs[row["element"]].add(club)
        counts["missing_player_metadata"] += not bool(player)
        counts["final_club_disagrees_with_fixture"] += bool(player) and player.get("team") != club
    output = sorted(
        accepted.values(),
        key=lambda row: (row["kickoff_time"], row["player_season_id"], int(row["fpl_fixture_id"])),
    )
    by_fixture = defaultdict(list)
    for row in output:
        by_fixture[row["fpl_fixture_id"]].append(row)
    xg_fields = [field for field in OBSERVATIONS if field.startswith("expected_")]
    for group in by_fixture.values():
        if all(row["starts"] == "0" for row in group) and any(
            int(row["minutes"]) > 0 for row in group
        ):
            counts["fixtures_with_placeholder_starts"] += 1
            mask_xg = all(
                row[field] in {"", "0", "0.00", "0.00000"} for row in group for field in xg_fields
            )
            for row in group:
                row["starts"] = ""
                if mask_xg:
                    for field in xg_fields:
                        row[field] = ""
            counts["fixtures_with_placeholder_xg"] += mask_xg
    histories = defaultdict(list)
    for row in output:
        history = histories[row["player_season_id"]]
        eligible = [r for r in history if r["kickoff_time"][:10] < row["kickoff_time"][:10]]
        prior = eligible[-5:]
        row["prior_observed_fixtures"] = len(eligible)
        row["prior5_count"] = len(prior)
        row["expected_minutes_prior5"] = (
            round(sum(int(r["minutes"]) for r in prior) / len(prior), 4) if prior else ""
        )
        row["prior5_latest_kickoff"] = prior[-1]["kickoff_time"] if prior else ""
        history.append(row)
    counts.update(
        {
            "source_rows": len(rows),
            "normalized_rows": len(output),
            "players": len(clubs),
            "fixtures": len({r["fpl_fixture_id"] for r in output}),
            "players_observed_at_multiple_clubs": sum(len(v) > 1 for v in clubs.values()),
            "rows_with_starts": sum(r["starts"] != "" for r in output),
            "rows_with_xg": sum(r["expected_goals"] != "" for r in output),
        }
    )
    coverage = {
        field: {
            "nonempty": sum(r[field] != "" for r in output),
            "nonzero": sum(r[field] != "" and float(r[field]) != 0 for r in output),
        }
        for field in OBSERVATIONS
    }
    starters = defaultdict(int)
    for row in output:
        if row["starts"] != "":
            starters[row["fpl_fixture_id"], row["team_id"]] += int(row["starts"])
    return output, {
        "season_id": season,
        **dict(counts),
        "fixture_sides_with_starts": len(starters),
        "fixture_sides_with_eleven_starters": sum(v == 11 for v in starters.values()),
        "field_coverage": coverage,
    }
