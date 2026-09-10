"""Re-check everything under a site directory against the publication boundary.

The pipeline already checks each document as it writes it. This runs the same
check over the whole committed surface, so a hand-edited or hand-copied file
cannot reach a public deployment.
"""

import argparse
import json
from pathlib import Path

from epl_forecast.publication import check_publishable, load_policy

ALLOWED_SUFFIXES = {".json", ".html", ".css", ".js", ".txt", ".svg", ""}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument("--policy", type=Path, default=Path("configs/publication.toml"))
    args = parser.parse_args()
    policy = load_policy(args.policy)
    unexpected = [
        path.as_posix()
        for path in sorted(args.site.rglob("*"))
        if path.is_file() and path.suffix.lower() not in ALLOWED_SUFFIXES
    ]
    if unexpected:
        raise SystemExit(f"Unexpected file types on the published surface: {unexpected}")
    documents = sorted((args.site / "data").rglob("*.json"))
    for path in documents:
        try:
            check_publishable(json.loads(path.read_text()), policy)
        except ValueError as error:
            raise SystemExit(f"{path}: {error}") from None
    print(f"{len(documents)} published documents pass the publication boundary")


if __name__ == "__main__":
    main()
