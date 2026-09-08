"""Small local collection loops shared by backfill and ongoing ingestion."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from epl_forecast.data import api_football as api
from epl_forecast.data import football_data, fpl, understat_ingest
from epl_forecast.data.capture import Fetcher, QuotaReached, SourceAccessError, writer_lock
from epl_forecast.data.sources import COMPETITIONS, season_name, source_url
from epl_forecast.datasets import Dataset
from epl_forecast.storage import sha256_bytes, write_json


def normalized_request(fetcher, endpoint, params=None, **kwargs):
    record, body = api.request(fetcher, endpoint, params, **kwargs)
    api.normalize(record, body, fetcher.root)
    return body


def backfill(root=Path("data"), start=2010, end=None, max_requests=None):
    now = datetime.now(UTC)
    end = end if end is not None else now.year - (now.month < 7)
    if start > end:
        raise ValueError("Backfill start must not exceed end")
    fetcher = Fetcher(root, reserve=1000)
    report = {"started_at": now.isoformat(), "start": start, "end": end, "status": "running"}
    initial = len(fetcher.records)

    def get(endpoint, params=None, **kwargs):
        if max_requests is not None and len(fetcher.records) - initial >= max_requests:
            raise QuotaReached("This backfill invocation reached its request budget; resume")
        return normalized_request(fetcher, endpoint, params, historical=True, **kwargs)

    try:
        report["subscription"] = api.preflight(fetcher)
        catalog = {
            league: get("leagues", {"id": league})["response"][0]["seasons"]
            for league in api.LEAGUES
        }
        for year in range(end, start - 1, -1):
            for league, comp in api.LEAGUES.items():
                seasons = {s["year"]: s for s in catalog[league]}
                if year not in seasons:
                    continue
                print(f"Backfill {comp} {year}: fixtures, players, injuries", flush=True)
                get("teams", {"league": league, "season": year})
                fixtures = get("fixtures", {"league": league, "season": year})["response"]
                ids = [
                    r["fixture"]["id"]
                    for r in fixtures
                    if r["fixture"]["status"]["short"] in ("FT", "AET", "PEN", "AWD", "WO")
                ]
                for index in range(0, len(ids), 20):
                    selected = ids[index : index + 20]
                    body = get("fixtures", {"ids": "-".join(map(str, selected))})
                    returned = {r["fixture"]["id"]: r for r in body["response"]}
                    for fid in selected:
                        r = returned.get(fid)
                        coverage = seasons[year]["coverage"]["fixtures"]
                        if (
                            r is None
                            or (coverage["lineups"] and not r.get("lineups"))
                            or (coverage["statistics_players"] and not r.get("players"))
                        ):
                            get("fixtures", {"id": fid})
                page = 1
                while True:
                    body = get("players", {"league": league, "season": year, "page": page})
                    if body["paging"]["current"] != page:
                        raise ValueError("API player pagination returned the wrong page")
                    if page >= body["paging"]["total"]:
                        break
                    page += 1
                if seasons[year]["coverage"]["injuries"]:
                    get("injuries", {"league": league, "season": year})
        data = Dataset(root)
        people = data.rows(
            "SELECT DISTINCT api_id FROM players WHERE api_id IS NOT NULL ORDER BY api_id"
        )
        data.close()
        report["players"] = len(people)
        for p in people:
            for endpoint in ("transfers", "sidelined"):
                get(endpoint, {"player": p["api_id"]})
        for year in range(end, start - 1, -1):
            for division, competition in COMPETITIONS.items():
                record, payload = fetcher.get(
                    "football_data",
                    source_url(year, division),
                    historical=year < end,
                    max_age=86400,
                    context={
                        "season_start": year,
                        "season_id": season_name(year),
                        "division": division,
                        "competition_id": competition["id"],
                    },
                )
                football_data.ingest(root, record, payload)
            if year >= 2014:
                record, payload = fetcher.get(
                    "understat",
                    f"https://understat.com/getLeagueData/EPL/{year}",
                    historical=year < end,
                    max_age=86400,
                    context={"kind": "league", "season_start": year},
                )
                understat_ingest.ingest(root, record, payload)
                data = Dataset(root)
                matches = data.rows(
                    "SELECT DISTINCT match_id, source_match_id FROM team_process "
                    "WHERE source_match_id IS NOT NULL AND season_id=?",
                    [season_name(year)],
                )
                data.close()
                for match in matches:
                    if max_requests is not None and len(fetcher.records) - initial >= max_requests:
                        raise QuotaReached(
                            "This backfill invocation reached its request budget; resume"
                        )
                    record, payload = fetcher.get(
                        "understat",
                        f"https://understat.com/getMatchData/{match['source_match_id']}",
                        historical=True,
                        context={"kind": "players", "match_id": match["match_id"]},
                    )
                    understat_ingest.ingest(root, record, payload)
        report["status"] = "complete"
    except QuotaReached as error:
        report.update(status="paused", reason=str(error))
    except Exception as error:
        report.update(status="failed", reason=str(error))
        raise
    finally:
        report["requests_captured"] = len(fetcher.records) - initial
        report["completed_at"] = datetime.now(UTC).isoformat()
        write_json(Path(root) / "audits" / "backfill.json", report)
    return report


def fixture_details_due(fixtures, records, now):
    captured = {}
    for record in records:
        context = record.get("context", {})
        if record["provider"] != "api_football" or context.get("endpoint") != "fixtures":
            continue
        ids = str(context.get("ids", context.get("id", ""))).split("-")
        for value in ids:
            if value:
                fid = int(value)
                observed = datetime.fromisoformat(record["retrieved_at"])
                captured[fid] = max(observed, captured.get(fid, observed))
    selected = []
    for row in fixtures:
        fixture = row["fixture"]
        kickoff = datetime.fromisoformat(fixture["date"])
        previous = captured.get(fixture["id"])
        status = fixture["status"]["short"]
        if status in {"FT", "AET", "PEN", "AWD", "WO"}:
            targets = [
                kickoff + timedelta(hours=2),
                kickoff + timedelta(days=1),
                kickoff + timedelta(days=7),
            ]
            due = any(
                target <= now and (previous is None or previous < target) for target in targets
            )
        else:
            due = kickoff - timedelta(minutes=90) <= now <= kickoff + timedelta(hours=6)
            due = due and (previous is None or (now - previous).total_seconds() >= 600)
        if due:
            selected.append(fixture["id"])
    return selected


def collect(root=Path("data"), season=None):
    now = datetime.now(UTC)
    year = season if season is not None else now.year - (now.month < 7)
    fetcher = Fetcher(root)
    errors = []

    def attempt(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, SourceAccessError, OSError) as error:
            errors.append(str(error))
            return None

    for league, comp in api.LEAGUES.items():
        body = attempt(
            normalized_request, fetcher, "fixtures", {"league": league, "season": year}, max_age=600
        )
        if body is None:
            continue
        fixtures = body["response"]
        teams = {r["teams"][side]["id"] for r in fixtures for side in ("home", "away")}
        for team in sorted(teams):
            record_body = attempt(
                api.request,
                fetcher,
                "players/squads",
                {"team": team},
                max_age=86400,
                context={"competition_id": comp, "season_id": season_name(year)},
            )
            if record_body:
                record, squad = record_body
                record = {
                    **record,
                    "context": {
                        **record["context"],
                        "competition_id": comp,
                        "season_id": season_name(year),
                    },
                }
                attempt(api.normalize, record, squad, root)
        for team in sorted(teams):
            attempt(
                normalized_request,
                fetcher,
                "transfers",
                {"team": team},
                max_age=86400 if now.month in (1, 6, 7, 8, 9) else 7 * 86400,
            )
        attempt(
            normalized_request,
            fetcher,
            "injuries",
            {"league": league, "season": year},
            max_age=14400,
        )
        selected = fixture_details_due(fixtures, fetcher.records, now)
        for offset in range(0, len(selected), 20):
            attempt(
                normalized_request,
                fetcher,
                "fixtures",
                {"ids": "-".join(map(str, selected[offset : offset + 20]))},
                max_age=600,
            )
    record_body = attempt(
        fetcher.get, "fpl", fpl.URL, context={"season_id": season_name(year)}, max_age=1800
    )
    if record_body:
        attempt(fpl.ingest, root, *record_body)
    for division, comp in COMPETITIONS.items():
        context = {
            "season_start": year,
            "season_id": season_name(year),
            "division": division,
            "competition_id": comp["id"],
        }
        response = attempt(
            fetcher.get, "football_data", source_url(year, division), context=context, max_age=86400
        )
        if response:
            attempt(football_data.ingest, root, *response)
    response = attempt(
        fetcher.get,
        "football_data",
        "https://football-data.co.uk/fixtures.csv",
        context={"kind": "latest_odds", "season_id": season_name(year)},
        max_age=21600,
    )
    if response:
        attempt(football_data.ingest, root, *response)
    response = attempt(
        fetcher.get,
        "understat",
        f"https://understat.com/getLeagueData/EPL/{year}",
        context={"kind": "league", "season_start": year},
        max_age=86400,
    )
    if response:
        attempt(understat_ingest.ingest, root, *response)
    data = Dataset(root)
    matches = data.rows(
        "SELECT DISTINCT t.match_id, t.source_match_id, f.match_date "
        "FROM team_process t JOIN fixtures f USING(match_id) "
        "WHERE t.source_match_id IS NOT NULL AND t.season_id=? AND "
        "(f.match_date>=? OR NOT EXISTS "
        "(SELECT 1 FROM player_process p WHERE p.match_id=t.match_id))",
        [season_name(year), (now - timedelta(days=8)).date()],
    )
    data.close()
    for match in matches:
        response = attempt(
            fetcher.get,
            "understat",
            f"https://understat.com/getMatchData/{match['source_match_id']}",
            context={"kind": "players", "match_id": match["match_id"]},
            max_age=86400,
        )
        if response:
            attempt(understat_ingest.ingest, root, *response)
    report = {
        "completed_at": datetime.now(UTC).isoformat(),
        "status": "partial" if errors else "complete",
        "errors": errors,
    }
    write_json(Path(root) / "audits" / "collection.json", report)
    return report


def normalize(root):
    modules = {"football_data": football_data, "understat": understat_ingest, "fpl": fpl}
    requests = [json.loads(p.read_text()) for p in (Path(root) / "requests").glob("*.json")]
    for record in sorted(requests, key=lambda r: r["retrieved_at"]):
        payload = (Path(root) / record["raw_path"]).read_bytes()
        if sha256_bytes(payload) != record["source_sha256"]:
            raise ValueError(f"Raw capture hash mismatch: {record['raw_path']}")
        if record["provider"] == "api_football":
            if record["context"]["endpoint"] != "status":
                api.normalize(record, json.loads(payload), root)
        else:
            modules[record["provider"]].ingest(root, record, payload)


def audit(root):
    data = Dataset(root)
    try:
        data.verify()
        fixtures = data.fixtures()
        counts = {}
        for f in fixtures:
            key = f"{f['competition_id']}/{f['season_id']}/{f['stage']}"
            counts[key] = counts.get(key, 0) + 1
        report = {
            "audited_at": datetime.now(UTC).isoformat(),
            "fixtures": counts,
            "tables": {
                t: data.rows(f"SELECT count(*) AS n FROM {t}")[0]["n"]
                for t in (
                    "players",
                    "appearances",
                    "memberships",
                    "availability",
                    "transfers",
                    "team_process",
                    "player_process",
                    "odds",
                )
            },
            "unresolved_process_players": data.rows(
                "SELECT count(DISTINCT understat_id) AS n "
                "FROM player_process WHERE player_id IS NULL"
            )[0]["n"],
            "unresolved_fpl_codes": data.rows(
                "SELECT count(DISTINCT fpl_code) AS n "
                "FROM availability_observations WHERE fpl_code IS NOT NULL AND player_id IS NULL "
                "AND retrieved_at=(SELECT max(retrieved_at) FROM availability_observations "
                "WHERE provider='fpl')"
            )[0]["n"],
        }
        report["season_coverage"] = data.rows(
            "WITH f AS (SELECT DISTINCT match_id, competition_id, season_id, stage FROM fixtures), "
            "a AS (SELECT DISTINCT match_id FROM appearances) "
            "SELECT competition_id, season_id, "
            "count(*) FILTER (WHERE stage='regular') AS regular_fixtures, "
            "CASE WHEN competition_id='eng-premier-league' THEN 380 ELSE 552 END "
            "AS expected_regular, "
            "count(*) FILTER (WHERE stage<>'regular') AS playoff_fixtures, "
            "count(a.match_id) AS fixtures_with_appearances "
            "FROM f LEFT JOIN a USING(match_id) GROUP BY 1,2 ORDER BY 1,2"
        )
        report["incomplete_starting_lineups"] = data.rows(
            "SELECT match_id, team_id, sum(starts) AS starters, "
            "count(*) FILTER (WHERE minutes IS NULL) AS unknown_minutes "
            "FROM appearances GROUP BY 1,2 HAVING sum(starts)<>11 OR sum(starts) IS NULL "
            "ORDER BY 1,2"
        )
        report["players_without_transfer_capture"] = data.rows(
            "SELECT count(*) AS n FROM players WHERE api_id IS NOT NULL"
        )[0]["n"]
        captured_transfers = set()
        captured_sidelined = set()
        for manifest in data.manifests:
            context = manifest["request"]["context"]
            if context.get("endpoint") == "transfers" and "player" in context:
                captured_transfers.add(int(context["player"]))
            if context.get("endpoint") == "sidelined" and "player" in context:
                captured_sidelined.add(int(context["player"]))
        total_players = report["players_without_transfer_capture"]
        report["players_without_transfer_capture"] = total_players - len(captured_transfers)
        report["players_without_sidelined_capture"] = total_players - len(captured_sidelined)
        report["archive_status"] = (
            "incomplete"
            if (
                report["players_without_transfer_capture"]
                or report["players_without_sidelined_capture"]
                or any(
                    r["regular_fixtures"] != r["expected_regular"]
                    for r in report["season_coverage"]
                )
            )
            else "requires_provider_coverage_review"
        )
        write_json(Path(root) / "audits" / "coverage.json", report)
        return report
    finally:
        data.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backfill", "collect", "normalize", "audit", "query"])
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--start", type=int, default=2010)
    parser.add_argument("--end", type=int)
    parser.add_argument("--max-requests", type=int)
    parser.add_argument(
        "--sql",
        default=(
            "SELECT competition_id, season_id, count(*) FROM fixtures GROUP BY 1,2 ORDER BY 1,2"
        ),
    )
    args = parser.parse_args()
    if args.action == "query":
        data = Dataset(args.root)
        try:
            print(json.dumps(data.rows(args.sql), default=str, indent=2))
        finally:
            data.close()
        return
    with writer_lock(args.root):
        if args.action == "backfill":
            result = backfill(args.root, args.start, args.end, args.max_requests)
        elif args.action == "collect":
            result = collect(args.root, args.end)
        elif args.action == "normalize":
            result = normalize(args.root)
        else:
            result = audit(args.root)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
