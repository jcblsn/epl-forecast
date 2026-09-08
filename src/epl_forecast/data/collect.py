"""Small local collection loops shared by backfill and ongoing ingestion."""

import argparse
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from epl_forecast.data import api_football as api
from epl_forecast.data import football_data, fpl, understat_ingest
from epl_forecast.data.capture import (
    Fetcher,
    QuotaReached,
    SourceAccessError,
    WriterBusy,
    writer_lock,
)
from epl_forecast.data.sources import COMPETITIONS, season_name, source_url
from epl_forecast.datasets import Dataset
from epl_forecast.storage import sha256_bytes, write_json

FIXTURE_REFRESH_SECONDS = 12 * 3600


def normalized_request(fetcher, endpoint, params=None, **kwargs):
    record, body = api.request(fetcher, endpoint, params, **kwargs)
    api.normalize(record, body, fetcher.root)
    return body


def prioritized_players(root, start, end):
    data = Dataset(root)
    try:
        return data.rows(
            "WITH seasons AS (SELECT player_id, season_id, competition_id FROM memberships UNION "
            "SELECT player_id, season_id, competition_id FROM appearances), people AS ("
            "SELECT p.player_id, p.api_id, max(s.season_id) AS latest_season, "
            "min(s.competition_id) AS competition_id "
            "FROM players p JOIN seasons s USING(player_id) "
            "WHERE p.api_id IS NOT NULL AND s.season_id>=? AND s.season_id<=? "
            "GROUP BY 1,2) SELECT *, row_number() OVER (PARTITION BY competition_id, latest_season "
            "ORDER BY api_id) AS priority_slot FROM people "
            "ORDER BY latest_season DESC, priority_slot, competition_id",
            [season_name(start), season_name(end)],
        )
    finally:
        data.close()


def recent_readiness(root, end):
    data = Dataset(root)
    try:
        cohorts = {
            (comp["id"], season_name(year)): {
                "competition_id": comp["id"],
                "season_id": season_name(year),
                "expected_fixtures": comp["matches"],
                "fixtures": 0,
                "finished": 0,
                "finished_with_starter_minutes": 0,
            }
            for comp in COMPETITIONS.values()
            for year in range(end - 3, end + 1)
        }
        appearances = {
            r["match_id"]: r["n"]
            for r in data.rows(
                "SELECT match_id, count(DISTINCT player_id) AS n FROM appearances "
                "WHERE starts=1 AND minutes IS NOT NULL GROUP BY match_id"
            )
        }
        for fixture in data.fixtures():
            row = cohorts.get((fixture["competition_id"], fixture["season_id"]))
            if row is None or fixture["stage"] != "regular":
                continue
            row["fixtures"] += 1
            if fixture["status"] == "finished":
                row["finished"] += 1
                row["finished_with_starter_minutes"] += (
                    appearances.get(fixture["match_id"], 0) == 22
                )
        captures = {
            endpoint: {
                int(m["request"]["context"]["player"])
                for m in data.manifests
                if m["request"]["context"].get("endpoint") == endpoint
                and "player" in m["request"]["context"]
            }
            for endpoint in ("transfers", "sidelined")
        }
    finally:
        data.close()
    rows = list(cohorts.values())
    match_ready = all(
        r["fixtures"] == r["expected_fixtures"]
        and (r["season_id"] == season_name(end) or r["finished"] == r["expected_fixtures"])
        for r in rows
    )
    current = prioritized_players(root, end, end)
    report = {
        "audited_at": datetime.now(UTC).isoformat(),
        "window_start": season_name(end - 3),
        "window_end": season_name(end),
        "seasons": rows,
        "ready_for_match_experiments": match_ready,
        "ready_for_player_experiments": match_ready
        and all(r["finished"] == r["finished_with_starter_minutes"] for r in rows),
        "current_players": len(current),
        "pending_current_player_histories": {
            endpoint: sum(p["api_id"] not in captured for p in current)
            for endpoint, captured in captures.items()
        },
        "scope": "Input coverage only; not model validation or historical point-in-time evidence",
    }
    write_json(Path(root) / "audits" / "recent_readiness.json", report)
    return report


