import json
from datetime import date
from pathlib import Path


def historical_adjustments(season: str, as_of: date) -> list[dict]:
    events = json.loads(Path(__file__).with_name("pl_adjustments.json").read_text())
    return [
        event
        for event in events
        if event["season_id"] == season and date.fromisoformat(event["known_on"]) <= as_of
    ]
