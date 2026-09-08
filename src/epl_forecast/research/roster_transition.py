"""Conservative offseason departure exposure, not a reconstructed historical squad."""

from collections import defaultdict
from datetime import datetime


def departure_status(team, transfers, season_end, cutoff):
    events = defaultdict(set)
    for row in transfers:
        day = row["transfer_date"]
        if day is None:
            return None, "undated transfer"
        if season_end < day < cutoff:
            events[day].add((row["from_team_id"], row["to_team_id"]))
    current = team
    for _, moves in sorted(events.items()):
        if len(moves) != 1:
            return None, "ambiguous same-day transfer order"
        origin, destination = next(iter(moves))
        if origin is None or destination is None:
            return None, "unknown transfer endpoint"
        if origin != current:
            return None, "transfer chain disagrees with last observed club"
        current = destination
    return current != team, None


def departure_exposure(team, minutes, transfers, captured, season_end, cutoff):
    if cutoff <= season_end:
        raise ValueError("Entry cutoff must follow previous season")
    total = sum(minutes.values())
    if total <= 0 or any(value < 0 for value in minutes.values()):
        raise ValueError("Prior-season exposure must be positive and nonnegative")
    departed, unknown, records = 0, 0, []
    for player, exposure in sorted(minutes.items()):
        if exposure == 0:
            continue
        history = transfers.get(player, [])
        if player not in captured:
            status, reason = None, "no retained transfer-history response"
        else:
            status, reason = departure_status(team, history, season_end, cutoff)
        if status is None:
            unknown += exposure
        elif status:
            departed += exposure
        records.append(
            {
                "player_id": player,
                "prior_minutes": exposure,
                "departed": status,
                "unknown_reason": reason,
            }
        )
    return {
        "team_id": team,
        "season_end": str(season_end),
        "cutoff": str(cutoff),
        "prior_minutes": total,
        "departure_minutes_share": departed / total if unknown == 0 else None,
        "departure_share_bounds": [departed / total, (departed + unknown) / total],
        "unknown_minutes_share": unknown / total,
        "players": records,
        "definition": "Prior-season minutes lost through a coherent retained transfer chain after season end and strictly before the opener. No recorded transfer is not proof of squad retention. Arrivals, released players missing provider events, and composition quality are not measured.",
        "information_basis": "Retrospective transfer event dates; not a strict historical replay or proof of publication before kickoff.",
    }


def captured_transfer_players(manifests, players, observed_before=None):
    api_to_player = {p["api_id"]: p["player_id"] for p in players if p["api_id"] is not None}
    result = set()
    for manifest in manifests:
        request = manifest["request"]
        context = request["context"]
        if context.get("endpoint") != "transfers" or "player" not in context:
            continue
        if (
            observed_before is not None
            and datetime.fromisoformat(request["retrieved_at"]) > observed_before
        ):
            continue
        player = api_to_player.get(int(context["player"]))
        if player is not None:
            result.add(player)
    return result