def backfill(root=Path("data"), start=2010, end=None, max_requests=None):
    now = datetime.now(UTC)
    end = end if end is not None else now.year - (now.month < 7)
    if start > end:
        raise ValueError("Backfill start must not exceed end")
    previous_report = Path(root) / "audits" / "backfill.json"
    if previous_report.exists():
        previous = json.loads(previous_report.read_text())
        if (
            previous.get("status") == "complete"
            and previous.get("start") == start
            and previous.get("end") == end
        ):
            return previous
    fetcher = Fetcher(root, reserve=1000)
    report = {"started_at": now.isoformat(), "start": start, "end": end, "status": "running"}
    initial = len(fetcher.records)

    def get(endpoint, params=None, **kwargs):
        if max_requests is not None and len(fetcher.records) - initial >= max_requests:
            raise QuotaReached("This backfill invocation reached its request budget; resume")
        return normalized_request(fetcher, endpoint, params, historical=True, **kwargs)

    def season_pass(years):
        for year in years:
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

    try:
        report["subscription"] = api.preflight(fetcher)
        catalog = {
            league: get("leagues", {"id": league})["response"][0]["seasons"]
            for league in api.LEAGUES
        }
        recent_start = max(start, end - 3)
        for phase, years, first in [
            ("current", [end], end),
            ("recent", range(end - 1, recent_start - 1, -1), recent_start),
            ("older", range(recent_start - 1, start - 1, -1), start),
        ]:
            report["phase"] = f"{phase}_fixtures_and_players"
            season_pass(years)
            report["phase"] = f"{phase}_player_histories"
            people = prioritized_players(root, first, end)
            report[f"{phase}_players"] = len(people)
            print(
                f"Backfill {phase}: sidelined and transfers for {len(people)} players", flush=True
            )
            for person in people:
                for endpoint in ("sidelined", "transfers"):
                    get(endpoint, {"player": person["api_id"]})
            report[f"{phase}_api_complete"] = True
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
        report["recent_readiness"] = recent_readiness(root, end)
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
            due = due and (
                previous is None or (now - previous).total_seconds() >= FIXTURE_REFRESH_SECONDS
            )
        if due and (
            previous is None or (now - previous).total_seconds() >= FIXTURE_REFRESH_SECONDS
        ):
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
            normalized_request,
            fetcher,
            "fixtures",
            {"league": league, "season": year},
            max_age=FIXTURE_REFRESH_SECONDS,
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
        page = 1
        while True:
            players = attempt(
                normalized_request,
                fetcher,
                "players",
                {"league": league, "season": year, "page": page},
                max_age=7 * 86400,
            )
            if players is None:
                break
            if players["paging"]["current"] != page:
                errors.append(f"Wrong player page for {comp}: expected {page}")
                break
            if page >= players["paging"]["total"]:
                break
            page += 1
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
                max_age=FIXTURE_REFRESH_SECONDS,
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
    root = Path(root)
    modules = {"football_data": football_data, "understat": understat_ingest, "fpl": fpl}
    requests = [json.loads(p.read_text()) for p in (root / "requests").glob("*.json")]

    def order(record):
        provider, context = record["provider"], record["context"]
        phase = 0
        if provider == "api_football" and context["endpoint"] in (
            "injuries",
            "sidelined",
            "transfers",
        ):
            phase = 1
        elif provider == "football_data" and context.get("kind") == "latest_odds":
            phase = 2
        elif provider == "understat":
            phase = 2 if context["kind"] == "league" else 3
        elif provider == "fpl":
            phase = 4
        return phase, record["retrieved_at"], record["url"], record["source_sha256"]

    with tempfile.TemporaryDirectory(prefix=".normalize-", dir=root) as temporary:
        staging = Path(temporary)
        for record in sorted(requests, key=order):
            payload = (root / record["raw_path"]).read_bytes()
            if sha256_bytes(payload) != record["source_sha256"]:
                raise ValueError(f"Raw capture hash mismatch: {record['raw_path']}")
            if record["provider"] == "api_football":
                if record["context"]["endpoint"] != "status":
                    api.normalize(record, json.loads(payload), staging)
            else:
                modules[record["provider"]].ingest(staging, record, payload)
        data = Dataset(staging)
        try:
            data.verify()
            data.fixtures()
        finally:
            data.close()
        replaced = []
        try:
            for name in ("parquet", "manifests"):
                (staging / name).mkdir(exist_ok=True)
                old = staging / ("previous-" + name)
                if (root / name).exists():
                    (root / name).rename(old)
                replaced.append(name)
                (staging / name).rename(root / name)
        except OSError:
            for name in reversed(replaced):
                if (root / name).exists():
                    (root / name).rename(staging / name)
                old = staging / ("previous-" + name)
                if old.exists():
                    old.rename(root / name)
            raise

    return {"status": "complete", "requests_replayed": len(requests)}


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
        report["normalization_issues"] = [
            {"source_sha256": m["request"]["source_sha256"], **issue}
            for m in data.manifests
            for issue in m["request"].get("normalization_issues", [])
        ]
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
            "SELECT count(*) AS n FROM players p WHERE api_id IS NOT NULL AND "
            "(EXISTS (SELECT 1 FROM memberships m WHERE m.player_id=p.player_id) OR "
            "EXISTS (SELECT 1 FROM appearances a WHERE a.player_id=p.player_id))"
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
    try:
        with writer_lock(args.root):
            if args.action == "backfill":
                result = backfill(args.root, args.start, args.end, args.max_requests)
            elif args.action == "collect":
                result = collect(args.root, args.end)
            elif args.action == "normalize":
                result = normalize(args.root)
            else:
                result = audit(args.root)
    except WriterBusy as error:
        result = {"status": "skipped", "reason": str(error)}
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
