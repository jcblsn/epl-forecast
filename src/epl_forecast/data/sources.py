import csv
import io
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from epl_forecast.storage import file_hash, json_bytes, sha256_bytes, write_immutable

COMPETITIONS = {
    "E0": {"id": "eng-premier-league", "teams": 20, "matches": 380},
    "E1": {"id": "eng-championship", "teams": 24, "matches": 552},
}
REQUIRED_FIELDS = {"Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}


class SourceAccessError(RuntimeError):
    pass


def download(
    url: str, attempts: int = 3, headers: dict[str, str] | None = None
) -> tuple[bytes, dict]:
    if attempts < 1:
        raise ValueError("attempts must be positive")
    for attempt in range(attempts):
        try:
            request = Request(
                url, headers={"User-Agent": "epl-forecast/0.1 (research)", **(headers or {})}
            )
            with urlopen(request, timeout=30) as response:
                payload = response.read()
                metadata = {
                    "url": url,
                    "final_url": response.url,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "sha256": sha256_bytes(payload),
                    "bytes": len(payload),
                    "headers": dict(response.headers),
                }
                return payload, metadata
        except HTTPError as error:
            if error.code in {401, 403}:
                raise SourceAccessError(
                    f"Access denied (HTTP {error.code}) for {url}. "
                    "Check source permissions or credentials; no authentication retries made."
                ) from error
            if error.code not in {429, 500, 502, 503, 504} or attempt == attempts - 1:
                raise SourceAccessError(f"HTTP {error.code} downloading {url}") from error
        except (URLError, TimeoutError) as error:
            if attempt == attempts - 1:
                raise SourceAccessError(f"Cannot download {url}: {error}") from error
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def csv_rows(payload: bytes) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    fields = reader.fieldnames or []
    if not REQUIRED_FIELDS.issubset(fields):
        raise ValueError(f"Missing CSV fields: {sorted(REQUIRED_FIELDS - set(fields))}")
    rows = []
    for line, row in enumerate(reader, 2):
        if not any(value for value in row.values()):
            continue
        extra = row.pop(None, None)
        if extra and any(extra):
            raise ValueError(f"Unexpected extra CSV values at row {line}")
        rows.append((line, {key: (value or "").strip() for key, value in row.items()}))
    if not rows:
        raise ValueError("Source CSV contains no matches")
    return fields, rows


def season_name(start: int) -> str:
    if not 1993 <= start <= 2098:
        raise ValueError("Season start must be between 1993 and 2098")
    return f"{start}-{start + 1}"


def source_url(start: int, division: str) -> str:
    season_name(start)
    if division not in COMPETITIONS:
        raise ValueError(f"Unsupported division: {division}")
    code = f"{start % 100:02d}{(start + 1) % 100:02d}"
    return f"https://football-data.co.uk/mmz4281/{code}/{division}.csv"


def fetch_snapshot(
    root: Path, snapshot_path: Path, start: int, end: int, divisions: list[str]
) -> dict:
    if start > end or not divisions or len(set(divisions)) != len(divisions):
        raise ValueError("Specify an ordered season range and distinct divisions")
    requests = [(year, div) for year in range(start, end + 1) for div in sorted(divisions)]
    for year, div in requests:
        source_url(year, div)
    if snapshot_path.exists():
        snapshot = read_snapshot(snapshot_path)
        actual = [(entry["season_start"], entry["division"]) for entry in snapshot["files"]]
        if actual != requests:
            raise ValueError("Snapshot already exists with different seasons or divisions")
        restore_snapshot(root, snapshot)
        return snapshot

    entries = []
    for year, division in requests:
        url = source_url(year, division)
        relative_dir = Path("raw/football_data") / season_name(year) / division
        cached = sorted((root / relative_dir).glob("*.csv"))
        if len(cached) > 1:
            raise ValueError(f"Multiple raw versions in {relative_dir}; use a pinned snapshot")
        if cached:
            path = cached[0]
            metadata = json.loads(path.with_suffix(".metadata.json").read_text())
            if file_hash(path) != metadata["sha256"] or path.stem != metadata["sha256"]:
                raise ValueError(f"Raw checksum mismatch: {path}")
            if metadata["url"] != url:
                raise ValueError(f"Raw source URL mismatch: {path}")
            payload = path.read_bytes()
        else:
            payload, metadata = download(url)
            csv_rows(payload)
            path = root / relative_dir / f"{metadata['sha256']}.csv"
            write_immutable(path, payload)
            write_immutable(path.with_suffix(".metadata.json"), json_bytes(metadata))
        csv_rows(payload)
        entries.append(
            {
                "source": "football-data.co.uk",
                "season_start": year,
                "season_id": season_name(year),
                "division": division,
                "competition_id": COMPETITIONS[division]["id"],
                "path": path.relative_to(root).as_posix(),
                **{key: metadata[key] for key in ("url", "sha256", "retrieved_at", "bytes")},
            }
        )
        print(f"Cached {season_name(year)} {division}", flush=True)
    snapshot = {"schema_version": 1, "files": entries}
    write_immutable(snapshot_path, json_bytes(snapshot))
    return snapshot


def read_snapshot(path: Path) -> dict:
    snapshot = json.loads(path.read_text())
    if snapshot.get("schema_version") != 1 or not snapshot.get("files"):
        raise ValueError("Unsupported or empty snapshot")
    seen = set()
    for entry in snapshot["files"]:
        expected_url = source_url(entry["season_start"], entry["division"])
        key = entry["season_start"], entry["division"]
        if key in seen:
            raise ValueError(f"Duplicate snapshot entry: {key}")
        seen.add(key)
        if entry["url"] != expected_url:
            raise ValueError("Snapshot source URL does not match season and division")
        if entry["season_id"] != season_name(entry["season_start"]):
            raise ValueError("Snapshot season ID mismatch")
        if entry["competition_id"] != COMPETITIONS[entry["division"]]["id"]:
            raise ValueError("Snapshot competition ID mismatch")
        expected_path = (
            f"raw/football_data/{entry['season_id']}/{entry['division']}/{entry['sha256']}.csv"
        )
        if entry["path"] != expected_path:
            raise ValueError("Unexpected raw snapshot path")
    return snapshot


def restore_snapshot(root: Path, snapshot: dict) -> None:
    for entry in snapshot["files"]:
        path = root / entry["path"]
        if path.exists():
            if file_hash(path) != entry["sha256"]:
                raise ValueError(f"Raw checksum mismatch: {path}")
            continue
        payload, metadata = download(entry["url"])
        if sha256_bytes(payload) != entry["sha256"]:
            raise ValueError(
                f"Upstream data changed for {entry['url']}. "
                "Restore the original raw file or create a new snapshot; refusing silent drift."
            )
        write_immutable(path, payload)
        write_immutable(path.with_suffix(".metadata.json"), json_bytes(metadata))
